"""F4: solo datos sintéticos y SQLite temporal bajo TMPDIR externo al candidato."""
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

import db
import supermercado
from api import create_app
from supermercado_pdf import build_pdf

SECRET = "synthetic-test-secret"


class SupermercadoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.path = str(Path(self.tmp.name) / "synthetic.sqlite")
        self.app = create_app(self.path, SECRET)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, auth=True, query=""):
        body = json.dumps(payload).encode() if payload is not None else b""
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path,
                   "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json" if body else "",
                   "QUERY_STRING": query, "wsgi.input": io.BytesIO(body)}
        if auth:
            environ["HTTP_X_INTERNAL_PROXY_SECRET"] = SECRET
        response = {}
        def start(status, headers):
            response["status"] = int(status.split()[0]); response["headers"] = dict(headers)
        response["body"] = b"".join(self.app(environ, start))
        if response["headers"]["Content-Type"].startswith("application/json"):
            response["json"] = json.loads(response["body"])
        return response

    def create(self, producto="Leche", desired=2.5, current=0.5, category=None):
        return self.request("POST", "/api/supermercado/productos", {
            "producto": producto, "unidad": "L", "categoria_id": category,
            "stock_deseado": desired, "stock_actual": current})

    def test_isolation_migration_and_empty_state(self):
        with db.get_connection(self.path) as conn:
            db.init_db(conn)
            db.init_db(conn)
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"supermercado_categorias", "supermercado_productos", "supermercado_auditoria"} <= names)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM supermercado_productos").fetchone()[0], 0)
        self.assertEqual(self.request("GET", "/api/supermercado")["json"]["resumen"]["global"]["productos"], 0)
        self.assertEqual(self.request("GET", "/api/supermercado/lista.pdf")["status"], 409)

    def test_calculations_and_audit(self):
        row = self.create()["json"]["registro"]
        self.assertEqual(row["version"], 1)
        self.assertEqual(self.request("PATCH", f'/api/supermercado/productos/{row["id"]}/stock', {"stock_actual": 1.25, "expected_version": row["version"]})["status"], 200)
        self.create("Cero", 0, 0)
        self.create("Overstock", 2, 3)
        state = self.request("GET", "/api/supermercado")["json"]
        rows = state["productos"]
        self.assertEqual(state["resumen"]["global"]["a_reponer"], 1)
        self.assertEqual(state["resumen"]["global"]["vacios"], 1)
        self.assertAlmostEqual(state["resumen"]["global"]["porcentaje_vacio"], 100 / 3)
        by_name = {r["producto"]: r for r in rows}
        self.assertEqual(by_name["Leche"]["a_comprar"], 1.25)
        self.assertEqual(by_name["Leche"]["porcentaje_faltante"], 50)
        self.assertEqual((by_name["Cero"]["a_comprar"], by_name["Cero"]["porcentaje_faltante"], by_name["Cero"]["estado"]), (0, 0, "Vacío"))
        self.assertEqual((by_name["Overstock"]["a_comprar"], by_name["Overstock"]["estado"]), (0, "OK"))
        history = self.request("GET", f'/api/supermercado/productos/{row["id"]}/historial')["json"]["historial"]
        self.assertEqual([h["operacion"] for h in history], ["stock", "alta"])
        self.assertEqual((history[0]["antes"]["stock_actual"], history[0]["despues"]["stock_actual"]), ("0.5", "1.25"))
        self.assertEqual(history[0]["actor"], supermercado.ACTOR)
        self.assertEqual(self.request("PATCH", f'/api/supermercado/productos/{row["id"]}/stock', {"stock_actual": "7", "expected_version": 2})["status"], 400)
        self.assertEqual(len(self.request("GET", f'/api/supermercado/productos/{row["id"]}/historial')["json"]["historial"]), 2)
        self.assertTrue(history[0]["fecha_utc"].endswith("+00:00"))
        self.request("DELETE", f'/api/supermercado/productos/{row["id"]}', {"expected_version": 2})
        self.assertEqual(self.request("GET", f'/api/supermercado/productos/{row["id"]}/historial')["json"]["historial"][0]["operacion"], "baja")

    def test_product_edit_updates_all_fields_and_audits_only_success(self):
        category = self.request("POST", "/api/supermercado/categorias", {"nombre": "Almacén", "orden": 1})["json"]["registro"]["id"]
        created = self.create()["json"]["registro"]
        path = f'/api/supermercado/productos/{created["id"]}'
        payload = {"producto": "Arroz integral", "unidad": "kg", "categoria_id": category,
                   "stock_deseado": 3.75, "stock_actual": 1.25, "expected_version": created["version"]}
        edited_response = self.request("PATCH", path, payload)
        self.assertEqual(edited_response["status"], 200)
        edited = edited_response["json"]["registro"]
        self.assertEqual(edited["version"], created["version"] + 1)
        self.assertEqual((edited["producto"], edited["unidad"], edited["categoria_id"]),
                         ("Arroz integral", "kg", category))
        self.assertEqual((edited["stock_deseado"], edited["stock_actual"]), ("3.75", "1.25"))
        history = self.request("GET", path + "/historial")["json"]["historial"]
        self.assertEqual([event["operacion"] for event in history], ["edicion", "alta"])
        self.assertEqual(history[0]["antes"], created)
        self.assertEqual(history[0]["despues"], edited)

        listed = self.request("GET", "/api/supermercado")["json"]["productos"]
        self.assertEqual(len(listed), 1)
        self.assertEqual((listed[0]["producto"], listed[0]["unidad"], listed[0]["categoria"], listed[0]["version"]),
                         ("Arroz integral", "kg", "Almacén", edited["version"]))
        self.assertEqual((listed[0]["a_comprar"], listed[0]["estado"]), (2.5, "Reponer"))
        self.assertAlmostEqual(listed[0]["porcentaje_faltante"], 2.5 / 3.75 * 100)

        invalid = self.request("PATCH", path, {"producto": "bad\nname", "expected_version": edited["version"]})
        self.assertEqual(invalid["status"], 400)
        self.assertEqual(self.request("GET", "/api/supermercado")["json"]["productos"], listed)
        self.assertEqual(self.request("GET", path + "/historial")["json"]["historial"], history)

    def test_validation_auth_and_category_order(self):
        self.assertEqual(self.request("GET", "/api/supermercado", auth=False)["status"], 401)
        for bad in [True, "2", -1, float("nan"), float("inf"), 0.0000001]:
            self.assertEqual(self.create(desired=bad)["status"], 400)
        self.assertEqual(self.create(producto="<script>alert(1)</script>")["status"], 201)
        self.assertEqual(self.create(producto="bad\nname")["status"], 400)
        cat2 = self.request("POST", "/api/supermercado/categorias", {"nombre": "Bebidas", "orden": 2})["json"]["registro"]["id"]
        cat1 = self.request("POST", "/api/supermercado/categorias", {"nombre": "Álmacen", "orden": 1})["json"]["registro"]["id"]
        self.create("Zumo", category=cat2)
        self.create("Árroz", category=cat1)
        self.create("Aceite", category=cat1)
        self.create("Sin categoría")
        rows = self.request("GET", "/api/supermercado")["json"]["productos"]
        self.assertEqual([r["producto"] for r in rows if r["categoria_id"] == cat1], ["Aceite", "Árroz"])
        self.assertEqual(rows[-1]["categoria"], None)
        self.assertEqual(self.request("PATCH", f"/api/supermercado/categorias/{cat2}", {"orden": 0})["status"], 200)
        self.assertEqual(self.request("DELETE", f"/api/supermercado/categorias/{cat2}")["status"], 200)
        after_delete = self.request("GET", "/api/supermercado")["json"]["productos"]
        z = next(row for row in after_delete if row["producto"] == "Zumo")
        self.assertIsNone(z["categoria_id"])
        self.assertEqual(self.request("GET", f'/api/supermercado/productos/{z["id"]}/historial')["json"]["historial"][0]["operacion"], "categoria_baja")
        self.assertEqual(self.request("POST", "/api/supermercado/categorias", {"nombre": "Bebidas", "orden": 3})["status"], 201)
        self.assertEqual(self.request("POST", "/api/supermercado/productos", {"producto": "x", "unidad": "u", "stock_actual": 0, "stock_deseado": 1, "actor": "JD"})["status"], 400)

    def test_two_readers_conflict_and_category_reassignment(self):
        category = self.request("POST", "/api/supermercado/categorias", {"nombre": "Lácteos", "orden": 1})["json"]["registro"]["id"]
        created = self.create(category=category)["json"]["registro"]
        path = f'/api/supermercado/productos/{created["id"]}'
        first = self.request("GET", "/api/supermercado")["json"]["productos"][0]
        second = self.request("GET", "/api/supermercado")["json"]["productos"][0]
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(self.request("PATCH", path + "/stock", {"stock_actual": 1, "expected_version": first["version"]})["json"]["registro"]["version"], 2)
        self.assertEqual(self.request("PATCH", path + "/stock", {"stock_actual": 9, "expected_version": second["version"]})["status"], 409)
        self.assertEqual(self.request("PATCH", path, {"producto": "Otro", "expected_version": second["version"]})["status"], 409)
        self.assertEqual(self.request("DELETE", path, {"expected_version": second["version"]})["status"], 409)
        self.assertEqual(self.request("PATCH", path + "/stock", {"stock_actual": 9})["status"], 400)
        self.assertEqual(self.request("DELETE", path)["status"], 400)
        self.assertEqual(self.request("GET", "/api/supermercado")["json"]["productos"][0]["stock_actual"], 1)
        history = self.request("GET", path + "/historial")["json"]["historial"]
        self.assertEqual(len(history), 2)
        self.assertEqual((history[0]["antes"]["version"], history[0]["despues"]["version"]), (1, 2))
        self.assertEqual(self.request("DELETE", f"/api/supermercado/categorias/{category}")["status"], 200)
        reassigned = self.request("GET", "/api/supermercado")["json"]["productos"][0]
        self.assertEqual((reassigned["categoria_id"], reassigned["version"]), (None, 3))
        self.assertEqual(self.request("PATCH", path + "/stock", {"stock_actual": 0, "expected_version": 2})["status"], 409)
        self.assertEqual(self.request("GET", path + "/historial")["json"]["historial"][0]["despues"]["version"], 3)

    def test_history_pages_invalid_cursor_and_deleted_product(self):
        row = self.create()["json"]["registro"]
        path = f'/api/supermercado/productos/{row["id"]}'
        for version in range(1, 54):
            response = self.request("PATCH", path + "/stock", {"stock_actual": version, "expected_version": version})
            self.assertEqual(response["status"], 200)
        first = self.request("GET", path + "/historial")["json"]
        self.assertEqual(len(first["historial"]), 50)
        self.assertTrue(first["has_more"])
        second = self.request("GET", path + "/historial", query=f'cursor={first["next_cursor"]}')["json"]
        self.assertEqual(len(second["historial"]), 4)
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_cursor"])
        for cursor in ["0", "abc", "999999999999999999999", "999999"]:
            self.assertEqual(self.request("GET", path + "/historial", query=f"cursor={cursor}")["status"], 400)
        self.assertEqual(self.request("GET", "/api/supermercado/productos/999999/historial")["status"], 404)
        self.assertEqual(self.request("DELETE", path, {"expected_version": 54})["status"], 200)
        self.assertEqual(self.request("PATCH", path + "/stock", {"stock_actual": 8, "expected_version": 54})["status"], 409)
        self.assertEqual(self.request("GET", path + "/historial")["json"]["historial"][0]["operacion"], "baja")

    def test_capacity_and_v1_migration(self):
        with db.get_connection(self.path) as conn:
            conn.executemany("INSERT INTO supermercado_categorias(nombre,orden) VALUES (?,0)",
                             [(f"Categoría {i}",) for i in range(supermercado.MAX_CATEGORIES)])
            conn.executemany("INSERT INTO supermercado_productos(producto,unidad,stock_deseado,stock_actual) VALUES ('x','u','1','0')",
                             [() for _ in range(supermercado.MAX_PRODUCTS)])
        self.assertEqual(self.request("POST", "/api/supermercado/categorias", {"nombre": "Extra", "orden": 0})["status"], 409)
        self.assertEqual(self.create()["status"], 409)
        with db.get_connection(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM supermercado_productos WHERE deleted_at IS NULL").fetchone()[0], 1000)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM supermercado_auditoria").fetchone()[0], 0)
        legacy = str(Path(self.tmp.name) / "v1.sqlite")
        with sqlite3.connect(legacy) as conn:
            conn.execute("CREATE TABLE supermercado_productos (id INTEGER PRIMARY KEY, categoria_id INTEGER, producto TEXT, unidad TEXT, stock_deseado TEXT, stock_actual TEXT, deleted_at TEXT)")
            conn.execute("INSERT INTO supermercado_productos(producto,unidad,stock_deseado,stock_actual) VALUES ('Viejo','u','1','0')")
            supermercado.init_schema(conn)
            supermercado.init_schema(conn)
            self.assertEqual(conn.execute("SELECT version FROM supermercado_productos").fetchone()[0], 1)

    def test_list_uses_one_sqlite_snapshot(self):
        category = self.request("POST", "/api/supermercado/categorias", {"nombre": "Inicial", "orden": 1})["json"]["registro"]["id"]
        self.create(category=category)
        with db.get_connection(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        original = supermercado.categories

        def concurrent_update(read_conn):
            result = original(read_conn)
            with db.get_connection(self.path) as writer:
                writer.execute("UPDATE supermercado_categorias SET nombre='Nuevo' WHERE id=?", (category,))
            return result

        with patch.object(supermercado, "categories", side_effect=concurrent_update):
            snapshot = self.request("GET", "/api/supermercado")["json"]
        self.assertEqual(snapshot["categorias"][0]["nombre"], "Inicial")
        self.assertEqual(snapshot["productos"][0]["categoria"], "Inicial")
        self.assertEqual(snapshot["resumen"]["categorias"][0]["nombre"], "Inicial")
        self.assertEqual(self.request("GET", "/api/supermercado")["json"]["categorias"][0]["nombre"], "Nuevo")

    def test_name_allows_literal_backslash_n(self):
        response = self.create(producto=r"bad\nname")
        self.assertEqual(response["status"], 201)
        self.assertEqual(response["json"]["registro"]["producto"], r"bad\nname")

    def test_pdf_a4_and_many_pages(self):
        self.create("Leche", 2.5, 0.5)
        response = self.request("GET", "/api/supermercado/lista.pdf")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/pdf")
        self.assertTrue(response["body"].startswith(b"%PDF-"))
        with db.get_connection(self.path) as conn:
            rows = supermercado.products(conn)
        # 170 synthetic rows plus long text: content must continue over pages.
        rows = rows + [{**rows[0], "id": i + 100, "producto": "Producto sintético " + "x" * 100} for i in range(170)]
        pdf = build_pdf(rows, datetime(2026, 10, 28, tzinfo=timezone.utc))
        self.assertGreater(len(re.findall(rb"/Type\s*/Page\b", pdf)), 1)
        self.assertTrue(pdf.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
