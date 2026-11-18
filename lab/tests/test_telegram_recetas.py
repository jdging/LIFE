"""Contrato del adaptador de recetas, sin bot ni datos reales."""

import asyncio
import importlib.util
import json
import sys
from contextvars import ContextVar, copy_context
from pathlib import Path
from shutil import copyfile
from threading import Thread
from types import ModuleType, SimpleNamespace
from wsgiref.simple_server import make_server

import pytest

import telegram_recetas
from telegram_recetas import ingest
from telegram_ingesta import ApiError, CliError


ROUTE = {"platform": "telegram", "profile": "lasso", "chat_type": "dm",
         "chat_id": "1234", "user_id": "1234", "message_id": "42"}
RECIPE = {"titulo": "Sopa", "ingredientes": [{"nombre": "Sal", "cantidad": None, "unidad": "a gusto"}],
          "pasos": ["Mezclar."]}


def test_explicit_complete_recipe_is_saved_with_telegram_event_key():
    posted = []

    def save(payload):
        posted.append(payload)
        return {**RECIPE, "id": 7, "version": 1}

    result = ingest(ROUTE, {"accion": "guardar", "receta": RECIPE}, save)

    assert posted == [{**RECIPE, "clave_ingesta": "telegram:lasso:1234:42", "allow_duplicado": False}]
    assert result == {"estado": "guardada", "receta": {**RECIPE, "id": 7, "version": 1},
                      "mensaje": "Guardé Sopa (receta #7, versión 1).\n\nIngredientes:\n- Sal (a gusto)\n\nPreparación:\n1. Mezclar."}


@pytest.mark.parametrize("incomplete,missing", [
    ({}, ["titulo", "ingredientes", "pasos"]),
    ({**RECIPE, "titulo": " "}, ["titulo"]),
    ({**RECIPE, "ingredientes": [{"nombre": " "}]}, ["ingredientes"]),
    ({**RECIPE, "pasos": [""]}, ["pasos"]),
])
def test_incomplete_recipe_asks_without_saving(incomplete, missing):
    result = ingest(ROUTE, {"accion": "guardar", "receta": incomplete},
                    lambda _: pytest.fail("No debe guardar datos incompletos"))
    assert result["estado"] == "faltan_datos"
    assert result["campos"] == missing


def test_duplicate_requires_a_new_event_in_the_same_chat_and_uses_original_recipe():
    pending = {}
    posted = []

    def save(payload):
        posted.append(payload)
        if not payload["allow_duplicado"]:
            raise ApiError(409, "duplicate", {"code": "receta_duplicada"})
        return {**RECIPE, "id": 8, "version": 1}

    confirm = {"accion": "confirmar_duplicado", "receta": {**RECIPE, "titulo": "Otra"}}
    duplicate = ingest(ROUTE, {"accion": "guardar", "receta": RECIPE}, save, pending=pending)
    assert duplicate["estado"] == "duplicada"
    kwargs = {"pending": pending, "confirmation_code": duplicate["confirmacion"].split()[-1]}
    assert ingest(ROUTE, confirm, save, **kwargs)["estado"] == "sin_confirmacion_pendiente"
    other_dm = {**ROUTE, "chat_id": "5678", "user_id": "5678", "message_id": "43"}
    assert ingest(other_dm, confirm, save, **kwargs)["estado"] == "sin_confirmacion_pendiente"
    assert ingest({**ROUTE, "message_id": "43"}, confirm, save, **kwargs)["estado"] == "guardada"
    assert ingest({**ROUTE, "message_id": "44"}, confirm, save, **kwargs)["estado"] == "sin_confirmacion_pendiente"
    assert posted == [{**RECIPE, "clave_ingesta": "telegram:lasso:1234:42", "allow_duplicado": allow}
                      for allow in [False, True]]


def test_unrelated_conflict_does_not_offer_duplicate_override():
    def save(_):
        raise ApiError(409, "private upstream detail", {"code": "other"})

    result = ingest(ROUTE, {"accion": "guardar", "receta": RECIPE}, save)
    assert result["estado"] == "error_api"
    assert "private upstream detail" not in str(result)


