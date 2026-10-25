"""Tests de la extensión Telegram (brief S2/S3, T1/T2/T6 de CTO-DISENO.md).

Cubre: migraciones aditivas e idempotentes sobre una base vieja, borradores
independientes por `(chat_id, usuario)`, las rutas `*/telegram`, el dedupe
de comprobantes y los umbrales de aviso de crédito. Todo contra SQLite
efímera (`:memory:` o archivos temporales); nunca contra la base real.
"""

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

import pytest

import db
from tests.test_api import WsgiApiTestCase


# --- T1: migraciones a nivel db.py ------------------------------------------


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def test_migracion_estado_conversacional_idempotente_sobre_base_vieja():
    """Simula una base vieja con el esquema previo de `estado_conversacional`
    (`UNIQUE(telegram_chat_id)` solo, t_65096083) y filas ya cargadas: la
    migración debe recrear la tabla preservando esas filas, agregar la
    UNIQUE compuesta, y una segunda corrida debe ser un no-op.
    """
    vieja = db.get_connection(":memory:")
    try:
        vieja.execute(
            """
            CREATE TABLE estado_conversacional (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_chat_id TEXT NOT NULL UNIQUE,
                usuario TEXT,
                intent_detectado TEXT NOT NULL DEFAULT 'gasto',
                payload_parcial TEXT,
                campo_pendiente TEXT,
                mensaje_original TEXT,
                estado TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        vieja.execute(
            """
            INSERT INTO estado_conversacional
                (telegram_chat_id, usuario, payload_parcial, estado, created_at, updated_at)
            VALUES ('chat-legacy', 'JD', '{"monto": 100}', 'esperando_confirmacion',
                    '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """
        )
        vieja.commit()

        assert db._estado_conversacional_tiene_unique_compuesto(vieja) is False

        db._migrar_estado_conversacional(vieja)  # primera corrida

        assert db._estado_conversacional_tiene_unique_compuesto(vieja) is True
        fila = vieja.execute(
            "SELECT * FROM estado_conversacional WHERE telegram_chat_id = 'chat-legacy'"
        ).fetchone()
        assert fila["usuario"] == "JD"
        assert fila["estado"] == "esperando_confirmacion"

        db._migrar_estado_conversacional(vieja)  # segunda corrida: idempotente
        filas = vieja.execute("SELECT * FROM estado_conversacional").fetchall()
        assert len(filas) == 1
    finally:
        vieja.close()


def test_migracion_columnas_telegram_gastos_e_ingresos_idempotente():
    """`gastos.telegram_user_id`/`telegram_message_id` e
    `ingresos.chat_id`/`telegram_user_id`/`telegram_message_id` se agregan
    vía `ALTER TABLE ADD COLUMN` sin perder datos existentes, y correr la
    migración dos veces es un no-op."""
    vieja = db.get_connection(":memory:")
    try:
        vieja.execute(
            """
            CREATE TABLE gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL, monto REAL NOT NULL,
                moneda TEXT NOT NULL DEFAULT 'ARS', categoria TEXT, subcategoria TEXT,
                medio_pago TEXT, pagado_por TEXT NOT NULL DEFAULT 'Común',
                descripcion_original TEXT, origen TEXT NOT NULL DEFAULT 'texto',
                confirmado INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                chat_id TEXT
            )
            """
        )
        vieja.execute(
            "INSERT INTO gastos (fecha, monto, created_at, chat_id) "
            "VALUES ('2026-01-01', 100.0, '2026-01-01T00:00:00', 'chat-1')"
        )
        vieja.execute(
            """
            CREATE TABLE ingresos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL, monto REAL NOT NULL,
                moneda TEXT NOT NULL DEFAULT 'ARS', categoria TEXT NOT NULL,
                persona TEXT NOT NULL, descripcion_original TEXT,
                origen TEXT NOT NULL DEFAULT 'texto',
                confirmado INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            )
            """
        )
        vieja.execute(
            "INSERT INTO ingresos (fecha, monto, categoria, persona, created_at) "
            "VALUES ('2026-01-01', 500.0, 'Salario', 'JD', '2026-01-01T00:00:00')"
        )
        vieja.commit()

        for _ in range(2):  # idempotente
            db._migrar_columnas_gastos(vieja)
            db._migrar_columnas_ingresos(vieja)

        columnas_gastos = db._column_names(vieja, "gastos")
        assert {"telegram_user_id", "telegram_message_id"} <= columnas_gastos
        columnas_ingresos = db._column_names(vieja, "ingresos")
        assert {"chat_id", "telegram_user_id", "telegram_message_id"} <= columnas_ingresos

        gasto = vieja.execute("SELECT * FROM gastos").fetchone()
        assert gasto["monto"] == 100.0
        assert gasto["chat_id"] == "chat-1"
        assert gasto["telegram_user_id"] is None
        ingreso = vieja.execute("SELECT * FROM ingresos").fetchone()
        assert ingreso["monto"] == 500.0
        assert ingreso["chat_id"] is None
    finally:
        vieja.close()


# --- T1: dos usuarios del mismo chat con borradores independientes --------


def test_dos_usuarios_mismo_chat_borradores_independientes(conn):
    assert db.get_estado(conn, "chat-9", usuario="JD") is None
    assert db.get_estado(conn, "chat-9", usuario="Pinki") is None

    db.set_estado(
        conn, "chat-9", estado="esperando_campo", campo_pendiente="monto",
        payload_parcial={"categoria": "Comida"}, usuario="JD",
    )
    db.set_estado(
        conn, "chat-9", estado="esperando_confirmacion",
        payload_parcial={"categoria": "Transporte", "monto": 500}, usuario="Pinki",
    )

    jd = db.get_estado(conn, "chat-9", usuario="JD")
    pinki = db.get_estado(conn, "chat-9", usuario="Pinki")
    assert jd["estado"] == "esperando_campo"
    assert jd["payload_parcial"] == {"categoria": "Comida"}
    assert pinki["estado"] == "esperando_confirmacion"
    assert pinki["payload_parcial"] == {"categoria": "Transporte", "monto": 500}

    # Actualizar el de JD no debe tocar el de Pinki.
    db.set_estado(conn, "chat-9", estado="completado", usuario="JD")
    assert db.get_estado(conn, "chat-9", usuario="JD")["estado"] == "completado"
    assert db.get_estado(conn, "chat-9", usuario="Pinki")["estado"] == "esperando_confirmacion"

    # Borrar el de JD no debe tocar el de Pinki.
    db.clear_estado(conn, "chat-9", usuario="JD")
    assert db.get_estado(conn, "chat-9", usuario="JD") is None
    assert db.get_estado(conn, "chat-9", usuario="Pinki") is not None

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM estado_conversacional WHERE telegram_chat_id = 'chat-9'"
    ).fetchone()
    assert rows["n"] == 1


