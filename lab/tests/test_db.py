import unittest

import db


class TestDb(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_init_db_crea_tablas(self):
        tablas = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("gastos", tablas)
        self.assertIn("estado_conversacional", tablas)

    def test_insert_gasto_confirmado_ok(self):
        gasto_id = db.insert_gasto(
            self.conn,
            {
                "monto": 3000.0,
                "categoria": "Comida",
                "subcategoria": "Supermercado",
                "descripcion_original": "gasté 3000 en el super con la tarjeta",
                "medio_pago": "Tarjeta",
                "chat_id": "chat-1",
                "confirmado": True,
            },
        )
        self.assertIsInstance(gasto_id, int)

        gastos = db.get_gastos(self.conn, chat_id="chat-1")
        self.assertEqual(len(gastos), 1)
        self.assertEqual(gastos[0]["monto"], 3000.0)
        self.assertEqual(gastos[0]["confirmado"], 1)
        self.assertEqual(gastos[0]["moneda"], "ARS")
        self.assertEqual(gastos[0]["pagado_por"], "Común")
        self.assertEqual(gastos[0]["origen"], "texto")
        self.assertEqual(
            gastos[0]["descripcion_original"], "gasté 3000 en el super con la tarjeta"
        )

    def test_insert_gasto_sin_confirmar_falla(self):
        with self.assertRaises(ValueError):
            db.insert_gasto(
                self.conn,
                {
                    "monto": 100.0,
                    "chat_id": "chat-1",
                    "confirmado": False,
                },
            )

        with self.assertRaises(ValueError):
            db.insert_gasto(self.conn, {"monto": 100.0, "chat_id": "chat-1"})

        self.assertEqual(db.get_gastos(self.conn), [])

    def test_estado_conversacional_set_get_clear(self):
        self.assertIsNone(db.get_estado(self.conn, "chat-2"))

        db.set_estado(
            self.conn,
            "chat-2",
            estado="esperando_campo",
            campo_pendiente="monto",
            payload_parcial={"medio_pago": "Efectivo"},
            mensaje_original="pagué en efectivo",
        )
        estado = db.get_estado(self.conn, "chat-2")
        self.assertEqual(estado["estado"], "esperando_campo")
        self.assertEqual(estado["campo_pendiente"], "monto")
        self.assertEqual(estado["payload_parcial"], {"medio_pago": "Efectivo"})
        self.assertEqual(estado["mensaje_original"], "pagué en efectivo")
        self.assertEqual(estado["intent_detectado"], "gasto")
        self.assertEqual(estado["telegram_chat_id"], "chat-2")

        db.set_estado(
            self.conn,
            "chat-2",
            estado="esperando_confirmacion",
            payload_parcial={"monto": 500},
            mensaje_original="pagué en efectivo",
        )
        estado = db.get_estado(self.conn, "chat-2")
        self.assertEqual(estado["estado"], "esperando_confirmacion")
        self.assertIsNone(estado["campo_pendiente"])

        db.clear_estado(self.conn, "chat-2")
        self.assertIsNone(db.get_estado(self.conn, "chat-2"))


if __name__ == "__main__":
    unittest.main()