def test_duplicate_prompt_replay_does_not_replace_the_pending_recipe():
    pending = {}
    def conflict(_):
        raise ApiError(409, "duplicate", {"code": "receta_duplicada"})

    first = ingest(ROUTE, {"accion": "guardar", "receta": RECIPE}, conflict, pending=pending)
    modified = {**RECIPE, "titulo": "Otro"}
    replay = ingest(ROUTE, {"accion": "guardar", "receta": modified}, conflict, pending=pending)
    assert replay == first


@pytest.mark.parametrize("base", [None, "http://127.0.0.1:mal", "https://example.com", "http://127.0.0.1:123/api"])
def test_configuration_requires_explicit_loopback_origin(base):
    with pytest.raises(CliError):
        telegram_recetas.recipe_api(base, "unused-file")


def test_event_replay_and_duplicate_confirmation_against_real_api(tmp_path):
    from api import create_app
    from tests.test_api import TEST_SECRET

    app = create_app(str(tmp_path / "recipes.sqlite"), TEST_SECRET)
    with make_server("127.0.0.1", 0, app) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            secret_file = tmp_path / "secret"
            secret_file.touch(mode=0o600)
            secret_file.write_text(TEST_SECRET)
            client = telegram_recetas.recipe_api(f"http://127.0.0.1:{server.server_port}", str(secret_file))
            request = {"accion": "guardar", "receta": RECIPE}
            pending = {}
            first = ingest(ROUTE, request, client.save_recipe, pending=pending)
            replay = ingest(ROUTE, {**request, "receta": {**RECIPE, "titulo": "Otro"}},
                            client.save_recipe, pending=pending)
            assert first == replay
            assert first["estado"] == "guardada"
            assert "Mezclar." in first["mensaje"]
            duplicate = ingest({**ROUTE, "message_id": "43"}, request, client.save_recipe, pending=pending)
            assert duplicate["estado"] == "duplicada"
            confirmed = ingest({**ROUTE, "message_id": "44"}, {"accion": "confirmar_duplicado"},
                               client.save_recipe, pending=pending,
                               confirmation_code=duplicate["confirmacion"].split()[-1])
            assert confirmed["estado"] == "guardada"
            assert confirmed["receta"]["id"] != first["receta"]["id"]
            assert client._request("GET", "/api/recetas")["recetas"] == [first["receta"], confirmed["receta"]]
        finally:
            server.shutdown()
            thread.join()
            app.close()