def test_estado_sin_usuario_sigue_funcionando_como_antes(conn):
    """Compatibilidad con el comportamiento previo a la migración: un
    `chat_id` sin `usuario` explícito (`None`) sigue teniendo un único
    borrador, igual que `tests/test_db.py`."""
    assert db.get_estado(conn, "chat-legacy") is None
    db.set_estado(conn, "chat-legacy", estado="esperando_campo", campo_pendiente="monto")
    db.set_estado(conn, "chat-legacy", estado="esperando_confirmacion")
    estado = db.get_estado(conn, "chat-legacy")
    assert estado["estado"] == "esperando_confirmacion"
    assert estado["campo_pendiente"] is None
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM estado_conversacional WHERE telegram_chat_id = 'chat-legacy'"
    ).fetchone()
    assert rows["n"] == 1
    db.clear_estado(conn, "chat-legacy")
    assert db.get_estado(conn, "chat-legacy") is None


# --- T1: total_credito_mes / detectar_umbrales_credito ---------------------


def _gasto_credito(**overrides):
    gasto = {
        "fecha": "2026-04-10", "monto": 100.0, "categoria": "Hogar",
        "medio_pago": "Crédito", "confirmado": True,
    }
    gasto.update(overrides)
    return gasto


def test_total_credito_mes_solo_cuenta_credito_no_borrado_del_mes(conn):
    db.insert_gasto(conn, _gasto_credito(monto=1000.0, fecha="2026-04-05"))
    db.insert_gasto(conn, _gasto_credito(monto=2000.0, fecha="2026-04-20"))
    # No-Crédito no cuenta.
    db.insert_gasto(conn, _gasto_credito(monto=5000.0, fecha="2026-04-15", medio_pago="Efectivo"))
    # Otro mes no cuenta.
    db.insert_gasto(conn, _gasto_credito(monto=9999.0, fecha="2026-05-01"))
    # Borrado no cuenta.
    borrado_id = db.insert_gasto(conn, _gasto_credito(monto=4000.0, fecha="2026-04-12"))
    db.eliminar_gasto_logico(conn, borrado_id, actor="test")

    assert db.total_credito_mes(conn, "2026-04") == 3000.0


def test_detectar_umbrales_credito_cruce_simple(conn):
    db.insert_gasto(conn, _gasto_credito(monto=100000.0, fecha="2026-04-10"))
    resultado = db.detectar_umbrales_credito(conn, "2026-04")
    assert resultado["total"] == 100000.0
    assert resultado["nuevos"] == [{"mes": "2026-04", "umbral": 100000, "total": 100000.0}]

    pendientes = db.avisos_credito_pendientes(conn)
    assert len(pendientes) == 1
    assert pendientes[0]["umbral"] == 100000
    assert pendientes[0]["enviado_en"] is None


def test_detectar_umbrales_credito_decimales_cruzan_exacto_100k(conn):
    """Hallazgo 1 del revisor run 65c69e0c: sumar `monto` como `REAL` directo
    puede dar `99999.99999999999` en vez de `100000.00` para estos tres
    importes (353,34 + 72.252,93 + 27.393,73 = 100.000,00 exacto), omitiendo
    el umbral. Con la suma en centavos enteros, el umbral se detecta."""
    db.insert_gasto(conn, _gasto_credito(monto=353.34, fecha="2026-04-10"))
    db.insert_gasto(conn, _gasto_credito(monto=72252.93, fecha="2026-04-11"))
    db.insert_gasto(conn, _gasto_credito(monto=27393.73, fecha="2026-04-12"))

    resultado = db.detectar_umbrales_credito(conn, "2026-04")
    assert resultado["total"] == 100000.0
    assert [item["umbral"] for item in resultado["nuevos"]] == [100000]


def test_detectar_umbrales_credito_decimales_cruzan_exacto_150k(conn):
    """Mismo caso que el anterior, extendido para cruzar también el umbral
    de $150.000 con otros dos importes decimales (18.765,43 + 31.234,57 =
    50.000,00 exacto)."""
    db.insert_gasto(conn, _gasto_credito(monto=353.34, fecha="2026-04-10"))
    db.insert_gasto(conn, _gasto_credito(monto=72252.93, fecha="2026-04-11"))
    db.insert_gasto(conn, _gasto_credito(monto=27393.73, fecha="2026-04-12"))
    db.insert_gasto(conn, _gasto_credito(monto=18765.43, fecha="2026-04-13"))
    db.insert_gasto(conn, _gasto_credito(monto=31234.57, fecha="2026-04-14"))

    resultado = db.detectar_umbrales_credito(conn, "2026-04")
    assert resultado["total"] == 150000.0
    assert [item["umbral"] for item in resultado["nuevos"]] == [100000, 150000]


def test_detectar_umbrales_credito_varios_de_golpe(conn):
    db.insert_gasto(conn, _gasto_credito(monto=80000.0, fecha="2026-04-10"))
    assert db.detectar_umbrales_credito(conn, "2026-04")["nuevos"] == []

    db.insert_gasto(conn, _gasto_credito(monto=130000.0, fecha="2026-04-12"))
    resultado = db.detectar_umbrales_credito(conn, "2026-04")
    assert resultado["total"] == 210000.0
    assert [item["umbral"] for item in resultado["nuevos"]] == [100000, 150000, 200000]


