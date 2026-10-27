"""Categoría de gastos fijos (brief t_38a7253f, punto 5): alta, versionado y
validación. La API web (ver test_api.py) ya cubre el contrato HTTP; estos
tests cubren la capa de dominio directamente.

`subcategoria` (brief t_38a7253f F1b, hallazgo A) sigue exactamente las
mismas reglas que `categoria` -- ver `TestValidarGastoFijoSubcategoria` y
`TestCrearVersionFijoSubcategoria` abajo, espejo de las de categoría.

Semántica omitido/null y regla cruzada "no puede quedar subcategoria sin
categoria" (brief t_38a7253f F1b-fix2, hallazgo 2 del revisor) también
cubiertas en esas mismas clases.
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


class TestValidarGastoFijoSubcategoria(unittest.TestCase):
    def _payload(self, **changes):
        payload = {
            "nombre": "Alquiler", "monto_estimado": 100.0,
            "periodicidad": "mensual", "vigente_desde": "2026-01-01",
        }
        payload.update(changes)
        return payload

    def test_subcategoria_ausente_o_none_es_valida(self):
        self.assertEqual(validaciones.validar_gasto_fijo(self._payload()), [])
        self.assertEqual(validaciones.validar_gasto_fijo(self._payload(subcategoria=None)), [])

    def test_subcategoria_string_no_vacio_es_valida(self):
        # Junto con su categoria: sola, sin categoria, es la regla cruzada
        # que se prueba en test_subcategoria_sin_categoria_es_invalida.
        self.assertEqual(
            validaciones.validar_gasto_fijo(self._payload(categoria="Hogar", subcategoria="Alquiler")), [])

    def test_subcategoria_vacia_o_no_string_es_invalida(self):
        for bad in ("", "   ", 123, True, []):
            with self.subTest(subcategoria=bad):
                errores = validaciones.validar_gasto_fijo(self._payload(categoria="Hogar", subcategoria=bad))
                self.assertTrue(any("subcategoria" in e for e in errores))

    def test_subcategoria_sin_categoria_es_invalida(self):
        """Regla cruzada (brief t_38a7253f F1b-fix2, hallazgo 2 del revisor):
        no puede quedar `subcategoria` asignada sin `categoria`."""
        errores = validaciones.validar_gasto_fijo(self._payload(subcategoria="Alquiler"))
        self.assertTrue(any("subcategoria" in e and "categoria" in e for e in errores))
        # Explícitamente en conflicto (categoria=None + subcategoria con valor) también.
        errores_explicito = validaciones.validar_gasto_fijo(
            self._payload(categoria=None, subcategoria="Alquiler"))
        self.assertTrue(any("subcategoria" in e and "categoria" in e for e in errores_explicito))


class TestCrearVersionFijoSubcategoria(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_alta_sin_subcategoria_queda_null_como_fijo_legacy(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Servicios",
        })
        fila = db.get_gastos_fijos(self.conn)[0]
        self.assertEqual(fila["id"], primero)
        self.assertIsNone(fila["subcategoria"])

    def test_alta_con_subcategoria_la_persiste(self):
        db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        fila = db.get_gastos_fijos(self.conn)[0]
        self.assertEqual(fila["subcategoria"], "Alquiler")

    def test_version_nueva_sin_subcategoria_hereda_la_anterior(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, monto_nuevo=220000.0, vigente_desde="2026-02-01",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["subcategoria"], "Alquiler")

    def test_version_nueva_puede_asignar_subcategoria_a_un_fijo_que_ya_tenia_categoria(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Servicios",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", subcategoria="Internet",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["subcategoria"], "Internet")
        self.assertEqual(fila["categoria"], "Servicios")  # heredada, no tocada en este llamado
        # La versión original, sin subcategoría, queda intacta en el historial.
        original = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == primero)
        self.assertIsNone(original["subcategoria"])

    def test_version_nueva_asignar_subcategoria_sin_categoria_previa_lanza_valueerror(self):
        """Regla cruzada (brief t_38a7253f F1b-fix2, hallazgo 2): un fijo
        legacy sin categoria no puede recibir una subcategoria sola -- hay
        que asignarle categoria en el mismo llamado (ver el test siguiente)."""
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01",
        })
        with self.assertRaises(db.FixedCategoriaError):
            db.crear_version_fijo(self.conn, primero, vigente_desde="2026-02-01", subcategoria="Internet")

    def test_version_nueva_puede_asignar_categoria_y_subcategoria_juntas(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Internet", "monto_estimado": 15000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", categoria="Servicios", subcategoria="Internet",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["categoria"], "Servicios")
        self.assertEqual(fila["subcategoria"], "Internet")

    def test_version_nueva_vaciar_categoria_vacia_tambien_la_subcategoria(self):
        """`categoria=None` explícito sin tocar `subcategoria` vacía ambas
        -- no tiene sentido conservar una subcategoría de una categoría que
        ya no existe (brief t_38a7253f F1b-fix2, hallazgo 2)."""
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", categoria=None,
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertIsNone(fila["categoria"])
        self.assertIsNone(fila["subcategoria"])
        # La versión original queda intacta en el historial.
        original = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == primero)
        self.assertEqual(original["categoria"], "Hogar")
        self.assertEqual(original["subcategoria"], "Alquiler")

    def test_version_nueva_vaciar_solo_subcategoria_conserva_la_categoria(self):
        """`subcategoria=None` explícito sin tocar `categoria` vacía solo la
        subcategoría; la categoría se hereda sin cambios."""
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", subcategoria=None,
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["categoria"], "Hogar")
        self.assertIsNone(fila["subcategoria"])

    def test_version_nueva_vaciar_categoria_pero_mandar_subcategoria_explicita_lanza_valueerror(self):
        """Conflicto explícito: vaciar `categoria` pero insistir con una
        `subcategoria` no vacía en el mismo llamado se rechaza -- no se
        auto-corrige silenciosamente."""
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        with self.assertRaises(db.FixedCategoriaError):
            db.crear_version_fijo(
                self.conn, primero, vigente_desde="2026-02-01", categoria=None, subcategoria="Expensas",
            )

    def test_version_nueva_puede_cambiar_subcategoria_existente(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", subcategoria="Expensas",
        )
        fila = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == segundo)
        self.assertEqual(fila["subcategoria"], "Expensas")

    def test_cambiar_solo_la_subcategoria_cuenta_como_cambio_real(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        segundo = db.crear_version_fijo(
            self.conn, primero, vigente_desde="2026-02-01", subcategoria="Expensas",
        )
        self.assertNotEqual(primero, segundo)
        with self.assertRaises(db.FixedNoChangeError):
            db.crear_version_fijo(self.conn, segundo, vigente_desde="2026-03-01", subcategoria="Expensas")

    def test_baja_conserva_la_subcategoria_vigente(self):
        primero = db.insert_gasto_fijo(self.conn, {
            "nombre": "Alquiler", "monto_estimado": 200000.0, "periodicidad": "mensual",
            "vigente_desde": "2026-01-01", "categoria": "Hogar", "subcategoria": "Alquiler",
        })
        baja_id = db.dar_baja_fijo(self.conn, primero, "2026-03-01", "test")
        baja = next(row for row in db.get_gastos_fijos(self.conn, solo_activos=False) if row["id"] == baja_id)
        self.assertEqual(baja["subcategoria"], "Alquiler")


if __name__ == "__main__":
    unittest.main()
