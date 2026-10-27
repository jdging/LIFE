"""Categoría de gastos fijos (brief t_38a7253f, punto 5): alta, versionado y
validación. La API web (ver test_api.py) ya cubre el contrato HTTP; estos
tests cubren la capa de dominio directamente.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import validaciones  # noqa: E402


class TestValidarGastoFijoCategoria(unittest.TestCase):
    def _payload(self, **changes):
        payload = {
            "nombre": "Alquiler", "monto_estimado": 100.0,
            "periodicidad": "mensual", "vigente_desde": "2026-01-01",
        }
        payload.update(changes)
        return payload

    def test_categoria_ausente_o_none_es_valida(self):
        self.assertEqual(validaciones.validar_gasto_fijo(self._payload()), [])
        self.assertEqual(validaciones.validar_gasto_fijo(self._payload(categoria=None)), [])

    def test_categoria_string_no_vacio_es_valida(self):
        self.assertEqual(validaciones.validar_gasto_fijo(self._payload(categoria="Hogar")), [])

    def test_categoria_vacia_o_no_string_es_invalida(self):
        for bad in ("", "   ", 123, True, []):
            with self.subTest(categoria=bad):
                errores = validaciones.validar_gasto_fijo(self._payload(categoria=bad))
                self.assertTrue(any("categoria" in e for e in errores))


class TestCrearVersionFijoCategoria(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_alta_sin_categoria_queda_null_como_fijo_legacy(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01",
        })
        fila = db.get_gastos_fijos(self.conn)[0]
        self.assertEqual(fila["id"], primero)
        self.assertIsNone(fila["categoria"])

    def test_alta_con_categoria_la_persiste(self):
        db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar",
        })
        fila = db.get_gastos_fijos(self.conn)[0]
        self.assertEqual(fila["categoria"], "Hogar")

    def test_version_nueva_sin_categoria_hereda_la_anterior(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, monto_nuevo=220000.0, vigente_desde="2026-02-01",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["categoria"], "Hogar")

    def test_version_nueva_puede_asignar_categoria_a_un_fijo_sin_ella(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", categoria="Servicios",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["categoria"], "Servicios")
        # La versión original, sin categoría, queda intacta en el historial.
        original = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == primero)
        self.assertIsNone(original["categoria"])

    def test_version_nueva_puede_cambiar_categoria_existente(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", categoria="Vivienda",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["categoria"], "Vivienda")

    def test_cambiar_solo_la_categoria_cuenta_como_cambio_real(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", categoria="Vivienda",
        )
        self.assertNotEqual(primero, segundo)
        with self.assertRaises(db.FixedNoChangeError):
            db.crear_version_fijo(self.conn, segundo, vigente_desde="2026-03-01", categoria="Vivienda")

    def test_baja_conserva_la_categoria_vigente(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar",
        })
        baja_id = db.dar_baja_fijo(self.conn, primero, "2026-03-01", "test")
        baja = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == baja_id)
        self.assertEqual(baja["categoria"], "Hogar")


if __name__ == "__main__":
    unittest.main()