def test_detectar_umbrales_credito_baja_no_desregistra_y_resuba_no_repite(conn):
    gasto_id = db.insert_gasto(conn, _gasto_credito(monto=150000.0, fecha="2026-04-10"))
    primero = db.detectar_umbrales_credito(conn, "2026-04")
    assert [item["umbral"] for item in primero["nuevos"]] == [100000, 150000]

    db.eliminar_gasto_logico(conn, gasto_id, actor="test")
    assert db.total_credito_mes(conn, "2026-04") == 0.0
    tras_baja = db.detectar_umbrales_credito(conn, "2026-04")
    assert tras_baja["nuevos"] == []  # no se "desnotifica"

    pendientes_tras_baja = db.avisos_credito_pendientes(conn)
    assert {p["umbral"] for p in pendientes_tras_baja} == {100000, 150000}

    # Vuelve a subir y cruza el mismo umbral ya registrado: no se repite.
    db.insert_gasto(conn, _gasto_credito(monto=150000.0, fecha="2026-04-15"))
    tras_resuba = db.detectar_umbrales_credito(conn, "2026-04")
    assert tras_resuba["nuevos"] == []

    # Pero un umbral NUEVO (no registrado antes) sí se detecta.
    db.insert_gasto(conn, _gasto_credito(monto=60000.0, fecha="2026-04-16"))
    tras_nuevo_umbral = db.detectar_umbrales_credito(conn, "2026-04")
    assert [item["umbral"] for item in tras_nuevo_umbral["nuevos"]] == [200000]


def test_detectar_umbrales_credito_cuotas_en_meses_distintos_y_mes_calendario(conn):
    db.insert_gasto_con_cuotas(
        conn,
        _gasto_credito(monto=300000.0, fecha="2026-04-28"),
        cuotas_total=3,
    )
    # Cada cuota cae en un mes distinto (abril, mayo, junio); cada una es
    # ~100000, por mes calendario de su propia fecha (no de la fecha del
    # gasto original).
    assert db.total_credito_mes(conn, "2026-04") == pytest.approx(100000.0)
    assert db.total_credito_mes(conn, "2026-05") == pytest.approx(100000.0)
    assert db.total_credito_mes(conn, "2026-06") == pytest.approx(100000.0)

    abril = db.detectar_umbrales_credito(conn, "2026-04")
    mayo = db.detectar_umbrales_credito(conn, "2026-05")
    assert [item["umbral"] for item in abril["nuevos"]] == [100000]
    assert [item["umbral"] for item in mayo["nuevos"]] == [100000]


def test_marcar_avisos_credito_enviados_es_idempotente(conn):
    db.insert_gasto(conn, _gasto_credito(monto=150000.0, fecha="2026-04-10"))
    db.detectar_umbrales_credito(conn, "2026-04")

    actualizados = db.marcar_avisos_credito_enviados(
        conn, [{"mes": "2026-04", "umbral": 100000}, {"mes": "2026-04", "umbral": 999999}],
    )
    assert actualizados == [{"mes": "2026-04", "umbral": 100000}]

    pendientes = db.avisos_credito_pendientes(conn)
    assert [p["umbral"] for p in pendientes] == [150000]

    # Reintentar el mismo lote no vuelve a contarlo (ya estaba marcado).
    otra_vez = db.marcar_avisos_credito_enviados(conn, [{"mes": "2026-04", "umbral": 100000}])
    assert otra_vez == []


# --- T1: dedupe de comprobantes ---------------------------------------------


def test_buscar_comprobante_dedupe_hash_y_aproximado(conn):
    gasto_id = db.insert_gasto(conn, {
        "fecha": "2026-04-10", "monto": 1500.0, "categoria": "Comida",
        "confirmado": True,
    })
    db._insert_comprobante_tx(
        conn,
        {
            "hash_archivo": "hash-abc", "monto_detectado": 1500.0,
            "fecha_detectada": "2026-04-10", "comercio_detectado": "Super",
        },
        gasto_id=gasto_id,
    )
    conn.commit()

    exacto = db.buscar_comprobante_dedupe(conn, "hash-abc")
    assert exacto == {
        "duplicado": True, "gasto_id": gasto_id, "ingreso_id": None, "coincidencia": "hash",
    }


def test_buscar_comprobante_dedupe_aproximado_limite_centavos(conn):
    """Bordes exactos de la tolerancia ±0,01 (hallazgo 2 del revisor run
    65c69e0c): comprobante guardado en 1,02, consultado contra 1,01
    (diferencia exacta 0,01 -> duplicado) y contra 1,00 (diferencia exacta
    0,02 -> no duplicado). `ABS(monto_detectado - ?) <= 0.01` en floats
    daba `0.010000000000000009` para el primer caso y lo descartaba."""
    db._insert_comprobante_tx(
        conn,
        {
            "hash_archivo": "hash-102", "monto_detectado": 1.02,
            "fecha_detectada": "2026-04-10", "comercio_detectado": None,
        },
    )
    conn.commit()

    dentro = db.buscar_comprobante_dedupe(conn, "hash-otro-1", monto=1.01, fecha="2026-04-10")
    assert dentro["duplicado"] is True
    assert dentro["coincidencia"] == "aproximada"

    fuera = db.buscar_comprobante_dedupe(conn, "hash-otro-2", monto=1.00, fecha="2026-04-10")
    assert fuera == {
        "duplicado": False, "gasto_id": None, "ingreso_id": None, "coincidencia": None,
    }


def test_buscar_comprobante_dedupe_aproximado_limite_centavos_sentido_inverso(conn):
    """Mismo límite que el test anterior, invertido: comprobante guardado en
    1,01, consultado contra 1,02 (duplicado) y contra 1,03 (no duplicado)."""
    db._insert_comprobante_tx(
        conn,
        {
            "hash_archivo": "hash-101", "monto_detectado": 1.01,
            "fecha_detectada": "2026-04-10", "comercio_detectado": None,
        },
    )
    conn.commit()

    dentro = db.buscar_comprobante_dedupe(conn, "hash-otro-3", monto=1.02, fecha="2026-04-10")
    assert dentro["duplicado"] is True
    assert dentro["coincidencia"] == "aproximada"

    fuera = db.buscar_comprobante_dedupe(conn, "hash-otro-4", monto=1.03, fecha="2026-04-10")
    assert fuera == {
        "duplicado": False, "gasto_id": None, "ingreso_id": None, "coincidencia": None,
    }


