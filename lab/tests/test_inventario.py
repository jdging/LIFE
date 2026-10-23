"""Tests de la pestaña Inventario (t_0e38e74e): `inventario_bienes` en
`db.py` + endpoints `/api/inventory` en `api.py`.

Mismo patrón que `test_ingresos.py` (capa db, SQLite efímera) y
`test_api.py` (capa HTTP/WSGI, para 401/404 y el contrato de la API).
Nunca contra la base real.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

import pytest

import db
from api import create_app


# --- Capa db.py: validar_inventario_bien / insert / actualizar / soft delete ---


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def _bien_valido(**overrides):
    bien = {
        "nombre": "Notebook",
        "categoria": "Electrónica",
        "ubicacion": "Oficina",
        "valor_estimado": 500000.0,
        "fecha_adquisicion": "2026-03-01",
        "notas": "Comprada con garantía extendida",
    }
    bien.update(overrides)
    return bien


def test_bien_valido():
    assert db.validar_inventario_bien(_bien_valido()) == []


def test_bien_nombre_ausente():
    payload = _bien_valido()
    del payload["nombre"]
    errores = db.validar_inventario_bien(payload)
    assert any("nombre" in e for e in errores)


def test_bien_nombre_vacio():
    errores = db.validar_inventario_bien(_bien_valido(nombre="   "))
    assert any("nombre" in e for e in errores)


def test_bien_valor_estimado_ausente():
    payload = _bien_valido()
    del payload["valor_estimado"]
    errores = db.validar_inventario_bien(payload)
    assert any("valor_estimado" in e for e in errores)


def test_bien_valor_estimado_cero():
    errores = db.validar_inventario_bien(_bien_valido(valor_estimado=0))
    assert any("valor_estimado" in e for e in errores)


def test_bien_valor_estimado_negativo():
    errores = db.validar_inventario_bien(_bien_valido(valor_estimado=-100))
    assert any("valor_estimado" in e for e in errores)


def test_bien_valor_estimado_no_numerico():
    errores = db.validar_inventario_bien(_bien_valido(valor_estimado="caro"))
    assert any("valor_estimado" in e for e in errores)


def test_bien_categoria_vacia_invalida():
    errores = db.validar_inventario_bien(_bien_valido(categoria=""))
    assert any("categoria" in e for e in errores)


def test_bien_ubicacion_vacia_invalida():
    errores = db.validar_inventario_bien(_bien_valido(ubicacion=""))
    assert any("ubicacion" in e for e in errores)


def test_bien_categoria_y_ubicacion_ausentes_son_validas():
    payload = _bien_valido()
    del payload["categoria"]
    del payload["ubicacion"]
    assert db.validar_inventario_bien(payload) == []


def test_bien_fecha_adquisicion_invalida():
    errores = db.validar_inventario_bien(_bien_valido(fecha_adquisicion="01-03-2026"))
    assert any("fecha_adquisicion" in e for e in errores)


def test_bien_fecha_adquisicion_ausente_es_valida():
    payload = _bien_valido()
    del payload["fecha_adquisicion"]
    assert db.validar_inventario_bien(payload) == []


def test_bien_notas_vacia_es_valida():
    assert db.validar_inventario_bien(_bien_valido(notas="")) == []


# --- Campos financieros de paridad con el legacy (t_0e38e74e) ---------------


def test_bien_campos_financieros_ausentes_son_validos():
    assert db.validar_inventario_bien(_bien_valido()) == []


@pytest.mark.parametrize(
    "campo", ["precio_ars", "cotizacion_usd_compra", "precio_usd_compra", "precio_venta_estimado_usd"],
)
def test_bien_campo_financiero_negativo_invalido(campo):
    errores = db.validar_inventario_bien(_bien_valido(**{campo: -1}))
    assert any(campo in e for e in errores)


@pytest.mark.parametrize(
    "campo", ["precio_ars", "cotizacion_usd_compra", "precio_usd_compra", "precio_venta_estimado_usd"],
)
def test_bien_campo_financiero_cero_es_valido(campo):
    assert db.validar_inventario_bien(_bien_valido(**{campo: 0})) == []


@pytest.mark.parametrize(
    "campo", ["precio_ars", "cotizacion_usd_compra", "precio_usd_compra", "precio_venta_estimado_usd"],
)
def test_bien_campo_financiero_no_numerico_invalido(campo):
    errores = db.validar_inventario_bien(_bien_valido(**{campo: "mucho"}))
    assert any(campo in e for e in errores)


def test_bien_proporcion_jd_cero_es_valida():
    assert db.validar_inventario_bien(_bien_valido(proporcion_jd=0)) == []


def test_bien_proporcion_jd_cien_es_valida():
    assert db.validar_inventario_bien(_bien_valido(proporcion_jd=100)) == []


def test_bien_proporcion_jd_negativa_invalida():
    errores = db.validar_inventario_bien(_bien_valido(proporcion_jd=-1))
    assert any("proporcion_jd" in e for e in errores)


def test_bien_proporcion_jd_mayor_a_cien_invalida():
    errores = db.validar_inventario_bien(_bien_valido(proporcion_jd=100.01))
    assert any("proporcion_jd" in e for e in errores)


def test_bien_proporcion_jd_no_numerica_invalida():
    errores = db.validar_inventario_bien(_bien_valido(proporcion_jd="mitad"))
    assert any("proporcion_jd" in e for e in errores)


@pytest.mark.parametrize("estado", db.INVENTARIO_ESTADOS)
def test_bien_estado_valido_para_cada_valor_cerrado(estado):
    assert db.validar_inventario_bien(_bien_valido(estado=estado)) == []


def test_bien_estado_invalido():
    errores = db.validar_inventario_bien(_bien_valido(estado="Perdido"))
    assert any("estado" in e for e in errores)


def test_insert_inventario_bien_valido(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["nombre"] == "Notebook"
    assert fila["valor_estimado"] == 500000.0
    assert fila["deleted_at"] is None


def test_insert_inventario_bien_invalido_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_inventario_bien(conn, _bien_valido(valor_estimado=-1))


# --- Defaults de negocio al crear (proporcion_jd=50, estado='Activo') -------


def test_insert_inventario_bien_default_proporcion_jd_50(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["proporcion_jd"] == 50


def test_insert_inventario_bien_default_estado_activo(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["estado"] == "Activo"


def test_insert_inventario_bien_proporcion_jd_cero_no_se_pisa_con_default(conn):
    """proporcion_jd=0 (100% Pinki) es falsy en Python — debe preservarse, no
    reemplazarse por el default 50 (ver nota de `insert_inventario_bien`)."""
    bien_id = db.insert_inventario_bien(conn, _bien_valido(proporcion_jd=0))
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["proporcion_jd"] == 0


def test_insert_inventario_bien_con_campos_financieros_explicitos(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido(
        precio_ars=500000.0, cotizacion_usd_compra=1200.0, precio_usd_compra=416.67,
        proporcion_jd=70, precio_venta_estimado_usd=300.0, estado="Vendido",
    ))
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["precio_ars"] == 500000.0
    assert fila["cotizacion_usd_compra"] == 1200.0
    assert fila["precio_usd_compra"] == 416.67
    assert fila["proporcion_jd"] == 70
    assert fila["precio_venta_estimado_usd"] == 300.0
    assert fila["estado"] == "Vendido"


def test_actualizar_inventario_bien_edicion_valida(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido(valor_estimado=500000.0))

    db.actualizar_inventario_bien(conn, bien_id, {"valor_estimado": 450000.0, "ubicacion": "Living"})

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["valor_estimado"] == 450000.0
    assert fila["ubicacion"] == "Living"
    assert fila["nombre"] == "Notebook"  # no tocado, se mantiene


def test_actualizar_inventario_bien_invalido_no_aplica_cambios(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido(valor_estimado=500000.0))

    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, bien_id, {"valor_estimado": -1})

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["valor_estimado"] == 500000.0  # no se aplicó el cambio inválido


def test_actualizar_inventario_bien_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, 9999, {"valor_estimado": 1000.0})


def test_actualizar_inventario_bien_campo_no_editable_lanza_valueerror(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, bien_id, {"id": 999})


def test_actualizar_inventario_bien_campos_financieros_edicion_valida(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())

    db.actualizar_inventario_bien(conn, bien_id, {
        "estado": "Donado", "proporcion_jd": 30, "precio_venta_estimado_usd": 120.5,
    })

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["estado"] == "Donado"
    assert fila["proporcion_jd"] == 30
    assert fila["precio_venta_estimado_usd"] == 120.5


def test_actualizar_inventario_bien_estado_invalido_no_aplica_cambios(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())

    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, bien_id, {"estado": "Perdido"})

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["estado"] == "Activo"  # default al crear, no se tocó


def test_actualizar_inventario_bien_cambios_vacios_lanza_valueerror(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, bien_id, {})


def test_actualizar_inventario_bien_sobre_borrado_lanza_valueerror(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido(valor_estimado=500000.0))
    db.eliminar_inventario_bien_logico(conn, bien_id, actor="JD")

    with pytest.raises(ValueError):
        db.actualizar_inventario_bien(conn, bien_id, {"valor_estimado": 1000.0})

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila["valor_estimado"] == 500000.0  # no se aplicó el cambio sobre un borrado


# --- Soft delete de inventario_bienes + auditoría ---------------------------


def test_migracion_agrega_columnas_soft_delete_inventario(conn):
    columnas = db._column_names(conn, "inventario_bienes")
    assert "deleted_at" in columnas
    assert "deleted_by" in columnas


def test_eliminar_inventario_bien_logico_no_borra_fila_fisicamente(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())

    db.eliminar_inventario_bien_logico(conn, bien_id, actor="JD")

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    assert fila is not None  # sigue existiendo físicamente
    assert fila["deleted_at"] is not None
    assert fila["deleted_by"] == "JD"


def test_eliminar_inventario_bien_logico_inserta_auditoria(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido(nombre="Bicicleta"))

    db.eliminar_inventario_bien_logico(conn, bien_id, actor="Pinki")

    filas_auditoria = conn.execute(
        "SELECT * FROM auditoria WHERE tabla = 'inventario_bienes' AND fila_id = ?", (bien_id,)
    ).fetchall()
    assert len(filas_auditoria) == 1
    auditoria = dict(filas_auditoria[0])
    assert auditoria["accion"] == "baja"
    assert auditoria["actor"] == "Pinki"
    assert auditoria["despues_json"] is None
    assert "Bicicleta" in auditoria["antes_json"]


def test_eliminar_inventario_bien_logico_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.eliminar_inventario_bien_logico(conn, 9999, actor="JD")


def test_eliminar_inventario_bien_logico_ya_borrado_lanza_valueerror(conn):
    bien_id = db.insert_inventario_bien(conn, _bien_valido())
    db.eliminar_inventario_bien_logico(conn, bien_id, actor="JD")

    with pytest.raises(ValueError):
        db.eliminar_inventario_bien_logico(conn, bien_id, actor="Pinki")


def test_get_inventario_bienes_excluye_borrados_por_default(conn):
    activo_id = db.insert_inventario_bien(conn, _bien_valido(nombre="Activo"))
    borrado_id = db.insert_inventario_bien(conn, _bien_valido(nombre="Borrado"))
    db.eliminar_inventario_bien_logico(conn, borrado_id, actor="JD")

    bienes = db.get_inventario_bienes(conn)
    ids = [b["id"] for b in bienes]

    assert activo_id in ids
    assert borrado_id not in ids


def test_get_inventario_bienes_incluye_borrados_si_se_pide_explicitamente(conn):
    activo_id = db.insert_inventario_bien(conn, _bien_valido(nombre="Activo"))
    borrado_id = db.insert_inventario_bien(conn, _bien_valido(nombre="Borrado"))
    db.eliminar_inventario_bien_logico(conn, borrado_id, actor="JD")

    bienes = db.get_inventario_bienes(conn, incluir_borrados=True)
    ids = [b["id"] for b in bienes]

    assert activo_id in ids
    assert borrado_id in ids
    assert len(bienes) == 2


def test_get_inventario_bienes_filtra_por_categoria(conn):
    db.insert_inventario_bien(conn, _bien_valido(nombre="Notebook", categoria="Electrónica"))
    db.insert_inventario_bien(conn, _bien_valido(nombre="Sillón", categoria="Muebles"))

    bienes = db.get_inventario_bienes(conn, categoria="Muebles")

    assert [b["nombre"] for b in bienes] == ["Sillón"]


def test_migracion_columnas_inventario_idempotente_sobre_base_vieja():
    """Simula una base vieja sin `deleted_at`/`deleted_by` en
    `inventario_bienes` (esquema previo a t_0e38e74e): crea la tabla a mano
    sin esas columnas, inserta una fila, y verifica que
    `_migrar_columnas_inventario_bienes` las agregue sin tocar los datos
    existentes, y que correrla dos veces sea un no-op.
    """
    vieja = db.get_connection(":memory:")
    try:
        vieja.execute(
            """
            CREATE TABLE inventario_bienes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT,
                ubicacion TEXT,
                valor_estimado REAL,
                fecha_adquisicion TEXT,
                notas TEXT
            )
            """
        )
        vieja.execute(
            """
            INSERT INTO inventario_bienes
                (nombre, categoria, ubicacion, valor_estimado, fecha_adquisicion, notas)
            VALUES ('Legacy TV', 'Electrónica', 'Living', 300000.0, '2025-01-01', 'migrado')
            """
        )
        vieja.commit()

        columnas_antes = db._column_names(vieja, "inventario_bienes")
        assert "deleted_at" not in columnas_antes
        assert "deleted_by" not in columnas_antes

        db._migrar_columnas_inventario_bienes(vieja)  # primera corrida

        columnas_despues = db._column_names(vieja, "inventario_bienes")
        assert "deleted_at" in columnas_despues
        assert "deleted_by" in columnas_despues

        fila = vieja.execute(
            "SELECT * FROM inventario_bienes WHERE nombre = 'Legacy TV'"
        ).fetchone()
        assert fila["valor_estimado"] == 300000.0
        assert fila["deleted_at"] is None

        db._migrar_columnas_inventario_bienes(vieja)  # segunda corrida: idempotente
        filas = vieja.execute("SELECT * FROM inventario_bienes").fetchall()
        assert len(filas) == 1
    finally:
        vieja.close()


def test_migracion_columnas_financieras_idempotente_sobre_tabla_sin_esas_columnas():
    """Simula una base intermedia (deleted_at/deleted_by ya migrados, pero sin
    las columnas financieras agregadas en esta vuelta de t_0e38e74e): verifica
    que `_migrar_columnas_inventario_bienes` las agregue en NULL sin tocar
    los datos existentes, y que correrla dos veces sea un no-op.
    """
    intermedia = db.get_connection(":memory:")
    try:
        intermedia.execute(
            """
            CREATE TABLE inventario_bienes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT,
                ubicacion TEXT,
                valor_estimado REAL,
                fecha_adquisicion TEXT,
                notas TEXT,
                deleted_at TEXT,
                deleted_by TEXT
            )
            """
        )
        intermedia.execute(
            """
            INSERT INTO inventario_bienes
                (nombre, categoria, ubicacion, valor_estimado, fecha_adquisicion, notas)
            VALUES ('TV migrada', 'Electrónica', 'Living', 300000.0, '2025-01-01', 'migrado')
            """
        )
        intermedia.commit()

        db._migrar_columnas_inventario_bienes(intermedia)  # primera corrida

        columnas = db._column_names(intermedia, "inventario_bienes")
        for columna in (
            "precio_ars", "cotizacion_usd_compra", "precio_usd_compra",
            "proporcion_jd", "precio_venta_estimado_usd", "estado",
        ):
            assert columna in columnas

        fila = intermedia.execute(
            "SELECT * FROM inventario_bienes WHERE nombre = 'TV migrada'"
        ).fetchone()
        assert fila["valor_estimado"] == 300000.0  # dato preexistente intacto
        # Columnas nuevas en NULL para filas preexistentes: no hay backfill
        # automático desde `notas` (ver docstring de la migración en db.py).
        assert fila["proporcion_jd"] is None
        assert fila["estado"] is None

        db._migrar_columnas_inventario_bienes(intermedia)  # segunda corrida: idempotente
        filas = intermedia.execute("SELECT * FROM inventario_bienes").fetchall()
        assert len(filas) == 1
    finally:
        intermedia.close()


# --- Capa HTTP/WSGI: /api/inventory (CRUD, 404, 401) -------------------------


TEST_SECRET = "local-test-only"


def _strict_json(raw):
    def reject_constant(value):
        raise ValueError(f"constante JSON inválida: {value}")
    return json.loads(raw, parse_constant=reject_constant)


class InventoryApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "api.sqlite")
        self.app = create_app(self.db_path, TEST_SECRET)

    def tearDown(self):
        self.app.close()
        self.tempdir.cleanup()

    def request(self, method, path, payload=None, *, auth=True):
        path_only, _, query = path.partition("?")
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_only,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json" if payload is not None else "",
            "wsgi.input": io.BytesIO(body),
        }
        if auth:
            environ["HTTP_X_INTERNAL_PROXY_SECRET"] = TEST_SECRET
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split(" ", 1)[0])
            captured["headers"] = dict(headers)

        response = b"".join(self.app(environ, start_response))
        return captured["status"], _strict_json(response), captured["headers"]

    def bien(self, **changes):
        payload = {
            "nombre": "Notebook", "categoria": "Electrónica", "ubicacion": "Oficina",
            "valor_estimado": 500000, "fecha_adquisicion": "2026-03-01",
        }
        payload.update(changes)
        return payload

    def test_health_declara_capability_inventory(self):
        status, body, _ = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertIn("inventory", body["capabilities"])

    def test_crud_completo(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien())
        self.assertEqual(status, 201)
        bien_id = created["inventory"]["id"]
        self.assertEqual(created["inventory"]["nombre"], "Notebook")

        status, listed, _ = self.request("GET", "/api/inventory")
        self.assertEqual(status, 200)
        self.assertIn(bien_id, [row["id"] for row in listed["inventory"]])

        status, updated, _ = self.request(
            "PATCH", f"/api/inventory/{bien_id}", {"valor_estimado": 450000}
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["inventory"]["valor_estimado"], 450000)

        status, deleted, _ = self.request("DELETE", f"/api/inventory/{bien_id}")
        self.assertEqual(status, 200)
        self.assertEqual(deleted, {"deleted": True, "id": bien_id})

        status, listed_after, _ = self.request("GET", "/api/inventory")
        self.assertEqual(status, 200)
        self.assertNotIn(bien_id, [row["id"] for row in listed_after["inventory"]])

    def test_create_valida_payload(self):
        self.assertEqual(self.request("POST", "/api/inventory", self.bien(nombre=""))[0], 400)
        self.assertEqual(self.request("POST", "/api/inventory", self.bien(valor_estimado=-1))[0], 400)
        self.assertEqual(self.request("POST", "/api/inventory", self.bien(fecha_adquisicion="no-es-fecha"))[0], 400)
        self.assertEqual(self.request("POST", "/api/inventory", self.bien(campo_desconocido=1))[0], 400)

    def test_update_404_y_sin_campos(self):
        self.assertEqual(self.request("PATCH", "/api/inventory/999999", {"valor_estimado": 1})[0], 404)
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.assertEqual(self.request("PATCH", f"/api/inventory/{bien_id}", {})[0], 400)

    def test_delete_404_en_inexistente_y_en_ya_borrado(self):
        self.assertEqual(self.request("DELETE", "/api/inventory/999999")[0], 404)
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.assertEqual(self.request("DELETE", f"/api/inventory/{bien_id}")[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/inventory/{bien_id}")[0], 404)

    def test_baja_logica_excluida_del_get_pero_queda_en_db(self):
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.request("DELETE", f"/api/inventory/{bien_id}")

        listed = self.request("GET", "/api/inventory")[1]["inventory"]
        self.assertNotIn(bien_id, [row["id"] for row in listed])

        with db.get_connection(self.db_path) as conn:
            fila = conn.execute(
                "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
            ).fetchone()
            self.assertIsNotNone(fila)  # sigue en la tabla, solo oculto del GET
            self.assertIsNotNone(fila["deleted_at"])

    def test_401_sin_secreto_en_todas_las_rutas(self):
        self.assertEqual(self.request("GET", "/api/inventory", auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/inventory", self.bien(), auth=False)[0], 401)
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.assertEqual(
            self.request("PATCH", f"/api/inventory/{bien_id}", {"valor_estimado": 1}, auth=False)[0], 401
        )
        self.assertEqual(self.request("DELETE", f"/api/inventory/{bien_id}", auth=False)[0], 401)

    # --- Campos financieros nuevos (t_0e38e74e, paridad con el legacy) ------

    def test_create_devuelve_defaults_proporcion_jd_y_estado(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien())
        self.assertEqual(status, 201)
        self.assertEqual(created["inventory"]["proporcion_jd"], 50)
        self.assertEqual(created["inventory"]["estado"], "Activo")

    def test_create_acepta_y_devuelve_campos_financieros_explicitos(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(
            precio_ars=500000, cotizacion_usd_compra=1200, precio_usd_compra=416.67,
            proporcion_jd=30, precio_venta_estimado_usd=300, estado="Donado",
        ))
        self.assertEqual(status, 201)
        body = created["inventory"]
        self.assertEqual(body["precio_ars"], 500000)
        self.assertEqual(body["cotizacion_usd_compra"], 1200)
        self.assertEqual(body["precio_usd_compra"], 416.67)
        self.assertEqual(body["proporcion_jd"], 30)
        self.assertEqual(body["precio_venta_estimado_usd"], 300)
        self.assertEqual(body["estado"], "Donado")

    def test_create_sugiere_precio_usd_compra_desde_ars_y_cotizacion(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(
            precio_ars=500000, cotizacion_usd_compra=1200,
        ))
        self.assertEqual(status, 201)
        # 500000 / 1200 = 416.666... -> redondeado a 2 decimales con ROUND_HALF_UP
        self.assertEqual(created["inventory"]["precio_usd_compra"], 416.67)

    def test_create_no_sugiere_si_precio_usd_compra_viene_explicito(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(
            precio_ars=500000, cotizacion_usd_compra=1200, precio_usd_compra=100,
        ))
        self.assertEqual(status, 201)
        self.assertEqual(created["inventory"]["precio_usd_compra"], 100)

    def test_create_no_sugiere_si_falta_cotizacion(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(precio_ars=500000))
        self.assertEqual(status, 201)
        self.assertIsNone(created["inventory"]["precio_usd_compra"])

    def test_create_no_sugiere_con_cotizacion_cero(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(
            precio_ars=500000, cotizacion_usd_compra=0,
        ))
        # cotizacion_usd_compra=0 es válido como monto (>= 0) pero no se usa
        # como divisor: evita ZeroDivisionError, no sugiere nada.
        self.assertEqual(status, 201)
        self.assertIsNone(created["inventory"]["precio_usd_compra"])

    def test_patch_sugiere_precio_usd_compra(self):
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        status, updated, _ = self.request("PATCH", f"/api/inventory/{bien_id}", {
            "precio_ars": 100000, "cotizacion_usd_compra": 1000,
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["inventory"]["precio_usd_compra"], 100.0)

    def test_create_rechaza_campo_financiero_negativo(self):
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(precio_ars=-1))[0], 400
        )
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(precio_venta_estimado_usd=-1))[0], 400
        )

    def test_create_rechaza_campo_financiero_con_mas_de_dos_decimales(self):
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(precio_usd_compra=1.005))[0], 400
        )

    def test_create_rechaza_proporcion_jd_fuera_de_rango(self):
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(proporcion_jd=101))[0], 400
        )
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(proporcion_jd=-1))[0], 400
        )

    def test_create_acepta_proporcion_jd_cero(self):
        status, created, _ = self.request("POST", "/api/inventory", self.bien(proporcion_jd=0))
        self.assertEqual(status, 201)
        self.assertEqual(created["inventory"]["proporcion_jd"], 0)

    def test_create_rechaza_estado_invalido(self):
        self.assertEqual(
            self.request("POST", "/api/inventory", self.bien(estado="Perdido"))[0], 400
        )

    def test_patch_rechaza_estado_invalido_y_no_aplica_cambios(self):
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.assertEqual(
            self.request("PATCH", f"/api/inventory/{bien_id}", {"estado": "Perdido"})[0], 400
        )
        listed = self.request("GET", "/api/inventory")[1]["inventory"]
        fila = next(row for row in listed if row["id"] == bien_id)
        self.assertEqual(fila["estado"], "Activo")

    # --- Vaciar campos opcionales en la edición (t_0e38e74e, hallazgo 3) ----

    def test_patch_vacia_fecha_adquisicion_con_null(self):
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        status, updated, _ = self.request(
            "PATCH", f"/api/inventory/{bien_id}", {"fecha_adquisicion": None}
        )
        self.assertEqual(status, 200)
        self.assertIsNone(updated["inventory"]["fecha_adquisicion"])

        listed = self.request("GET", "/api/inventory")[1]["inventory"]
        fila = next(row for row in listed if row["id"] == bien_id)
        self.assertIsNone(fila["fecha_adquisicion"])

    def test_patch_vacia_varios_campos_opcionales_con_null(self):
        bien_id = self.request("POST", "/api/inventory", self.bien(
            categoria="Electrónica", ubicacion="Oficina", notas="algo",
            precio_ars=100000, cotizacion_usd_compra=1000, precio_usd_compra=100,
            proporcion_jd=70,
        ))[1]["inventory"]["id"]

        status, updated, _ = self.request("PATCH", f"/api/inventory/{bien_id}", {
            "categoria": None, "ubicacion": None, "notas": None,
            "precio_ars": None, "cotizacion_usd_compra": None,
            "precio_usd_compra": None, "proporcion_jd": None,
        })
        self.assertEqual(status, 200)
        body = updated["inventory"]
        for campo in (
            "categoria", "ubicacion", "notas", "precio_ars",
            "cotizacion_usd_compra", "precio_usd_compra", "proporcion_jd",
        ):
            self.assertIsNone(body[campo])

    def test_patch_fecha_adquisicion_null_no_rompe_validacion_de_formato(self):
        bien_id = self.request("POST", "/api/inventory", self.bien())[1]["inventory"]["id"]
        self.assertEqual(
            self.request(
                "PATCH", f"/api/inventory/{bien_id}", {"fecha_adquisicion": "no-es-fecha"}
            )[0], 400,
        )
