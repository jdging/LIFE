"""Contract checks for the candidate WSGI API; all databases are ephemeral."""

import io
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from wsgiref.simple_server import make_server

import db
from api import create_app


TEST_SECRET = "local-test-only"


def strict_json(raw):
    def reject_constant(value):
        raise ValueError(f"constante JSON inválida: {value}")
    return json.loads(raw, parse_constant=reject_constant)


class WsgiApiTestCase(unittest.TestCase):
    """Harness WSGI común (setUp/tearDown/request + payloads de ejemplo).

    Separado de `ApiTest` para que `tests/test_telegram_api.py` lo reutilice
    sin duplicar ~60 líneas de infraestructura de request/respuesta ni
    volver a correr los `test_*` de este archivo bajo otro nombre de clase.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "api.sqlite")
        self.app = create_app(self.db_path, TEST_SECRET)

    def tearDown(self):
        self.app.close()
        self.tempdir.cleanup()

    def request(self, method, path, payload=None, *, auth=True, content_type=None, raw=None):
        path_only, _, query = path.partition("?")
        if raw is not None:
            body = raw
        elif payload is None:
            body = b""
        else:
            body = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_only,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": content_type or ("application/json" if payload is not None else ""),
            "wsgi.input": io.BytesIO(body),
        }
        if auth:
            environ["HTTP_X_INTERNAL_PROXY_SECRET"] = TEST_SECRET
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split(" ", 1)[0])
            captured["headers"] = dict(headers)

        response = b"".join(self.app(environ, start_response))
        return captured["status"], strict_json(response), captured["headers"]

    def expense(self, **changes):
        payload = {
            "fecha": "2026-04-10", "monto": 100, "categoria": "Hogar",
            "pagado_por": "JD",
        }
        payload.update(changes)
        return payload

    def income(self, **changes):
        payload = {
            "fecha": "2026-04-02", "monto": 100, "categoria": "Salario",
            "persona": "JD",
        }
        payload.update(changes)
        return payload

    def inventory(self, **changes):
        payload = {
            "nombre": "Notebook", "categoria": "Electrónica", "ubicacion": "Oficina",
            "valor_estimado": 500, "fecha_adquisicion": "2026-03-01",
        }
        payload.update(changes)
        return payload

    def fixed(self, **changes):
        payload = {
            "nombre": "Alquiler", "monto_estimado": 200,
            "periodicidad": "mensual", "responsable": "Común",
            "vigente_desde": "2026-04-15",
        }
        payload.update(changes)
        return payload


class ApiTest(WsgiApiTestCase):
    def test_auth_health_and_factory(self):
        for args in ((None, TEST_SECRET), (self.db_path, None), ("", TEST_SECRET)):
            with self.assertRaises(ValueError):
                create_app(*args)
        status, _, _ = self.request("GET", "/api/health", auth=False)
        self.assertEqual(status, 401)
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {
            "ok": True, "capabilities": ["expenses", "income", "fixed", "inventory"], "mode": "live",
        })
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_route_matching_valid_unknown_and_wrong_method(self):
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertNotIn("Allow", headers)

        status, _, headers = self.request("GET", "/api/no-such-route")
        self.assertEqual(status, 404)
        self.assertNotIn("Allow", headers)

        status, _, headers = self.request("POST", "/api/health")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET")

        status, _, headers = self.request("PUT", "/api/expenses")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET, POST")

        # A dynamic path must pass its captured id to the handler.
        self.assertEqual(self.request("DELETE", "/api/expenses/999")[0], 404)
        status, _, headers = self.request("GET", "/api/expenses/999")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "DELETE")

    def test_expense_installments_and_single_installment_delete(self):
        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(cuotas_total=3)
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual([row["fecha"] for row in rows], [
            "2026-04-10", "2026-05-10", "2026-06-10",
        ])
        self.assertEqual([row["cuota_nro"] for row in rows], [1, 2, 3])
        self.assertEqual([round(row["monto"], 2) for row in rows], [33.34, 33.33, 33.33])
        self.assertEqual({row["cuota_ref"] for row in rows}, {rows[0]["id"]})
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 10000)
        self.assertTrue(all(row["confirmado"] == 1 for row in rows))

        status, listed, _ = self.request("GET", "/api/expenses?month=2026-05")
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in listed["expenses"]], [rows[1]["id"]])
        status, _, _ = self.request("DELETE", f"/api/expenses/{rows[1]['id']}")
        self.assertEqual(status, 200)
        status, listed, _ = self.request("GET", "/api/expenses")
        self.assertEqual({row["id"] for row in listed["expenses"]}, {rows[0]["id"], rows[2]["id"]})
        status, _, _ = self.request("DELETE", f"/api/expenses/{rows[1]['id']}")
        self.assertEqual(status, 404)
        with db.get_connection(self.db_path) as conn:
            deleted = next(row for row in db.get_gastos(conn, incluir_borrados=True)
                           if row["id"] == rows[1]["id"])
            self.assertEqual(deleted["deleted_by"], "sesion_compartida:no_verificado")

    def test_saldar_expense(self):
        status, body, _ = self.request("POST", "/api/expenses", self.expense(pagado_por="JD"))
        self.assertEqual(status, 201)
        expense_id = body["expenses"][0]["id"]

        status, body, _ = self.request("POST", f"/api/expenses/{expense_id}/saldar")
        self.assertEqual(status, 200)
        self.assertEqual(body["expense"]["id"], expense_id)
        self.assertIsNotNone(body["expense"]["saldado"])

        status, listed, _ = self.request("GET", "/api/expenses")
        self.assertEqual(listed["expenses"][0]["saldado"], body["expense"]["saldado"])

        # Ya saldado: la segunda llamada no puede volver a aplicar el cambio.
        status, _, _ = self.request("POST", f"/api/expenses/{expense_id}/saldar")
        self.assertEqual(status, 409)

        self.assertEqual(self.request("POST", "/api/expenses/999/saldar")[0], 404)

    def test_saldar_expense_rejects_comun_and_deleted(self):
        status, body, _ = self.request("POST", "/api/expenses", self.expense(pagado_por="Común"))
        self.assertEqual(status, 201)
        comun_id = body["expenses"][0]["id"]
        status, _, _ = self.request("POST", f"/api/expenses/{comun_id}/saldar")
        self.assertEqual(status, 409)

        status, body, _ = self.request("POST", "/api/expenses", self.expense(pagado_por="Pinki"))
        self.assertEqual(status, 201)
        deleted_id = body["expenses"][0]["id"]
        self.assertEqual(self.request("DELETE", f"/api/expenses/{deleted_id}")[0], 200)
        status, _, _ = self.request("POST", f"/api/expenses/{deleted_id}/saldar")
        self.assertEqual(status, 409)

    def test_expense_installments_120_uses_original_total(self):
        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=120, cuotas_total=120)
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual(len(rows), 120)
        self.assertEqual([row["cuota_nro"] for row in rows], list(range(1, 121)))
        self.assertEqual([rows[0]["fecha"], rows[1]["fecha"], rows[-1]["fecha"]],
                         ["2026-04-10", "2026-05-10", "2036-03-10"])
        self.assertTrue(all(row["monto"] == 1 and row["monto"] > 0 for row in rows))
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 12000)
        self.assertEqual({row["cuota_ref"] for row in rows}, {rows[0]["id"]})
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], 120)

    def test_expense_installments_minimum_cent_and_indivisible_total(self):
        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=0.01, cuotas_total=1)
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(body["expenses"]), 1)
        self.assertEqual(round(body["expenses"][0]["monto"] * 100), 1)

        status, _, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=0.01, cuotas_total=2)
        )
        self.assertEqual(status, 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], 1)

        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=0.05, cuotas_total=2)
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual([round(row["monto"] * 100) for row in rows], [3, 2])
        self.assertTrue(all(row["monto"] > 0 for row in rows))
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 5)
        self.assertEqual([row["fecha"] for row in rows], ["2026-04-10", "2026-05-10"])

        # $0,08 en 5 cuotas: 8 centavos no son divisibles por 5, pero el
        # reparto en centavos enteros (divmod) da 5 filas positivas que
        # suman exacto, con el resto repartido en las primeras cuotas
        # (dictamen NO APTO e46265bb: antes la última cuota quedaba en $0).
        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=0.08, cuotas_total=5)
        )
        self.assertEqual(status, 201)
        rows = body["expenses"]
        self.assertEqual([round(row["monto"] * 100) for row in rows], [2, 2, 2, 1, 1])
        self.assertTrue(all(row["monto"] > 0 for row in rows))
        self.assertEqual(sum(round(row["monto"] * 100) for row in rows), 8)

    def test_repartir_cuotas_centavos_exhaustivo_1_a_500(self):
        """Prueba sintética exhaustiva del helper único (`db._repartir_cuotas_centavos`)
        usado por ambos expansores (web y Telegram): para cada monto de 1 a
        500 centavos y cada cantidad de cuotas de 1 a `min(120, centavos)`,
        el reparto tiene exactamente `cuotas` filas, todas positivas, que
        suman el total exacto y difieren entre sí a lo sumo en un centavo.
        Los asserts de suma comparan enteros (centavos), no floats."""
        for centavos in range(1, 501):
            monto_total = centavos / 100
            for cuotas in range(1, min(120, centavos) + 1):
                with self.subTest(centavos=centavos, cuotas=cuotas):
                    reparto = db._repartir_cuotas_centavos(monto_total, cuotas)
                    self.assertEqual(len(reparto), cuotas)
                    self.assertTrue(all(isinstance(valor, int) and valor > 0 for valor in reparto))
                    self.assertEqual(sum(reparto), centavos)
                    self.assertLessEqual(max(reparto) - min(reparto), 1)

    def test_expense_installments_roll_back_after_second_insert_fails(self):
        with db.get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TRIGGER reject_second_installment BEFORE INSERT ON gastos
                WHEN NEW.cuota_nro = 2
                BEGIN SELECT RAISE(ABORT, 'forced second installment failure'); END
            """)

        status, _, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=120, cuotas_total=120)
        )
        self.assertEqual(status, 409)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], 0)
            conn.execute("DROP TRIGGER reject_second_installment")

        status, body, _ = self.request(
            "POST", "/api/expenses", self.expense(monto=120, cuotas_total=120)
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(body["expenses"]), 120)

    def test_income_validation_update_and_summary(self):
        status, _, _ = self.request("POST", "/api/income", self.income(persona="Común"))
        self.assertEqual(status, 400)
        status, first, _ = self.request("POST", "/api/income", self.income(monto=300))
        self.assertEqual(status, 201)
        self.assertEqual(first["income"]["confirmado"], 1)
        status, _, _ = self.request("POST", "/api/income", self.income(persona="Pinki"))
        self.assertEqual(status, 201)
        status, _, _ = self.request("POST", "/api/expenses", self.expense())
        self.assertEqual(status, 201)

        status, summary, _ = self.request("GET", "/api/summary?month=2026-04")
        self.assertEqual(status, 200)
        self.assertEqual(summary["proportion"], {"JD": 75.0, "Pinki": 25.0})
        self.assertEqual(summary["debt_month"]["monto"], 25.0)
        self.assertEqual(summary["income_total"], 400)
        status, months, _ = self.request("GET", "/api/summary")
        self.assertEqual([row["month"] for row in months["months"]], ["2026-04"])
        income_id = first["income"]["id"]
        self.assertEqual(self.request("PATCH", f"/api/income/{income_id}", {})[0], 400)
        status, updated, _ = self.request("PATCH", f"/api/income/{income_id}", {"monto": 100})
        self.assertEqual(status, 200)
        self.assertEqual(updated["income"]["monto"], 100)
        self.assertEqual(self.request("GET", "/api/summary?month=2026-04")[1]["proportion"],
                         {"JD": 50.0, "Pinki": 50.0})
        self.assertEqual(self.request("PATCH", "/api/income/999", {"monto": 2})[0], 404)
        self.assertEqual(self.request("DELETE", f"/api/income/{income_id}")[0], 200)

    def test_income_delete_200_404_401_body_rejected_and_summary_changes(self):
        status, first, _ = self.request("POST", "/api/income", self.income(monto=300))
        self.assertEqual(status, 201)
        income_id = first["income"]["id"]
        status, _, _ = self.request("POST", "/api/income", self.income(monto=100, persona="Pinki"))
        self.assertEqual(status, 201)

        status, summary, _ = self.request("GET", "/api/summary?month=2026-04")
        self.assertEqual(status, 200)
        self.assertEqual(summary["income_total"], 400)
        self.assertEqual(summary["proportion"], {"JD": 75.0, "Pinki": 25.0})

        # DELETE no acepta cuerpo, igual que gastos.
        self.assertEqual(self.request("DELETE", f"/api/income/{income_id}", {"x": 1})[0], 400)
        # Sin el header de auth interno, 401 (antes de llegar al handler).
        self.assertEqual(self.request("DELETE", f"/api/income/{income_id}", auth=False)[0], 401)
        # Inexistente desde el principio.
        self.assertEqual(self.request("DELETE", "/api/income/999999")[0], 404)

        status, deleted, _ = self.request("DELETE", f"/api/income/{income_id}")
        self.assertEqual(status, 200)
        self.assertEqual(deleted, {"deleted": True, "id": income_id})

        # Doble baja sobre el mismo id: ya no existe para efectos públicos.
        self.assertEqual(self.request("DELETE", f"/api/income/{income_id}")[0], 404)

        status, listed, _ = self.request("GET", "/api/income")
        self.assertEqual(status, 200)
        self.assertNotIn(income_id, [row["id"] for row in listed["income"]])

        status, summary_after, _ = self.request("GET", "/api/summary?month=2026-04")
        self.assertEqual(status, 200)
        self.assertEqual(summary_after["income_total"], 100)
        self.assertEqual(summary_after["proportion"], {"JD": 0.0, "Pinki": 100.0})

        with db.get_connection(self.db_path) as conn:
            borrado = next(
                row for row in db.get_ingresos(conn, incluir_borrados=True) if row["id"] == income_id
            )
            self.assertIsNotNone(borrado["deleted_at"])
            self.assertEqual(borrado["deleted_by"], "sesion_compartida:no_verificado")
            auditoria = conn.execute(
                "SELECT * FROM auditoria WHERE tabla = 'ingresos' AND fila_id = ?", (income_id,)
            ).fetchone()
            self.assertIsNotNone(auditoria)
            self.assertEqual(auditoria["accion"], "baja")

    def test_fixed_versions_history_range_and_end(self):
        status, _, _ = self.request("POST", "/api/fixed", self.fixed(responsable=None))
        self.assertEqual(status, 400)
        status, created, _ = self.request("POST", "/api/fixed", self.fixed())
        self.assertEqual(status, 201)
        first_id = created["fixed"]["id"]
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-04-14")[1]["fixed"], [])
        self.assertEqual(self.request("GET", "/api/summary?month=2026-04")[1]["fixed_total_mensual"], 200)

        status, changed, _ = self.request("PATCH", f"/api/fixed/{first_id}", {
            "nombre": "Alquiler nuevo", "monto_estimado": 300,
            "periodicidad": "bimestral",
            "vigente_desde": "2026-05-01",
        })
        self.assertEqual(status, 200)
        second_id = changed["fixed"]["id"]
        self.assertEqual(changed["fixed"]["monto_mensual"], 150)
        self.assertEqual(changed["fixed"]["fijo_grupo_id"], first_id)
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-04-30")[1]["fixed"][0]["monto_estimado"], 200)
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-05-01")[1]["fixed"][0]["nombre"], "Alquiler nuevo")
        status, versions, _ = self.request("GET", "/api/fixed/versions")
        self.assertEqual(status, 200)
        self.assertEqual([v["id"] for v in versions["versions"]], [first_id, second_id])
        self.assertTrue(all("monto_mensual" in v for v in versions["versions"]))
        status, history, _ = self.request("GET", f"/api/fixed/{second_id}/historial")
        self.assertEqual(status, 200)
        self.assertEqual([v["id"] for v in history["historial"]], [first_id, second_id])
        self.assertEqual(history["historial"][0]["vigente_hasta"], "2026-04-30")
        status, range_body, _ = self.request("GET", "/api/fixed/range?fromISO=2026-04-20&toISO=2026-05-05")
        self.assertEqual(status, 200)
        self.assertEqual(len(range_body["range"][0]["tramos"]), 2)

        status, ended, _ = self.request("DELETE", f"/api/fixed/{first_id}", {"fecha_baja": "2026-06-01"})
        self.assertEqual(status, 200)
        self.assertEqual(ended["fixed"]["activo"], 0)
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-05-31")[1]["fixed"][0]["id"], second_id)
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-06-01")[1]["fixed"], [])
        self.assertEqual(self.request("DELETE", f"/api/fixed/{first_id}", {"fecha_baja": "2026-06-02"})[0], 409)

    def test_fixed_common_split_is_versioned_and_preserved(self):
        for pct in (0, 100, 25):
            with self.subTest(proporcion_jd=pct):
                status, created, _ = self.request("POST", "/api/fixed", self.fixed(
                    nombre=f"Fijo {pct}", tipo_proporcion="custom", proporcion_jd=pct,
                ))
                self.assertEqual(status, 201)
                self.assertEqual(created["fixed"]["tipo_proporcion"], "custom")
                self.assertEqual(created["fixed"]["proporcion_jd"], pct)

        status, created, _ = self.request("POST", "/api/fixed", self.fixed(
            tipo_proporcion="dinamico",
        ))
        self.assertEqual(status, 201)
        self.assertEqual((created["fixed"]["tipo_proporcion"], created["fixed"]["proporcion_jd"]),
                         ("dinamica", None))
        fixed_id = self.request("GET", "/api/fixed/versions")[1]["versions"][2]["id"]
        status, renamed, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-05-01", "nombre": "Fijo renombrado",
        })
        self.assertEqual(status, 200)
        self.assertEqual((renamed["fixed"]["tipo_proporcion"], renamed["fixed"]["proporcion_jd"]),
                         ("custom", 25))
        status, changed, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-06-01", "proporcion_jd": 0,
        })
        self.assertEqual(status, 200)
        self.assertEqual(changed["fixed"]["proporcion_jd"], 0)
        status, dynamic, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-07-01", "tipo_proporcion": "dinamica",
            "proporcion_jd": None,
        })
        self.assertEqual(status, 200)
        self.assertEqual((dynamic["fixed"]["tipo_proporcion"], dynamic["fixed"]["proporcion_jd"]),
                         ("dinamica", None))
        history = self.request("GET", f"/api/fixed/{fixed_id}/historial")[1]["historial"]
        self.assertEqual([row["proporcion_jd"] for row in history], [25, 25, 0, None])
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-05-15")[1]["fixed"][2]["proporcion_jd"], 25)
        self.assertEqual(self.request("GET", "/api/fixed/range?fromISO=2026-05-01&toISO=2026-06-30")[1]["range"][2]["tramos"][-1]["proporcion_jd"], 0)
        with db.get_connection(self.db_path) as conn:
            audit = conn.execute("SELECT antes_json, despues_json FROM auditoria WHERE fila_id = ? AND accion = 'version'",
                                 (changed["fixed"]["id"],)).fetchone()
            self.assertEqual(json.loads(audit["antes_json"])["proporcion_jd"], 25)
            self.assertEqual(json.loads(audit["despues_json"])["proporcion_jd"], 0)

    def test_fixed_split_invalid_requests_do_not_persist(self):
        invalid = (
            {"tipo_proporcion": "custom"},
            {"tipo_proporcion": "custom", "proporcion_jd": None},
            {"tipo_proporcion": "custom", "proporcion_jd": True},
            {"tipo_proporcion": "custom", "proporcion_jd": float("nan")},
            {"tipo_proporcion": "custom", "proporcion_jd": -0.01},
            {"tipo_proporcion": "custom", "proporcion_jd": 100.01},
            {"tipo_proporcion": "dinamica", "proporcion_jd": 25},
            {"tipo_proporcion": None},
            {"tipo_proporcion": "otro"},
            {"responsable": "JD", "tipo_proporcion": "custom", "proporcion_jd": 25},
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                self.assertEqual(self.request("POST", "/api/fixed", self.fixed(**fields))[0], 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 0)

        fixed_id = self.request("POST", "/api/fixed", self.fixed(
            tipo_proporcion="custom", proporcion_jd=25,
        ))[1]["fixed"]["id"]
        for fields in invalid[:-1]:
            with self.subTest(patch=fields):
                self.assertEqual(self.request("PATCH", f"/api/fixed/{fixed_id}", {
                    "vigente_desde": "2026-05-01", **fields,
                })[0], 400)
        self.assertEqual(self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-05-01", "nombre": "Alquiler",
        })[0], 400)
        dynamic_id = self.request("POST", "/api/fixed", self.fixed(
            nombre="Internet", tipo_proporcion="dinamica", proporcion_jd=None,
        ))[1]["fixed"]["id"]
        self.assertEqual(self.request("PATCH", f"/api/fixed/{dynamic_id}", {
            "vigente_desde": "2026-05-01", "tipo_proporcion": "custom",
        })[0], 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auditoria WHERE tabla = 'gastos_fijos'").fetchone()[0], 2)

    def test_fixed_personal_split_and_return_to_common(self):
        fixed_id = self.request("POST", "/api/fixed", self.fixed(
            tipo_proporcion="custom", proporcion_jd=25,
        ))[1]["fixed"]["id"]
        status, personal, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-05-01", "responsable": "Pinki",
        })
        self.assertEqual(status, 200)
        self.assertEqual((personal["fixed"]["tipo_proporcion"], personal["fixed"]["proporcion_jd"]),
                         (None, 0))
        status, common, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-06-01", "responsable": "Común",
        })
        self.assertEqual(status, 200)
        self.assertEqual((common["fixed"]["tipo_proporcion"], common["fixed"]["proporcion_jd"]),
                         ("dinamica", None))
        history = self.request("GET", f"/api/fixed/{fixed_id}/historial")[1]["historial"]
        self.assertEqual([row["proporcion_jd"] for row in history], [25, 0, None])
        self.assertEqual(self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-07-01", "tipo_proporcion": "custom",
        })[0], 400)
        status, custom_again, _ = self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-07-01", "tipo_proporcion": "custom", "proporcion_jd": 100,
        })
        self.assertEqual(status, 200)
        self.assertEqual(custom_again["fixed"]["proporcion_jd"], 100)
        status, jd, _ = self.request("POST", "/api/fixed", self.fixed(responsable="JD"))
        self.assertEqual(status, 201)
        self.assertEqual((jd["fixed"]["tipo_proporcion"], jd["fixed"]["proporcion_jd"]),
                         (None, 100))

    def test_http_boundaries(self):
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(fecha="2026-02-30"))[0], 400)
        self.assertEqual(self.request("POST", "/api/income", self.income(monto=True))[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(monto=float("inf")))[0], 400)
        self.assertEqual(self.request("POST", "/api/fixed", self.fixed(monto_estimado=True))[0], 400)
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-02-30")[0], 400)
        self.assertEqual(self.request("GET", "/api/expenses?month=2026-2")[0], 400)
        self.assertEqual(self.request("GET", "/api/summary?month=2026-13")[0], 400)
        self.assertEqual(self.request("GET", "/api/fixed/range?fromISO=2026-05-01&toISO=2026-04-01")[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(actor="JD"))[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(confirmado=True))[0], 400)
        self.assertEqual(self.request("GET", "/api/health?extra=1")[0], 400)
        self.assertEqual(self.request("GET", "/api/expenses?month=2026-04&month=2026-05")[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", raw=b"{}", content_type="text/plain")[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", raw=b'{"monto":1,"monto":2}', content_type="application/json")[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", raw=b"x" * 65537, content_type="application/json")[0], 413)
        self.assertEqual(self.request("POST", "/api/expenses", raw=b"x" * 65537, content_type="application/json", auth=False)[0], 401)
        self.assertEqual(self.request("DELETE", "/api/expenses/999")[0], 404)
        self.assertEqual(self.request("GET", "/api/fixed/999/historial")[0], 404)
        self.assertEqual(self.request("GET", "/api/no-such-route")[0], 404)

    def test_expense_proporcion_custom_fuera_de_rango_rechazada(self):
        for proporcion_jd, proporcion_pinki in ((120, -20), (-5, 105)):
            with self.subTest(proporcion_jd=proporcion_jd):
                status, _, _ = self.request(
                    "POST", "/api/expenses",
                    self.expense(
                        tipo_proporcion="custom",
                        proporcion_jd=proporcion_jd, proporcion_pinki=proporcion_pinki,
                    ),
                )
                self.assertEqual(status, 400)

    def test_expense_proporcion_custom_no_numerica_o_nan_rechazada(self):
        for proporcion_jd, proporcion_pinki in ((float("nan"), 100), ("50", 50)):
            with self.subTest(proporcion_jd=proporcion_jd):
                status, _, _ = self.request(
                    "POST", "/api/expenses",
                    self.expense(
                        tipo_proporcion="custom",
                        proporcion_jd=proporcion_jd, proporcion_pinki=proporcion_pinki,
                    ),
                )
                self.assertEqual(status, 400)

    def test_expense_proporcion_personal_100_0_aceptada(self):
        status, body, _ = self.request(
            "POST", "/api/expenses",
            self.expense(tipo_proporcion="custom", proporcion_jd=100, proporcion_pinki=0),
        )
        self.assertEqual(status, 201)
        gasto = body["expenses"][0]
        self.assertEqual((gasto["proporcion_jd"], gasto["proporcion_pinki"]), (100, 0))

    def test_money_rejected_before_write_and_retry_does_not_duplicate(self):
        cases = (
            ("POST", "/api/expenses", self.expense(monto=1e308), "gastos"),
            ("POST", "/api/expenses", self.expense(monto=1.001), "gastos"),
            ("POST", "/api/income", self.income(monto=1e308), "ingresos"),
            ("POST", "/api/fixed", self.fixed(monto_estimado=1e308), "gastos_fijos"),
        )
        for method, path, payload, table in cases:
            with self.subTest(path=path, payload=payload):
                for _ in range(2):
                    self.assertEqual(self.request(method, path, payload)[0], 400)
                with db.get_connection(self.db_path) as conn:
                    self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

        income_id = self.request("POST", "/api/income", self.income())[1]["income"]["id"]
        fixed_id = self.request("POST", "/api/fixed", self.fixed())[1]["fixed"]["id"]
        self.assertEqual(self.request("PATCH", f"/api/income/{income_id}", {"monto": 1e308})[0], 400)
        self.assertEqual(self.request("PATCH", f"/api/fixed/{fixed_id}", {
            "vigente_desde": "2026-05-01", "monto_estimado": 1e308,
        })[0], 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0], 1)

    def test_strict_json_and_invalid_legacy_summary(self):
        self.assertEqual(self.request("POST", "/api/income", self.income(monto=300))[0], 201)
        self.assertEqual(self.request("POST", "/api/income", self.income(persona="Pinki"))[0], 201)
        self.assertEqual(self.request("GET", "/api/summary?month=2026-04")[1]["proportion"],
                         {"JD": 75.0, "Pinki": 25.0})
        with db.get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO ingresos (fecha, monto, categoria, persona, created_at) VALUES (?, ?, ?, ?, ?)",
                ("2026-04-03", 1e308, "Salario", "JD", "2026-04-03T00:00:00"),
            )
            conn.commit()
        status, body, _ = self.request("GET", "/api/summary?month=2026-04")
        self.assertEqual(status, 422)
        self.assertIn("error", body)
        self.assertNotIn("proportion", body)
        self.assertEqual(self.request("GET", "/api/summary")[0], 422)
        self.assertEqual(self.request("GET", "/api/income")[0], 422)

    def test_bounded_aggregate_never_returns_false_ratio(self):
        self.assertEqual(self.request("POST", "/api/income", self.income(monto=1e12))[0], 201)
        self.assertEqual(self.request("POST", "/api/income", self.income(monto=1e12, persona="Pinki"))[0], 201)
        status, body, _ = self.request("GET", "/api/summary?month=2026-04")
        self.assertEqual(status, 422)
        self.assertNotIn("proportion", body)
        self.assertNotIn("income_total", body)

    def test_query_whitelist_on_every_write(self):
        expense_id = self.request("POST", "/api/expenses", self.expense())[1]["expenses"][0]["id"]
        income_id = self.request("POST", "/api/income", self.income())[1]["income"]["id"]
        fixed_id = self.request("POST", "/api/fixed", self.fixed())[1]["fixed"]["id"]
        operations = (
            ("POST", "/api/expenses", self.expense()),
            ("DELETE", f"/api/expenses/{expense_id}", None),
            ("POST", "/api/income", self.income()),
            ("PATCH", f"/api/income/{income_id}", {"monto": 200}),
            ("DELETE", f"/api/income/{income_id}", None),
            ("POST", "/api/fixed", self.fixed()),
            ("PATCH", f"/api/fixed/{fixed_id}", {"vigente_desde": "2026-05-01", "monto_estimado": 300}),
            ("DELETE", f"/api/fixed/{fixed_id}", {"fecha_baja": "2026-06-01"}),
        )
        with db.get_connection(self.db_path) as conn:
            before = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("gastos", "ingresos", "gastos_fijos", "auditoria")]
        for method, path, payload in operations:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path + "?unexpected=1", payload)[0], 400)
                self.assertEqual(self.request(method, path + "?unexpected=1&unexpected=2", payload)[0], 400)
        with db.get_connection(self.db_path) as conn:
            after = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("gastos", "ingresos", "gastos_fijos", "auditoria")]
            self.assertEqual(after, before)
            self.assertIsNone(conn.execute("SELECT deleted_at FROM gastos WHERE id = ?", (expense_id,)).fetchone()[0])

    def test_same_day_history_keeps_versions_without_empty_range(self):
        first_id = self.request("POST", "/api/fixed", self.fixed())[1]["fixed"]["id"]
        second_id = self.request("PATCH", f"/api/fixed/{first_id}", {
            "vigente_desde": "2026-04-15", "monto_estimado": 300,
        })[1]["fixed"]["id"]
        third_id = self.request("PATCH", f"/api/fixed/{first_id}", {
            "vigente_desde": "2026-04-15", "monto_estimado": 400,
        })[1]["fixed"]["id"]
        history = self.request("GET", f"/api/fixed/{first_id}/historial")[1]["historial"]
        self.assertEqual([row["id"] for row in history], [first_id, second_id, third_id])
        self.assertEqual([row["supersedida_mismo_dia"] for row in history], [True, True, False])
        self.assertEqual([row["tiene_intervalo_vigencia"] for row in history], [False, False, True])
        self.assertTrue(all(row["vigente_hasta"] is None for row in history))
        tramos = self.request("GET", "/api/fixed/range?fromISO=2026-04-15&toISO=2026-04-30")[1]["range"][0]["tramos"]
        self.assertEqual([row["id"] for row in tramos], [third_id])
        self.assertEqual(self.request("GET", "/api/fixed?dateISO=2026-04-16")[1]["fixed"][0]["id"], third_id)
        self.assertEqual(self.request("DELETE", f"/api/fixed/{first_id}", {"fecha_baja": "2026-05-01"})[0], 200)
        self.assertEqual(self.request("PATCH", f"/api/fixed/{first_id}", {
            "vigente_desde": "2026-05-02", "monto_estimado": 500,
        })[0], 409)

    def test_operational_limits_before_sqlite_or_expansion(self):
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(cuotas_total=1000000))[0], 400)
        self.assertEqual(self.request("POST", "/api/expenses", self.expense(cuotas_total=121))[0], 400)
        huge_id = "9" * 5000
        self.assertEqual(self.request("DELETE", f"/api/expenses/{huge_id}")[0], 400)
        self.assertEqual(self.request("PATCH", f"/api/income/{huge_id}", {"monto": 2})[0], 400)
        self.assertEqual(self.request("DELETE", f"/api/income/{huge_id}")[0], 400)
        self.assertEqual(self.request("GET", f"/api/fixed/{huge_id}/historial")[0], 400)
        self.assertEqual(self.request("DELETE", f"/api/fixed/{huge_id}", {"fecha_baja": "2026-05-01"})[0], 400)
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0], 0)

    def test_concurrent_wsgi_delete_has_one_winner_and_one_audit(self):
        expense_id = self.request("POST", "/api/expenses", self.expense())[1]["expenses"][0]["id"]
        gate = threading.Barrier(3)
        both_open = threading.Barrier(2)
        original_get_connection = self.app._get_connection
        opened_connections = []

        def two_connections():
            conn = original_get_connection()
            opened_connections.append(conn)
            both_open.wait(timeout=5)
            return conn

        self.app._get_connection = two_connections

        def delete_request():
            gate.wait(timeout=5)
            return self.request("DELETE", f"/api/expenses/{expense_id}")[0]

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(delete_request) for _ in range(2)]
                gate.wait(timeout=5)
                statuses = [future.result(timeout=10) for future in futures]
        finally:
            self.app._get_connection = original_get_connection
        self.assertEqual(len(opened_connections), 2)
        self.assertIsNot(opened_connections[0], opened_connections[1])
        self.assertEqual(sorted(statuses), [200, 404])
        with db.get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auditoria WHERE tabla = 'gastos' AND accion = 'baja' AND fila_id = ?", (expense_id,)).fetchone()[0], 1)

    def test_in_memory_is_shared_across_request_connections(self):
        app = create_app(":memory:", TEST_SECRET)
        previous = self.app
        try:
            self.app = app
            self.assertEqual(self.request("POST", "/api/income", self.income())[0], 201)
            self.assertEqual(len(self.request("GET", "/api/income")[1]["income"]), 1)
        finally:
            self.app = previous
            app.close()

    def test_legacy_migration_only_in_temporary_database(self):
        legacy_path = str(Path(self.tempdir.name) / "legacy.sqlite")
        conn = sqlite3.connect(legacy_path)
        try:
            conn.execute("""CREATE TABLE gastos_fijos (
                id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, monto_estimado REAL NOT NULL,
                periodicidad TEXT NOT NULL, dia_vencimiento INTEGER, categoria TEXT,
                subcategoria TEXT, activo INTEGER NOT NULL, ultima_actualizacion TEXT NOT NULL,
                responsable TEXT, tipo_proporcion TEXT, proporcion_jd REAL, medio_pago TEXT
            )""")
            conn.execute("""INSERT INTO gastos_fijos
                (id, nombre, monto_estimado, periodicidad, activo, ultima_actualizacion)
                VALUES (1, 'Internet', 10, 'mensual', 1, '2026-03-01T00:00:00')""")
            conn.commit()
        finally:
            conn.close()
        app = create_app(legacy_path, TEST_SECRET)
        try:
            with db.get_connection(legacy_path) as migrated:
                row = db.get_gastos_fijos(migrated, solo_activos=False)[0]
                self.assertEqual(row["fijo_grupo_id"], 1)
                self.assertEqual(row["vigente_desde"], "2026-03-01")
                self.assertIsNone(row["responsable"])
                self.assertIsNone(row["tipo_proporcion"])
        finally:
            app.close()

    def test_categories_empty_grouped_ordered_deduped_and_validated(self):
        # Base sin categorías: lista vacía, no 404 ni error.
        status, body, _ = self.request("GET", "/api/categories?tipo=Gasto")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"categories": []})

        with db.get_connection(self.db_path) as conn:
            for tipo, categoria, subcategoria in (
                ("Gasto", "Hogar", "Alquiler"),
                ("Gasto", "Comida", "Supermercado"),
                ("Gasto", "Hogar", "Expensas"),
                ("Gasto", "Hogar", "Alquiler"),  # duplicado, debe deduplicarse
                ("Gasto", "Hogar", None),  # sin subcategoría, no debe agregar nada
                ("Gasto", "Transporte", ""),  # subcategoría vacía, se ignora
                ("Gasto", "Transporte", "Nafta"),
                ("Ingreso", "Salario", None),  # otro tipo, no debe aparecer
            ):
                conn.execute(
                    "INSERT INTO categorias (tipo, categoria, subcategoria, creada_en) "
                    "VALUES (?, ?, ?, '2026-01-01T00:00:00')",
                    (tipo, categoria, subcategoria),
                )
            conn.commit()

        status, body, _ = self.request("GET", "/api/categories?tipo=Gasto")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"categories": [
            {"categoria": "Hogar", "subcategorias": ["Alquiler", "Expensas"]},
            {"categoria": "Comida", "subcategorias": ["Supermercado"]},
            {"categoria": "Transporte", "subcategorias": ["Nafta"]},
        ]})

        status, body, _ = self.request("GET", "/api/categories?tipo=Ingreso")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"categories": [{"categoria": "Salario", "subcategorias": []}]})

        status, body, _ = self.request("GET", "/api/categories?tipo=Inversión")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"categories": []})

        # tipo obligatorio y limitado a los tres valores; falta o inválido -> 422.
        for query in ("", "?tipo=", "?tipo=gasto", "?tipo=Factura"):
            status, _, _ = self.request("GET", f"/api/categories{query}")
            self.assertEqual(status, 422)

        # Query desconocida: mismo rechazo (400) que el resto de la API.
        self.assertEqual(self.request("GET", "/api/categories?tipo=Gasto&extra=1")[0], 400)
        self.assertEqual(self.request("GET", "/api/categories?tipo=Gasto&tipo=Ingreso")[0], 400)

        # Auth por el mismo header que todas las rutas.
        self.assertEqual(self.request("GET", "/api/categories?tipo=Gasto", auth=False)[0], 401)

    def test_local_http_roundtrip(self):
        server = make_server("127.0.0.1", 0, self.app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("GET", "/api/health")
                unauthorized = conn.getresponse()
                self.assertEqual(unauthorized.status, 401)
                unauthorized.read()
                conn.request("GET", "/api/health", headers={"X-Internal-Proxy-Secret": TEST_SECRET})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["ok"])
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