def test_insert_comprobante_duplicado_levanta_error_sin_insertar(conn):
    gasto_id = db.insert_gasto(conn, {
        "fecha": "2026-04-10", "monto": 100.0, "categoria": "Hogar", "confirmado": True,
    })
    db._insert_comprobante_tx(conn, {"hash_archivo": "hash-x"}, gasto_id=gasto_id)
    conn.commit()
    with pytest.raises(db.ComprobanteDuplicadoError):
        db._insert_comprobante_tx(conn, {"hash_archivo": "hash-x"}, gasto_id=gasto_id)
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM comprobantes_telegram WHERE hash_archivo = 'hash-x'"
    ).fetchone()["n"]
    assert total == 1


# --- t_a3f2bbb5: dedupe por nro_operacion + migración idempotente ----------


def test_migracion_columna_nro_operacion_idempotente_sobre_base_vieja():
    """Simula una base vieja con `comprobantes_telegram` sin `nro_operacion`
    (esquema previo a t_a3f2bbb5) y filas ya cargadas: la migración agrega
    la columna y el índice único parcial sin tocar los datos existentes, y
    correrla dos veces es un no-op."""
    vieja = db.get_connection(":memory:")
    try:
        vieja.execute(
            """
            CREATE TABLE comprobantes_telegram (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_archivo TEXT NOT NULL UNIQUE,
                chat_id TEXT, telegram_user_id TEXT, telegram_message_id TEXT,
                texto_extraido TEXT, monto_detectado REAL, fecha_detectada TEXT,
                comercio_detectado TEXT, ruta_archivo TEXT,
                gasto_id INTEGER, ingreso_id INTEGER, creado_en TEXT NOT NULL
            )
            """
        )
        vieja.execute(
            "INSERT INTO comprobantes_telegram (hash_archivo, creado_en) "
            "VALUES ('hash-legacy', '2026-01-01T00:00:00')"
        )
        vieja.commit()

        assert "nro_operacion" not in db._column_names(vieja, "comprobantes_telegram")

        for _ in range(2):  # idempotente
            db._migrar_columnas_comprobantes_telegram(vieja)

        assert "nro_operacion" in db._column_names(vieja, "comprobantes_telegram")
        fila = vieja.execute(
            "SELECT * FROM comprobantes_telegram WHERE hash_archivo = 'hash-legacy'"
        ).fetchone()
        assert fila["nro_operacion"] is None
    finally:
        vieja.close()


def test_indice_unico_parcial_nro_operacion_permite_varios_null(conn):
    """El índice único es PARCIAL (`WHERE nro_operacion IS NOT NULL`):
    varios comprobantes sin número de operación conviven sin problema,
    pero dos con el MISMO número de operación chocan."""
    db._insert_comprobante_tx(conn, {"hash_archivo": "hash-sin-op-1"})
    db._insert_comprobante_tx(conn, {"hash_archivo": "hash-sin-op-2"})
    conn.commit()

    db._insert_comprobante_tx(conn, {"hash_archivo": "hash-op-1", "nro_operacion": "173192245876"})
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO comprobantes_telegram (hash_archivo, nro_operacion, creado_en) "
            "VALUES ('hash-op-2', '173192245876', '2026-01-01T00:00:00')"
        )


def test_buscar_comprobante_dedupe_por_nro_operacion(conn):
    db._insert_comprobante_tx(conn, {"hash_archivo": "hash-op-x", "nro_operacion": "173192245876"})
    conn.commit()

    exacto = db.buscar_comprobante_dedupe(conn, "otro-hash", nro_operacion="173192245876")
    assert exacto["duplicado"] is True
    assert exacto["coincidencia"] == "operacion"

    sin_match = db.buscar_comprobante_dedupe(conn, "otro-hash-2", nro_operacion="000000000")
    assert sin_match == {
        "duplicado": False, "gasto_id": None, "ingreso_id": None, "coincidencia": None,
    }


def test_buscar_comprobante_dedupe_nro_operacion_tiene_prioridad_sobre_aproximada(conn):
    """Un comprobante con el mismo número de operación es duplicado aunque
    monto/fecha no coincidan -- la coincidencia por operación se prueba
    ANTES que la aproximada (más fuerte: un número de operación bancaria es
    inequívoco, un monto+fecha parecidos no tanto)."""
    db._insert_comprobante_tx(
        conn,
        {
            "hash_archivo": "hash-op-y", "monto_detectado": 27000.0,
            "fecha_detectada": "2026-08-11", "nro_operacion": "173192245876",
        },
    )
    conn.commit()

    resultado = db.buscar_comprobante_dedupe(
        conn, "otro-hash", monto=9999.0, fecha="2026-09-01", nro_operacion="173192245876",
    )
    assert resultado["duplicado"] is True
    assert resultado["coincidencia"] == "operacion"


# --- T2: rutas HTTP /telegram ------------------------------------------------