@pytest.fixture
def plugin_turn(tmp_path, monkeypatch):
    lab = Path(telegram_recetas.__file__).parent
    package = tmp_path / "lasso_recetas_test"
    package.mkdir()
    copyfile(lab / "hermes" / "lasso-recetas" / "__init__.py", package / "__init__.py")
    for name in ("telegram_recetas.py", "telegram_ingesta.py"):
        copyfile(lab / name, package / name)
    gateway = ModuleType("gateway.session_context")
    metadata = {f"HERMES_SESSION_{key.upper()}": value for key, value in ROUTE.items()}
    metadata["HERMES_SESSION_KEY"] = "agent:lasso:telegram:dm:1234"
    metadata["HERMES_SESSION_THREAD_ID"] = ""
    setattr(gateway, "_VAR_MAP", {key: ContextVar(key, default=None) for key in metadata})
    for key, value in metadata.items():
        gateway._VAR_MAP[key].set(value)
    setattr(gateway, "get_session_env", lambda key: metadata.get(key, ""))
    monkeypatch.setitem(sys.modules, "gateway.session_context", gateway)
    telegram = ModuleType("telegram")
    setattr(telegram, "Message", SimpleNamespace)
    monkeypatch.setitem(sys.modules, "telegram", telegram)
    spec = importlib.util.spec_from_file_location(package.name, package / "__init__.py")
    assert spec is not None and spec.loader is not None
    plugin = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, package.name, plugin)
    spec.loader.exec_module(plugin)
    calls = []

    def save(payload):
        calls.append(payload)
        return {**RECIPE, "id": 1, "version": 1}

    monkeypatch.setattr(plugin, "_save", save)
    monkeypatch.setattr(plugin, "_dedicated_lasso", lambda gateway: True)
    registration = {}
    hooks = {}
    plugin.register(SimpleNamespace(register_tool=lambda **kwargs: registration.update(kwargs),
                                    register_hook=lambda name, cb: hooks.update({name: cb})))

    async def deliver(ready, text, *, message_id="42", admit=True, before=True,
                      event_text=None, different_task=False, **raw_fields):
        route = {**ROUTE, "message_id": message_id}
        session_key = metadata["HERMES_SESSION_KEY"]
        gateway._VAR_MAP["HERMES_SESSION_MESSAGE_ID"].set(message_id)
        source = SimpleNamespace(**{**route, "platform": SimpleNamespace(value="telegram")})
        raw = SimpleNamespace(text=text, message_id=int(message_id), chat=SimpleNamespace(id=1234, type="private"),
                              from_user=SimpleNamespace(id=1234, is_bot=False), **raw_fields)
        # Match the payloads from the installed Hermes hooks.
        if before and "pre_gateway_dispatch" in hooks:
            hooks["pre_gateway_dispatch"](event=SimpleNamespace(source=source, raw_message=raw,
                                          message_id=message_id, text=text), gateway=object())
        if admit and "post_gateway_admission" in hooks:
            async def post():
                hooks["post_gateway_admission"](session_key=session_key, source=route, platform="telegram",
                                                message_id=message_id, text=event_text if event_text is not None else text)
            if different_task:
                await asyncio.create_task(post())
            else:
                await post()
        ready.set()
        await asyncio.Future()  # Keep the inbound task alive while the test calls the handler.

    context = copy_context()
    task = None

    async def end():
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def start(*args, **kwargs):
        nonlocal task
        await end()
        ready = asyncio.Event()
        task = asyncio.create_task(deliver(ready, *args, **kwargs), context=context)
        await asyncio.wait_for(ready.wait(), 2)

    with asyncio.Runner() as runner:
        yield SimpleNamespace(plugin=plugin, deliver=lambda *a, **kw: runner.run(start(*a, **kw)),
                              vars=gateway._VAR_MAP, calls=calls, context=context,
                              end=lambda: runner.run(end()), api_error=plugin.ingest.__globals__["ApiError"],
                              handle=lambda params: json.loads(context.run(registration["handler"], params)))


SAVE_TEXT = "Guardá esta receta:\nSopa. Ingrediente: sal a gusto. Paso: Mezclar."
SAVE_REQUEST = {"accion": "guardar", "receta": RECIPE}


@pytest.mark.parametrize("text,options", [
    (SAVE_TEXT, {"admit": False}), (SAVE_TEXT, {"before": False}),
    ("¿Tenés una receta de sopa?", {}), ("Nota: " + SAVE_TEXT, {}),
    ("> " + SAVE_TEXT, {}), ("Guardá esta receta:", {}),
    (SAVE_TEXT, {"forward_origin": object()}), (SAVE_TEXT, {"quote": object()}),
    (SAVE_TEXT, {"external_reply": object()}), (SAVE_TEXT, {"reply_to_message": object()}),
    (SAVE_TEXT, {"edit_date": object()}), (SAVE_TEXT, {"different_task": True}),
    (None, {}),  # A transcript is not raw Telegram text.
    (SAVE_TEXT, {"entities": [SimpleNamespace(type="blockquote")]}),
    (SAVE_TEXT, {"event_text": SAVE_TEXT + "\nOtro evento"}),
])
def test_untrusted_intent_never_calls_recipe_api(plugin_turn, text, options):
    plugin_turn.deliver(text, **options)
    assert plugin_turn.handle({**SAVE_REQUEST, **ROUTE})["estado"] == "no_autorizada"
    assert plugin_turn.calls == []


def test_authorization_is_bound_to_turn_and_consumed_once(plugin_turn):
    plugin_turn.deliver(SAVE_TEXT)
    for key, wrong in [("PLATFORM", "cli"), ("PROFILE", "other"), ("CHAT_TYPE", "group"),
                       ("MESSAGE_ID", "43"), ("USER_ID", "9876"), ("KEY", "different"),
                       ("THREAD_ID", "123")]:
        var = plugin_turn.vars[f"HERMES_SESSION_{key}"]
        token = plugin_turn.context.run(var.set, wrong)
        try:
            assert plugin_turn.handle(SAVE_REQUEST)["estado"] == "no_autorizada"
        finally:
            plugin_turn.context.run(var.reset, token)
    assert plugin_turn.calls == []
    assert plugin_turn.handle({"accion": "confirmar_duplicado"})["estado"] == "no_autorizada"
    assert plugin_turn.handle(SAVE_REQUEST)["estado"] == "guardada"
    assert plugin_turn.handle(SAVE_REQUEST)["estado"] == "no_autorizada"
    assert len(plugin_turn.calls) == 1


