"""Tests de tarjetas y reparto (tipo_proporcion / proporcion_jd / proporcion_pinki)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402


class TestTarjetas(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_init_db_crea_tabla_tarjetas(self):
        tablas = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("tarjetas", tablas)

    def test_insert_y_get_tarjeta(self):
        db.insert_tarjeta(
            self.conn,
            {
                "id": "TC1",
                "nombre": "Visa",
                "tipo": "Crédito",
                "banco": "BNA",
                "titular": "Común",
                "dia_cierre": 10,
                "dia_vencimiento": 20,
            },
        )
        tarjetas = db.get_tarjetas(self.conn)
        self.assertEqual(len(tarjetas), 1)
        self.assertEqual(tarjetas[0]["id"], "TC1")
        self.assertEqual(tarjetas[0]["titular"], "Común")
        self.assertEqual(tarjetas[0]["es_default_dinamico"], 0)

    def test_get_tarjetas_filtra_por_titular(self):
        db.insert_tarjeta(
            self.conn,
            {"id": "TC1", "nombre": "Visa", "tipo": "Crédito", "titular": "Común"},
        )
        db.insert_tarjeta(
            self.conn,
            {"id": "TD1", "nombre": "Débito", "tipo": "Débito", "titular": "JD"},
        )
        self.assertEqual(len(db.get_tarjetas(self.conn, titular="JD")), 1)
        self.assertEqual(len(db.get_tarjetas(self.conn)), 2)

    def test_get_tarjeta_default_dinamico(self):
        self.assertIsNone(db.get_tarjeta_default_dinamico(self.conn))

        db.insert_tarjeta(
            self.conn,
            {
                "id": "TC1",
                "nombre": "Visa",
                "tipo": "Crédito",
                "banco": "BNA",
                "titular": "Común",
                "es_default_dinamico": True,
            },
        )
        default = db.get_tarjeta_default_dinamico(self.conn)
        self.assertIsNotNone(default)
        self.assertEqual(default["id"], "TC1")

    def test_insert_y_get_tarjeta_uso_compartido(self):
        db.insert_tarjeta(
            self.conn,
            {
                "id": "TC1",
                "nombre": "Visa",
                "tipo": "Crédito",
                "banco": "BNA",
                "titular": "JD",
                "dia_cierre": 10,
                "dia_vencimiento": 20,
                "uso_compartido": True,
            },
        )
        tarjetas = db.get_tarjetas(self.conn)
        self.assertEqual(len(tarjetas), 1)
        self.assertEqual(tarjetas[0]["titular"], "JD")
        self.assertEqual(tarjetas[0]["uso_compartido"], 1)

    def test_uso_compartido_default_false_si_no_se_pasa(self):
        db.insert_tarjeta(
            self.conn,
            {"id": "TD1", "nombre": "Débito", "tipo": "Débito", "titular": "Pinki"},
        )
        tarjetas = db.get_tarjetas(self.conn)
        self.assertEqual(tarjetas[0]["uso_compartido"], 0)

    def test_solo_una_tarjeta_puede_ser_default_dinamico(self):
        db.insert_tarjeta(
            self.conn,
            {
                "id": "TC1",
                "nombre": "Visa",
                "tipo": "Crédito",
                "titular": "Común",
                "es_default_dinamico": True,
            },
        )
        with self.assertRaises(ValueError):
            db.insert_tarjeta(
                self.conn,
                {
                    "id": "TC2",
                    "nombre": "Mastercard",
                    "tipo": "Crédito",
                    "titular": "JD",
                    "es_default_dinamico": True,
                },
            )


class TestInsertGastoReparto(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _gasto_base(self, **overrides):
        gasto = {
            "monto": 17000.0,
            "categoria": "Entretenimiento",
            "descripcion_original": "cine con pinki",
            "confirmado": True,
        }
        gasto.update(overrides)
        return gasto

    def test_dinamico_sin_proporciones_ok(self):
        gasto_id = db.insert_gasto(self.conn, self._gasto_base())
        gastos = db.get_gastos(self.conn)
        self.assertEqual(gastos[0]["id"], gasto_id)
        self.assertEqual(gastos[0]["tipo_proporcion"], "dinamico")
        self.assertIsNone(gastos[0]["proporcion_jd"])
        self.assertIsNone(gastos[0]["proporcion_pinki"])
        self.assertIsNone(gastos[0]["tarjeta_id"])

    def test_custom_50_50_ok(self):
        db.insert_gasto(
            self.conn,
            self._gasto_base(
                tipo_proporcion="custom", proporcion_jd=50, proporcion_pinki=50
            ),
        )
        gastos = db.get_gastos(self.conn)
        self.assertEqual(gastos[0]["tipo_proporcion"], "custom")
        self.assertEqual(gastos[0]["proporcion_jd"], 50)
        self.assertEqual(gastos[0]["proporcion_pinki"], 50)

    def test_custom_100_0_ok(self):
        db.insert_gasto(
            self.conn,
            self._gasto_base(
                tipo_proporcion="custom", proporcion_jd=100, proporcion_pinki=0
            ),
        )
        gastos = db.get_gastos(self.conn)
        self.assertEqual(gastos[0]["proporcion_jd"], 100)
        self.assertEqual(gastos[0]["proporcion_pinki"], 0)

    def test_custom_que_no_suma_100_falla(self):
        with self.assertRaises(ValueError):
            db.insert_gasto(
                self.conn,
                self._gasto_base(
                    tipo_proporcion="custom", proporcion_jd=60, proporcion_pinki=30
                ),
            )
        self.assertEqual(db.get_gastos(self.conn), [])

    def test_dinamico_con_proporciones_seteadas_falla(self):
        with self.assertRaises(ValueError):
            db.insert_gasto(
                self.conn,
                self._gasto_base(
                    tipo_proporcion="dinamico", proporcion_jd=50, proporcion_pinki=50
                ),
            )
        self.assertEqual(db.get_gastos(self.conn), [])

    def test_insert_gasto_con_tarjeta_id(self):
        db.insert_tarjeta(
            self.conn,
            {"id": "TC1", "nombre": "Visa", "tipo": "Crédito", "titular": "Común"},
        )
        db.insert_gasto(self.conn, self._gasto_base(tarjeta_id="TC1"))
        gastos = db.get_gastos(self.conn)
        self.assertEqual(gastos[0]["tarjeta_id"], "TC1")


if __name__ == "__main__":
    unittest.main()