class TelegramApiTest(WsgiApiTestCase):
    def setUp(self):
        super().setUp()
        with db.get_connection(self.db_path) as conn:
            db.insert_tarjeta(conn, {
                "id": "TC1", "nombre": "Visa", "tipo": "Crédito", "titular": "JD",
            })

    def expense_telegram(self, **changes):
        payload = self.expense()
        payload.update({
            "chat_id": "-5500256401", "telegram_user_id": "7355824354",
            "telegram_message_id": "42", "medio_pago": "Efectivo", "confirmado": True,
        })
        payload.update(changes)
        if payload.get("medio_pago") in ("Crédito", "Débito") and "tarjeta_id" not in changes:
            payload["tarjeta_id"] = "TC1"
        return payload

    def income_telegram(self, **changes):
        payload = self.income()
        payload.update({
            "chat_id": "-5500256401", "telegram_user_id": "7355824354",
            "telegram_message_id": "43", "confirmado": True,
        })
        payload.update(changes)
        return payload

    def comprobante(self, **changes):
        payload = {
            "hash_archivo": "hash-1", "texto_extraido": "Super $1500",
            "monto_detectado": 1500.0, "fecha_detectada": "2026-04-10",
            "comercio_detectado": "Super",
        }
        payload.update(changes)
        return payload

    def test_create_expense_telegram_sets_origen_and_ids(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram", self.expense_telegram(),
        )
        self.assertEqual(status, 201)
        gasto = body["expenses"][0]
        self.assertEqual(gasto["origen"], "telegram")
        self.assertEqual(gasto["chat_id"], "-5500256401")
        self.assertEqual(gasto["telegram_user_id"], "7355824354")
        self.assertEqual(gasto["telegram_message_id"], "42")
        self.assertEqual(body["avisos_credito_nuevos"], [])
        self.assertNotIn("comprobante", body)

    def test_telegram_rechaza_campos_obligatorios_sin_escribir(self):
        cases = [
            ("/api/expenses/telegram", self.expense_telegram(), "confirmado"),
            ("/api/expenses/telegram", self.expense_telegram(), "pagado_por"),
            ("/api/expenses/telegram", self.expense_telegram(), "fecha"),
            ("/api/expenses/telegram", self.expense_telegram(), "medio_pago"),
            ("/api/expenses/telegram", self.expense_telegram(medio_pago="Crédito"), "tarjeta_id"),
            ("/api/income/telegram", self.income_telegram(), "confirmado"),
            ("/api/income/telegram", self.income_telegram(), "fecha"),
            ("/api/income/telegram", self.income_telegram(), "persona"),
        ]
        for route, payload, field in cases:
            with self.subTest(route=route, field=field):
                payload.pop(field)
                with db.get_connection(self.db_path) as conn:
                    before = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                                   for table in ("gastos", "ingresos", "comprobantes_telegram"))
                self.assertEqual(self.request("POST", route, payload)[0], 400)
                with db.get_connection(self.db_path) as conn:
                    after = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                                  for table in ("gastos", "ingresos", "comprobantes_telegram"))
                self.assertEqual(after, before)
        for value in (False, 1, None):
            with self.subTest(confirmado=value):
                self.assertEqual(self.request("POST", "/api/expenses/telegram", self.expense_telegram(confirmado=value))[0], 400)
                self.assertEqual(self.request("POST", "/api/income/telegram", self.income_telegram(confirmado=value))[0], 400)

    def test_telegram_cuotas_estrictas(self):
        for value in (2.9, True, 0, 121):
            with self.subTest(value=value):
                self.assertEqual(self.request("POST", "/api/expenses/telegram", self.expense_telegram(cuotas_total=value))[0], 400)
        for value in (1, 3, 120):
            with self.subTest(value=value):
                status, body, _ = self.request("POST", "/api/expenses/telegram", self.expense_telegram(cuotas_total=value, monto=120))
                self.assertEqual(status, 201)
                self.assertEqual(len(body["expenses"]), value)

    def test_telegram_120_cuotas_conserva_total_fechas_y_atomicidad(self):
        payload = self.expense_telegram(cuotas_total=120, monto=120)
        status, body, _ = self.request("POST", "/api/expenses/telegram", payload)
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual(len(rows), 120)
        self.assertEqual([row["cuota_nro"] for row in rows], list(range(1, 121)))
        self.assertEqual({row["cuotas_total"] for row in rows}, {120})
        self.assertEqual({row["cuota_ref"] for row in rows}, {rows[0]["id"]})
        self.assertEqual(
            [row["fecha"] for row in rows],
            [f"{2026 + (3 + offset) // 12:04d}-{(3 + offset) % 12 + 1:02d}-10"
             for offset in range(120)],
        )
        self.assertEqual([round(row["monto"] * 100) for row in rows], [100] * 120)
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 12000)

        with db.get_connection(self.db_path) as conn:
            before = conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]
            comprobantes_before = conn.execute(
                "SELECT COUNT(*) FROM comprobantes_telegram"
            ).fetchone()[0]
            stored = conn.execute(
                "SELECT id, monto, fecha, cuota_nro FROM gastos ORDER BY id"
            ).fetchall()
        self.assertEqual(before, 120)
        self.assertEqual([row["id"] for row in stored], [row["id"] for row in rows])
        self.assertEqual(
            [(row["monto"], row["fecha"], row["cuota_nro"]) for row in stored],
            [(row["monto"], row["fecha"], row["cuota_nro"]) for row in rows],
        )

        # El monto original no alcanza para dar al menos un centavo a cada cuota.
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(
                cuotas_total=120, monto=1.19,
                comprobante=self.comprobante(hash_archivo="invalid-120"),
            ),
        )
        self.assertEqual(status, 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], before)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM comprobantes_telegram").fetchone()[0],
                comprobantes_before,
            )

    def test_telegram_installments_minimum_cent_and_indivisible_total(self):
        """Mismo contrato de reparto que la ruta web (`test_api.py`): usa el
        helper único `db._repartir_cuotas_centavos`, así que debe aceptar
        0,01/1, rechazar 0,01/2 sin escrituras, y repartir 0,08/5 en centavos
        enteros positivos (dictamen NO APTO e46265bb)."""
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=0.01, cuotas_total=1),
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(body["expenses"]), 1)
        self.assertEqual(round(body["expenses"][0]["monto"] * 100), 1)

        with db.get_connection(self.db_path) as conn:
            before = conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=0.01, cuotas_total=2),
        )
        self.assertEqual(status, 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], before)

        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=0.08, cuotas_total=5),
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual([round(row["monto"] * 100) for row in rows], [2, 2, 2, 1, 1])
        self.assertTrue(all(row["monto"] > 0 for row in rows))
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 8)

    def test_telegram_120_cuotas_revierte_todas_ante_comprobante_duplicado(self):
        comprobante = self.comprobante()
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(comprobante=comprobante),
        )
        self.assertEqual(status, 201)
        with db.get_connection(self.db_path) as conn:
            before = conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]

        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(cuotas_total=120, monto=120, comprobante=comprobante),
        )
        self.assertEqual(status, 409)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], before)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM comprobantes_telegram").fetchone()[0], 1,
            )

    def test_create_expense_telegram_rejects_client_origen_and_unknown_fields(self):
        self.assertEqual(
            self.request("POST", "/api/expenses/telegram", self.expense_telegram(origen="otro"))[0],
            400,
        )
        self.assertEqual(
            self.request("POST", "/api/expenses/telegram", self.expense_telegram(actor="JD"))[0],
            400,
        )

    def test_create_expense_telegram_validates_telegram_ids(self):
        for bad_id in ("abc", "12-34", "", "1" * 40):
            with self.subTest(bad_id=bad_id):
                status, _, _ = self.request(
                    "POST", "/api/expenses/telegram",
                    self.expense_telegram(telegram_user_id=bad_id),
                )
                self.assertEqual(status, 400)
        # Chat id negativo (grupo) es válido.
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram", self.expense_telegram(chat_id="-123"),
        )
        self.assertEqual(status, 201)

    def test_create_expense_telegram_same_validation_as_normal_route(self):
        self.assertEqual(
            self.request("POST", "/api/expenses/telegram", self.expense_telegram(monto=-5))[0],
            400,
        )
        self.assertEqual(
            self.request("POST", "/api/expenses/telegram", self.expense_telegram(categoria=""))[0],
            400,
        )

    def test_create_expense_telegram_rechaza_proporcion_fuera_de_rango(self):
        for proporcion_jd, proporcion_pinki in ((120, -20), (-5, 105)):
            with self.subTest(proporcion_jd=proporcion_jd):
                status, _, _ = self.request(
                    "POST", "/api/expenses/telegram",
                    self.expense_telegram(
                        tipo_proporcion="custom",
                        proporcion_jd=proporcion_jd, proporcion_pinki=proporcion_pinki,
                    ),
                )
                self.assertEqual(status, 400)

    def test_create_expense_telegram_rechaza_proporcion_no_numerica_o_nan(self):
        for proporcion_jd, proporcion_pinki in ((float("nan"), 100), ("50", 50)):
            with self.subTest(proporcion_jd=proporcion_jd):
                status, _, _ = self.request(
                    "POST", "/api/expenses/telegram",
                    self.expense_telegram(
                        tipo_proporcion="custom",
                        proporcion_jd=proporcion_jd, proporcion_pinki=proporcion_pinki,
                    ),
                )
                self.assertEqual(status, 400)

    def test_create_expense_telegram_acepta_proporcion_personal_100_0(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(tipo_proporcion="custom", proporcion_jd=100, proporcion_pinki=0),
        )
        self.assertEqual(status, 201)
        gasto = body["expenses"][0]
        self.assertEqual((gasto["proporcion_jd"], gasto["proporcion_pinki"]), (100, 0))

    def test_create_expense_telegram_with_installments(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram", self.expense_telegram(cuotas_total=3, monto=300),
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["chat_id"] for row in rows}, {"-5500256401"})
        self.assertEqual({row["cuota_ref"] for row in rows}, {rows[0]["id"]})

    def test_create_expense_telegram_with_comprobante_same_transaction(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(comprobante=self.comprobante()),
        )
        self.assertEqual(status, 201)
        self.assertIn("comprobante", body)
        self.assertEqual(body["comprobante"]["hash_archivo"], "hash-1")
        self.assertEqual(body["comprobante"]["gasto_id"], body["expenses"][0]["id"])

        # Hash duplicado: 409, no crea nada nuevo (ni gasto ni comprobante).
        with db.get_connection(self.db_path) as conn:
            antes = conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(comprobante=self.comprobante()),
        )
        self.assertEqual(status, 409)
        with db.get_connection(self.db_path) as conn:
            despues = conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]
            comprobantes = conn.execute(
                "SELECT COUNT(*) FROM comprobantes_telegram WHERE hash_archivo = 'hash-1'"
            ).fetchone()[0]
        self.assertEqual(despues, antes)
        self.assertEqual(comprobantes, 1)

    def test_create_expense_telegram_credit_threshold_in_response(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=150000, medio_pago="Crédito"),
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            [a["umbral"] for a in body["avisos_credito_nuevos"]], [100000, 150000],
        )

    def test_create_income_telegram_sets_origen_and_ids(self):
        status, body, _ = self.request(
            "POST", "/api/income/telegram", self.income_telegram(),
        )
        self.assertEqual(status, 201)
        ingreso = body["income"]
        self.assertEqual(ingreso["origen"], "telegram")
        self.assertEqual(ingreso["chat_id"], "-5500256401")
        self.assertEqual(ingreso["telegram_user_id"], "7355824354")

    def test_create_income_telegram_with_comprobante_duplicate_hash_409(self):
        status, body, _ = self.request(
            "POST", "/api/income/telegram",
            self.income_telegram(comprobante=self.comprobante(hash_archivo="hash-income")),
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["comprobante"]["ingreso_id"], body["income"]["id"])

        with db.get_connection(self.db_path) as conn:
            antes = conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0]
        status, _, _ = self.request(
            "POST", "/api/income/telegram",
            self.income_telegram(comprobante=self.comprobante(hash_archivo="hash-income")),
        )
        self.assertEqual(status, 409)
        with db.get_connection(self.db_path) as conn:
            despues = conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0]
        self.assertEqual(despues, antes)

    def test_comprobante_conserva_recepcion_original_para_retencion(self):
        received = "2026-08-11T10:00:00+00:00"
        status, body, _ = self.request(
            "POST", "/api/income/telegram",
            self.income_telegram(comprobante=self.comprobante(hash_archivo="received-original", received_at=received)),
        )
        self.assertEqual(status, 201)
        with db.get_connection(self.db_path) as conn:
            row = conn.execute("SELECT creado_en FROM comprobantes_telegram WHERE id = ?", (body["comprobante"]["id"],)).fetchone()
        self.assertEqual(row["creado_en"], received)

    def test_income_operacion_duplicada_y_carrera_de_indice_devuelven_409(self):
        first = self.comprobante(hash_archivo="op-first", nro_operacion="173192245876")
        self.assertEqual(self.request("POST", "/api/income/telegram", self.income_telegram(comprobante=first))[0], 201)
        with db.get_connection(self.db_path) as conn:
            before = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                           for table in ("ingresos", "comprobantes_telegram"))
        second = self.comprobante(hash_archivo="op-second", nro_operacion="173192245876")
        self.assertEqual(self.request("POST", "/api/income/telegram", self.income_telegram(comprobante=second))[0], 409)
        with mock.patch.object(db, "_insert_comprobante_tx", side_effect=sqlite3.IntegrityError("unique race")):
            self.assertEqual(self.request("POST", "/api/income/telegram", self.income_telegram(comprobante=self.comprobante(hash_archivo="race")))[0], 409)
        with db.get_connection(self.db_path) as conn:
            after = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                          for table in ("ingresos", "comprobantes_telegram"))
        self.assertEqual(after, before)

    def test_income_operacion_concurrente_solo_crea_una_fila(self):
        barrier = Barrier(2)

        def send(hash_archivo):
            barrier.wait()
            comprobante = self.comprobante(hash_archivo=hash_archivo, nro_operacion="9000000001")
            return self.request("POST", "/api/income/telegram", self.income_telegram(comprobante=comprobante))[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(send, f"parallel-{index}") for index in range(2)]
            statuses = sorted(future.result() for future in futures)
        self.assertEqual(statuses, [201, 409])
        with db.get_connection(self.db_path) as conn:
            incomes = conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0]
            receipts = conn.execute("SELECT COUNT(*) FROM comprobantes_telegram WHERE nro_operacion = '9000000001'").fetchone()[0]
        self.assertEqual((incomes, receipts), (1, 1))

    def test_create_income_telegram_validation_same_as_normal_route(self):
        self.assertEqual(
            self.request("POST", "/api/income/telegram", self.income_telegram(persona="Común"))[0],
            400,
        )

    def test_telegram_routes_require_auth(self):
        self.assertEqual(
            self.request("POST", "/api/expenses/telegram", self.expense_telegram(), auth=False)[0],
            401,
        )
        self.assertEqual(
            self.request("POST", "/api/income/telegram", self.income_telegram(), auth=False)[0],
            401,
        )
        self.assertEqual(self.request("GET", "/api/tarjetas", auth=False)[0], 401)
        self.assertEqual(
            self.request("GET", "/api/comprobantes/dedupe?hash=x", auth=False)[0], 401,
        )

    def test_list_tarjetas(self):
        with db.get_connection(self.db_path) as conn:
            db.insert_tarjeta(conn, {
                "id": "TC2", "nombre": "Mastercard", "tipo": "Crédito", "titular": "JD",
            })
        status, body, _ = self.request("GET", "/api/tarjetas")
        self.assertEqual(status, 200)
        self.assertEqual({t["id"] for t in body["tarjetas"]}, {"TC1", "TC2"})

    def test_comprobantes_dedupe_route(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(comprobante=self.comprobante(hash_archivo="hash-dedupe")),
        )
        self.assertEqual(status, 201)

        status, body, _ = self.request("GET", "/api/comprobantes/dedupe?hash=hash-dedupe")
        self.assertEqual(status, 200)
        self.assertEqual(body["duplicado"], True)
        self.assertEqual(body["coincidencia"], "hash")

        status, body, _ = self.request("GET", "/api/comprobantes/dedupe?hash=otro-hash")
        self.assertEqual(status, 200)
        self.assertEqual(body["duplicado"], False)

        status, body, _ = self.request(
            "GET", "/api/comprobantes/dedupe?hash=otro-hash&monto=1500&fecha=2026-04-11&comercio=Super",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["coincidencia"], "aproximada")

        self.assertEqual(self.request("GET", "/api/comprobantes/dedupe")[0], 400)

    def test_comprobantes_dedupe_por_nro_operacion(self):
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(
                comprobante=self.comprobante(hash_archivo="hash-con-operacion", nro_operacion="173192245876"),
            ),
        )
        self.assertEqual(status, 201)

        status, body, _ = self.request(
            "GET", "/api/comprobantes/dedupe?hash=otro-hash&nro_operacion=173192245876",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["duplicado"], True)
        self.assertEqual(body["coincidencia"], "operacion")

        status, body, _ = self.request(
            "GET", "/api/comprobantes/dedupe?hash=otro-hash&nro_operacion=000000000",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["duplicado"], False)

        self.assertEqual(
            self.request("GET", "/api/comprobantes/dedupe?hash=x&nro_operacion=abc")[0], 400,
        )

    def test_create_expense_telegram_con_nro_operacion_queda_en_el_comprobante(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(
                comprobante=self.comprobante(hash_archivo="hash-op-guardado", nro_operacion="173192245876"),
            ),
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["comprobante"]["nro_operacion"], "173192245876")

        self.assertEqual(
            self.request(
                "POST", "/api/expenses/telegram",
                self.expense_telegram(
                    comprobante=self.comprobante(hash_archivo="hash-otro", nro_operacion="abc"),
                ),
            )[0],
            400,
        )

    def test_avisos_credito_pendientes_y_marcar_enviados(self):
        status, _, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=150000, medio_pago="Crédito"),
        )
        self.assertEqual(status, 201)

        status, body, _ = self.request("GET", "/api/avisos-credito/pendientes")
        self.assertEqual(status, 200)
        umbrales = {a["umbral"] for a in body["avisos_credito"]}
        self.assertEqual(umbrales, {100000, 150000})

        status, body, _ = self.request(
            "POST", "/api/avisos-credito/marcar-enviados",
            {"items": [{"mes": "2026-04", "umbral": 100000}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["actualizados"], [{"mes": "2026-04", "umbral": 100000}])

        status, body, _ = self.request("GET", "/api/avisos-credito/pendientes")
        self.assertEqual([a["umbral"] for a in body["avisos_credito"]], [150000])

        # Reintentar un item ya marcado no rompe nada y no lo re-cuenta.
        status, body, _ = self.request(
            "POST", "/api/avisos-credito/marcar-enviados",
            {"items": [{"mes": "2026-04", "umbral": 100000}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["actualizados"], [])

    def test_avisos_credito_marcar_enviados_validates_items(self):
        self.assertEqual(
            self.request("POST", "/api/avisos-credito/marcar-enviados", {"items": []})[0], 400,
        )
        self.assertEqual(
            self.request(
                "POST", "/api/avisos-credito/marcar-enviados",
                {"items": [{"mes": "2026-04"}]},
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "POST", "/api/avisos-credito/marcar-enviados",
                {"items": [{"mes": "2026-4", "umbral": 100000}]},
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "POST", "/api/avisos-credito/marcar-enviados",
                {"items": [{"mes": "2026-04", "umbral": -1}]},
            )[0],
            400,
        )

    def test_delete_expense_credit_includes_avisos_credito_nuevos(self):
        status, body, _ = self.request(
            "POST", "/api/expenses/telegram",
            self.expense_telegram(monto=100000, medio_pago="Crédito"),
        )
        self.assertEqual(status, 201)
        gasto_id = body["expenses"][0]["id"]

        status, deleted, _ = self.request("DELETE", f"/api/expenses/{gasto_id}")
        self.assertEqual(status, 200)
        self.assertIn("avisos_credito_nuevos", deleted)
        # Ya estaba registrado por el alta; la baja no debe re-registrar ni
        # desregistrar nada.
        self.assertEqual(deleted["avisos_credito_nuevos"], [])
        pendientes = self.request("GET", "/api/avisos-credito/pendientes")[1]["avisos_credito"]
        self.assertEqual([a["umbral"] for a in pendientes], [100000])


# --- T3: GET/PUT/DELETE /api/telegram/borrador ------------------------------


class TelegramBorradorApiTest(WsgiApiTestCase):
    """Rutas internas agregadas para el CLI (brief S2/S3, T3): exponen
    `db.get_estado`/`set_estado`/`clear_estado` sobre HTTP, misma auth que el
    resto de `/api/*`. `chat`/`usuario` son identificadores de dominio
    arbitrarios (no se exige formato de dígitos, a diferencia de
    `telegram_user_id`/`chat_id` de las rutas `*/telegram` de altas)."""

    def test_get_sin_borrador_devuelve_null(self):
        status, body, _ = self.request("GET", "/api/telegram/borrador?chat=chat-9&usuario=JD")
        self.assertEqual(status, 200)
        self.assertIsNone(body["borrador"])

    def test_set_get_clear_roundtrip(self):
        status, body, _ = self.request(
            "PUT", "/api/telegram/borrador?chat=chat-9&usuario=JD",
            {"estado": "esperando_campo", "campo_pendiente": "monto", "payload_parcial": {"categoria": "Comida"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["borrador"]["estado"], "esperando_campo")
        self.assertEqual(body["borrador"]["campo_pendiente"], "monto")
        self.assertEqual(body["borrador"]["payload_parcial"], {"categoria": "Comida"})

        status, body, _ = self.request("GET", "/api/telegram/borrador?chat=chat-9&usuario=JD")
        self.assertEqual(status, 200)
        self.assertEqual(body["borrador"]["estado"], "esperando_campo")

        status, body, _ = self.request("DELETE", "/api/telegram/borrador?chat=chat-9&usuario=JD")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"cleared": True})

        status, body, _ = self.request("GET", "/api/telegram/borrador?chat=chat-9&usuario=JD")
        self.assertEqual(status, 200)
        self.assertIsNone(body["borrador"])

    def test_dos_usuarios_mismo_chat_no_se_pisan(self):
        self.request(
            "PUT", "/api/telegram/borrador?chat=chat-9&usuario=JD",
            {"estado": "esperando_campo", "campo_pendiente": "monto"},
        )
        self.request(
            "PUT", "/api/telegram/borrador?chat=chat-9&usuario=Pinki",
            {"estado": "esperando_confirmacion"},
        )
        status, jd, _ = self.request("GET", "/api/telegram/borrador?chat=chat-9&usuario=JD")
        status2, pinki, _ = self.request("GET", "/api/telegram/borrador?chat=chat-9&usuario=Pinki")
        self.assertEqual(jd["borrador"]["estado"], "esperando_campo")
        self.assertEqual(pinki["borrador"]["estado"], "esperando_confirmacion")

    def test_usuario_omitido_usa_el_borrador_sin_usuario(self):
        status, body, _ = self.request(
            "PUT", "/api/telegram/borrador?chat=chat-legacy", {"estado": "esperando_confirmacion"},
        )
        self.assertEqual(status, 200)
        status, body, _ = self.request("GET", "/api/telegram/borrador?chat=chat-legacy")
        self.assertEqual(body["borrador"]["estado"], "esperando_confirmacion")

    def test_chat_obligatorio(self):
        self.assertEqual(self.request("GET", "/api/telegram/borrador?usuario=JD")[0], 400)
        self.assertEqual(self.request("PUT", "/api/telegram/borrador?usuario=JD", {"estado": "x"})[0], 400)
        self.assertEqual(self.request("DELETE", "/api/telegram/borrador?usuario=JD")[0], 400)

    def test_set_requiere_estado_no_vacio(self):
        status, _, _ = self.request("PUT", "/api/telegram/borrador?chat=chat-9", {})
        self.assertEqual(status, 400)
        status, _, _ = self.request("PUT", "/api/telegram/borrador?chat=chat-9", {"estado": ""})
        self.assertEqual(status, 400)
        status, _, _ = self.request("PUT", "/api/telegram/borrador?chat=chat-9", {"estado": "x", "campo_raro": 1})
        self.assertEqual(status, 400)

    def test_requiere_auth(self):
        self.assertEqual(self.request("GET", "/api/telegram/borrador?chat=chat-9", auth=False)[0], 401)
        self.assertEqual(
            self.request("PUT", "/api/telegram/borrador?chat=chat-9", {"estado": "x"}, auth=False)[0], 401,
        )
        self.assertEqual(self.request("DELETE", "/api/telegram/borrador?chat=chat-9", auth=False)[0], 401)

    def test_metodo_no_permitido_devuelve_405_con_allow(self):
        status, _, headers = self.request("POST", "/api/telegram/borrador?chat=chat-9", {"estado": "x"})
        self.assertEqual(status, 405)
        self.assertIn("Allow", headers)


if __name__ == "__main__":
    unittest.main()