def test_environment_is_not_a_bound_gateway_context(plugin_turn, monkeypatch):
    plugin_turn.deliver(SAVE_TEXT)
    for name, var in plugin_turn.vars.items():
        monkeypatch.setenv(name, plugin_turn.context.run(var.get))
        plugin_turn.context.run(var.set, None)
    assert plugin_turn.handle(SAVE_REQUEST)["estado"] == "no_autorizada"
    assert plugin_turn.calls == []


def test_duplicate_requires_exact_message_for_current_proposal(plugin_turn, monkeypatch):
    calls = plugin_turn.calls

    def save(payload):
        calls.append(payload)
        if not payload["allow_duplicado"]:
            raise plugin_turn.api_error(409, "duplicate", {"code": "receta_duplicada"})
        return {**RECIPE, "id": 8, "version": 1}

    monkeypatch.setattr(plugin_turn.plugin, "_save", save)
    plugin_turn.deliver(SAVE_TEXT)
    duplicate = plugin_turn.handle(SAVE_REQUEST)
    confirmation = duplicate["confirmacion"]
    assert confirmation.startswith("Confirmá duplicado: ") and confirmation in duplicate["mensaje"]
    confirm = {"accion": "confirmar_duplicado", "receta": {**RECIPE, "titulo": "Otra"}}
    calls.clear()
    for message_id, text, args in [("43", "Sí", {"confirmacion": confirmation}),
                                    ("44", confirmation + " por favor", {}),
                                    ("45", "Confirmá duplicado: 0000000000000000", {})]:
        plugin_turn.deliver(text, message_id=message_id)
        assert plugin_turn.handle({**confirm, **args})["estado"] != "guardada"
    assert calls == []
    plugin_turn.deliver(confirmation, message_id="46")
    assert plugin_turn.handle(confirm)["estado"] == "guardada"
    assert calls == [{**RECIPE, "clave_ingesta": "telegram:lasso:1234:42", "allow_duplicado": True}]


@pytest.mark.parametrize("end_turn", [False, True])
def test_unused_authorization_expires_or_ends_with_its_turn(plugin_turn, monkeypatch, end_turn):
    monkeypatch.setattr(plugin_turn.plugin, "monotonic", lambda: 1000)
    plugin_turn.deliver(SAVE_TEXT)
    if end_turn:
        plugin_turn.end()
    else:
        monkeypatch.setattr(plugin_turn.plugin, "monotonic", lambda: 1000 + plugin_turn.plugin.INTENT_TTL)
    assert plugin_turn.handle(SAVE_REQUEST)["estado"] == "no_autorizada"
    assert plugin_turn.calls == []


def test_confirmation_code_cannot_be_reused_for_a_replacement_or_expired_proposal(monkeypatch):
    now = 1000
    monkeypatch.setattr(telegram_recetas, "monotonic", lambda: now)
    codes = iter(["1" * 16, "2" * 16])
    monkeypatch.setattr(telegram_recetas, "token_hex", lambda _: next(codes))
    pending = {}

    def conflict(_):
        raise ApiError(409, "duplicate", {"code": "receta_duplicada"})

    assert ingest(ROUTE, SAVE_REQUEST, conflict, pending=pending)["estado"] == "duplicada"
    assert ingest({**ROUTE, "message_id": "43"}, SAVE_REQUEST, conflict, pending=pending)["estado"] == "duplicada"
    for code in ("1" * 16, "2" * 16):
        result = ingest({**ROUTE, "message_id": "44"}, {"accion": "confirmar_duplicado"},
                        lambda _: pytest.fail("No debe confirmar"), pending=pending, confirmation_code=code)
        assert result["estado"] == "sin_confirmacion_pendiente"
        now += telegram_recetas.PENDING_TTL
