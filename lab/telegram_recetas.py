"""Adaptador de recetas para eventos autorizados de Lasso en Telegram."""

import re
from copy import deepcopy
from dataclasses import dataclass
from secrets import token_hex
from time import monotonic
from types import SimpleNamespace
from urllib.parse import urlsplit

if __package__:
    from .telegram_ingesta import ApiClient, ApiError, CliError, _resolver_secret
else:
    from telegram_ingesta import ApiClient, ApiError, CliError, _resolver_secret


class RecipeApiClient(ApiClient):
    def save_recipe(self, payload):
        recipe = self._request("POST", "/api/recetas", json_body=payload)
        if not isinstance(recipe, dict) or _missing_fields(recipe) or any(
            type(recipe.get(field)) is not int or recipe[field] < 1 for field in ("id", "version")
        ):
            raise ApiError(0, "respuesta de receta inválida.")
        return recipe


def recipe_api(base_url, secret_file):
    """Configuración dedicada y explícita; no cae en la de gastos."""
    if not base_url or not secret_file:
        raise CliError("falta configurar la API candidata de recetas.")
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError:
        raise CliError("origen inválido para la API candidata de recetas.") from None
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "::1"}
            or not port or parts.path not in ("", "/") or parts.query or parts.fragment
            or parts.username is not None or parts.password is not None):
        raise CliError("la API candidata debe ser un origen HTTP loopback con puerto explícito.")
    return RecipeApiClient(base_url, _resolver_secret(SimpleNamespace(secret_file=secret_file)))


def _saved_message(recipe):
    ingredients = []
    for item in recipe["ingredientes"]:
        measure = " ".join(str(item[k]) for k in ("cantidad", "unidad") if item.get(k) is not None)
        ingredients.append(f"- {item['nombre']} ({measure})" if measure else f"- {item['nombre']}")
    steps = [f"{n}. {step}" for n, step in enumerate(recipe["pasos"], start=1)]
    return "\n".join([
        f"Guardé {recipe['titulo']} (receta #{recipe['id']}, versión {recipe['version']}).",
        "", "Ingredientes:", *ingredients, "", "Preparación:", *steps,
    ])


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _missing_fields(recipe):
    missing = []
    if not _nonblank(recipe.get("titulo")):
        missing.append("titulo")
    ingredients = recipe.get("ingredientes")
    if not isinstance(ingredients, list) or not ingredients or not all(
        isinstance(item, dict) and _nonblank(item.get("nombre")) for item in ingredients
    ):
        missing.append("ingredientes")
    steps = recipe.get("pasos")
    if not isinstance(steps, list) or not steps or not all(map(_nonblank, steps)):
        missing.append("pasos")
    return missing


SAVE_HEADER = "Guardá esta receta:"
CONFIRM_HEADER = "Confirmá duplicado: "
PENDING_TTL = 600


@dataclass(frozen=True)
class _Proposal:
    event: int
    payload: dict
    code: str
    expires_at: float


def _duplicate_prompt(proposal):
    title = proposal.payload["titulo"]
    confirmation = CONFIRM_HEADER + proposal.code
    return {"estado": "duplicada", "confirmacion": confirmation,
            "mensaje": f"Ya hay una receta con el título {title}. Para guardarla como otra, "
                       f"mandame en este chat, como mensaje nuevo y dentro de 10 minutos:\n{confirmation}"}


def ingest(route, request, save, *, pending=None, confirmation_code=None) -> dict:
    """Adaptador interno: el plugin valida la intención antes de llamar, y aporta el código del evento."""
    chat = route.get("chat_id")
    event = route.get("message_id")
    if (route.get("platform"), route.get("profile"), route.get("chat_type")) != ("telegram", "lasso", "dm") or not (
        isinstance(chat, str) and re.fullmatch(r"[1-9][0-9]{0,19}", chat) and chat == route.get("user_id")
        and isinstance(event, str) and re.fullmatch(r"[1-9][0-9]{0,19}", event)
    ):
        return {"estado": "no_autorizada"}
    action = request.get("accion")
    if action not in ("guardar", "confirmar_duplicado"):
        return {"estado": "ignorada"}
    scope = (chat, route.get("thread_id"), route.get("session_key"))
    proposal = pending.get(scope) if pending is not None else None
    if pending is not None and proposal is not None and monotonic() >= proposal.expires_at:
        del pending[scope]
        proposal = None
    confirming = action == "confirmar_duplicado"
    if confirming:
        if proposal is None or confirmation_code != proposal.code or int(event) <= proposal.event:
            return {"estado": "sin_confirmacion_pendiente",
                    "mensaje": "Ese mensaje no confirma un duplicado pendiente de este chat."
                               " Usá el código exacto de la propuesta vigente."}
        payload = {**proposal.payload, "allow_duplicado": True}
    else:
        if pending is not None and proposal is not None:
            if int(event) == proposal.event:
                return _duplicate_prompt(proposal)
            if int(event) < proposal.event:
                return {"estado": "ignorada", "mensaje": "Hay un pedido de guardado posterior en este chat."}
            del pending[scope]
        data = request.get("receta")
        missing = _missing_fields(data if isinstance(data, dict) else {})
        if missing:
            return {"estado": "faltan_datos", "campos": missing,
                    "mensaje": f"Para guardar la receta, falta: {', '.join(missing)}. "
                               f"Mandame un mensaje nuevo con «{SAVE_HEADER}» en la primera línea "
                               "y la receta completa debajo, incluyendo lo que falta."}
        payload = {k: data[k] for k in ("titulo", "ingredientes", "pasos")}
        payload.update(clave_ingesta=f"telegram:lasso:{chat}:{event}", allow_duplicado=False)
    try:
        recipe = save(payload)
    except ApiError as exc:
        if (not confirming and exc.status == 409 and isinstance(exc.body, dict)
                and exc.body.get("code") == "receta_duplicada" and pending is not None):
            if len(pending) >= 128:
                pending.pop(next(iter(pending)))
            proposal = _Proposal(int(event), deepcopy(payload), token_hex(8), monotonic() + PENDING_TTL)
            pending[scope] = proposal
            return _duplicate_prompt(proposal)
        if exc.status in (400, 413, 422):
            return {"estado": "receta_invalida", "mensaje": "La API rechazó el formato de la receta. Revisá los campos."}
        return {"estado": "error_api", "mensaje": "No pude verificar el guardado. No lo des por confirmado."}
    except (CliError, OSError):
        return {"estado": "error_api", "mensaje": "No pude verificar el guardado. No lo des por confirmado."}
    if confirming and pending is not None:
        pending.pop(scope, None)
    return {"estado": "guardada", "receta": recipe, "mensaje": _saved_message(recipe)}
