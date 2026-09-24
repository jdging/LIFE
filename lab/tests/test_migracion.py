"""Tests de la migración de datos reales de LIFE (Finanzas + Inventario).

Usa datasets chicos de ejemplo (no los 223 registros reales) para verificar
el mapeo de tipo_proporcion, la resolución de cuota_ref a ids nuevos de
SQLite, y la idempotencia de correr la migración más de una vez.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import migrar_datos_reales as migracion  # noqa: E402


class TestMapeoTipoProporcion(unittest.TestCase):
    def test_dinamica_o_vacio_da_dinamico_sin_proporciones(self):
        for raw in ("dinamica", None, ""):
            with self.subTest(raw=raw):
                tipo, jd, pinki = migracion.mapear_tipo_proporcion(raw, None)
                self.assertEqual(tipo, "dinamico")
                self.assertIsNone(jd)
                self.assertIsNone(pinki)

    def test_50_50(self):
        tipo, jd, pinki = migracion.mapear_tipo_proporcion("50/50", None)
        self.assertEqual(tipo, "custom")
        self.assertEqual(jd, 50.0)
        self.assertEqual(pinki, 50.0)

    def test_100_jd(self):
        tipo, jd, pinki = migracion.mapear_tipo_proporcion("100% JD", None)
        self.assertEqual(tipo, "custom")
        self.assertEqual(jd, 100.0)
        self.assertEqual(pinki, 0.0)

    def test_100_pinki(self):
        tipo, jd, pinki = migracion.mapear_tipo_proporcion("100% Pinki", None)
        self.assertEqual(tipo, "custom")
        self.assertEqual(jd, 0.0)
        self.assertEqual(pinki, 100.0)

    def test_custom_con_proporcion_jd_explicito(self):
        tipo, jd, pinki = migracion.mapear_tipo_proporcion("custom", 30.0)
        self.assertEqual(tipo, "custom")
        self.assertEqual(jd, 30.0)
        self.assertEqual(pinki, 70.0)

    def test_custom_sin_proporcion_jd_cae_a_dinamico(self):
        tipo, jd, pinki = migracion.mapear_tipo_proporcion("custom", None)
        self.assertEqual(tipo, "dinamico")
        self.assertIsNone(jd)
        self.assertIsNone(pinki)

    def test_valor_desconocido_lanza_error(self):
        with self.assertRaises(ValueError):
            migracion.mapear_tipo_proporcion("no existe", None)


def _finanzas_ejemplo():
    """Dataset chico: 1 tarjeta, 1 categoría, 1 gasto fijo, un gasto en 3
    cuotas (autorreferenciado como en el Excel real) y un ingreso.
    """
    return {
        "Tarjetas": [
            {
                "id": "TC1", "nombre": "Visa Crédito", "tipo": "Crédito",
                "banco": "BNA", "titular": "JD", "dia_cierre": 19.0,
                "dia_vencimiento": 1.0, "label": "BNA – Visa Crédito – JD",
            },
        ],
        "Categorías": [
            {"tipo": "Gasto", "categoria": "Hogar", "subcategoria": "Electrodomesticos"},
            {"tipo": "Ingreso", "categoria": "Ingreso", "subcategoria": "Salario"},
        ],
        "GastosFijos": [
            {
                "id": "GF-001", "categoria": "Hogar", "subcategoria": "Alquiler",
                "descripcion": "Alquiler", "monto": 100000.0, "responsable": "Común",
                "medio_pago": "Transferencia", "tarjeta": None, "es_bimestral": False,
                "vigente_desde": "2026-02-01", "activo": True,
                "tipo_proporcion": "dinamica", "proporcion_jd": None,
            },
        ],
        "Log": [
            {
                "id": "LOG-00001", "fecha": "2026-02-02", "tipo": "Ingreso",
                "categoria": "Ingreso", "subcategoria": "Salario", "descripcion": "Sueldo",
                "monto_total": 500000.0, "cuotas_total": 1.0, "cuota_nro": 1.0,
                "cuota_ref": None, "medio_pago": "Transferencia", "tarjeta": None,
                "pago": "JD", "es_fijo": False, "notas": None, "borrado": False,
                "tipo_proporcion": None, "proporcion_jd": None, "corresponde_a": None,
                "saldado": False,
            },
            {
                "id": "LOG-00011", "fecha": "2026-04-04", "tipo": "Gasto",
                "categoria": "Hogar", "subcategoria": "Electrodomesticos",
                "descripcion": "Lavarropa", "monto_total": 36555.56, "cuotas_total": 3.0,
                "cuota_nro": 1.0, "cuota_ref": "LOG-00011", "medio_pago": "Crédito",
                "tarjeta": "TC1", "pago": "Común", "es_fijo": False, "notas": None,
                "borrado": False, "tipo_proporcion": "50/50", "proporcion_jd": None,
                "corresponde_a": None, "saldado": None,
            },
            {
                "id": "LOG-00012", "fecha": "2026-05-04", "tipo": "Gasto",
                "categoria": "Hogar", "subcategoria": "Electrodomesticos",
                "descripcion": "Lavarropa", "monto_total": 36555.56, "cuotas_total": 3.0,
                "cuota_nro": 2.0, "cuota_ref": "LOG-00011", "medio_pago": "Crédito",
                "tarjeta": "TC1", "pago": "Común", "es_fijo": False, "notas": None,
                "borrado": False, "tipo_proporcion": "50/50", "proporcion_jd": None,
                "corresponde_a": None, "saldado": None,
            },
            {
                "id": "LOG-00013", "fecha": "2026-06-04", "tipo": "Gasto",
                "categoria": "Hogar", "subcategoria": "Electrodomesticos",
                "descripcion": "Lavarropa", "monto_total": 36555.56, "cuotas_total": 3.0,
                "cuota_nro": 3.0, "cuota_ref": "LOG-00011", "medio_pago": "Crédito",
                "tarjeta": "TC1", "pago": "Común", "es_fijo": False, "notas": None,
                "borrado": False, "tipo_proporcion": "50/50", "proporcion_jd": None,
                "corresponde_a": None, "saldado": None,
            },
            {
                "id": "LOG-00014", "fecha": "2026-06-05", "tipo": "Gasto",
                "categoria": "Comida", "subcategoria": "Verdulería",
                "descripcion": "Verdura borrada", "monto_total": 5000.0,
                "cuotas_total": 1.0, "cuota_nro": 1.0, "cuota_ref": None,
                "medio_pago": "Efectivo", "tarjeta": None, "pago": "Común",
                "es_fijo": False, "notas": None, "borrado": True,
                "tipo_proporcion": "dinamica", "proporcion_jd": None,
                "corresponde_a": None, "saldado": None,
            },
        ],
    }


def _inventario_ejemplo():
    return {
        "Inventario": [
            {
                "id": "INV-00001", "descripcion": "Purificador de agua",
                "categoria": "Electrodomesticos", "fecha_compra": "2026-03-03",
                "precio_ars": 138000.0, "cotizacion_usd_compra": 1465.0,
                "precio_usd_compra": 94.19795222, "proporcion_jd": 50.0,
                "precio_venta_estimado_usd": None, "estado": None, "notas": None,
                "borrado": None,
            },
        ],
    }


class TestMigracionCuotas(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_cuota_ref_resuelve_a_id_sqlite_no_al_string_de_sheets(self):
        migracion.migrar_todo(self.conn, _finanzas_ejemplo(), _inventario_ejemplo())

        gastos = db.get_gastos(self.conn)
        lavarropa = [g for g in gastos if g["descripcion_original"] == "Lavarropa"]
        self.assertEqual(len(lavarropa), 3)

        primera_cuota = next(g for g in lavarropa if g["cuota_nro"] == 1)
        segunda_cuota = next(g for g in lavarropa if g["cuota_nro"] == 2)
        tercera_cuota = next(g for g in lavarropa if g["cuota_nro"] == 3)

        # La primera cuota se autorreferencia en el Excel (cuota_ref ==
        # LOG-00011, su propio id); acá debe apuntar a su propio id de SQLite.
        self.assertEqual(primera_cuota["cuota_ref"], primera_cuota["id"])
        self.assertIsInstance(primera_cuota["cuota_ref"], int)

        # Las cuotas siguientes deben apuntar al mismo id nuevo de SQLite,
        # nunca al string "LOG-00011" del Excel.
        self.assertEqual(segunda_cuota["cuota_ref"], primera_cuota["id"])
        self.assertEqual(tercera_cuota["cuota_ref"], primera_cuota["id"])
        for cuota in lavarropa:
            self.assertNotEqual(cuota["cuota_ref"], "LOG-00011")

    def test_fila_borrado_no_se_migra(self):
        migracion.migrar_todo(self.conn, _finanzas_ejemplo(), _inventario_ejemplo())
        gastos = db.get_gastos(self.conn)
        descripciones = [g["descripcion_original"] for g in gastos]
        self.assertNotIn("Verdura borrada", descripciones)

    def test_ingreso_usa_subcategoria_como_categoria(self):
        migracion.migrar_todo(self.conn, _finanzas_ejemplo(), _inventario_ejemplo())
        ingresos = db.get_ingresos(self.conn)
        self.assertEqual(len(ingresos), 1)
        self.assertEqual(ingresos[0]["categoria"], "Salario")
        self.assertEqual(ingresos[0]["persona"], "JD")
        self.assertEqual(ingresos[0]["origen"], "migracion")


class TestMigracionIdempotente(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_correr_migracion_dos_veces_no_duplica(self):
        finanzas = _finanzas_ejemplo()
        inventario = _inventario_ejemplo()

        migracion.migrar_todo(self.conn, finanzas, inventario)
        primera = {
            "gastos": len(db.get_gastos(self.conn)),
            "ingresos": len(db.get_ingresos(self.conn)),
            "gastos_fijos": len(db.get_gastos_fijos(self.conn, solo_activos=False)),
            "tarjetas": len(db.get_tarjetas(self.conn)),
            "inventario": len(db.get_inventario_bienes(self.conn)),
            "categorias": len(db.get_categorias(self.conn)),
        }

        migracion.migrar_todo(self.conn, finanzas, inventario)
        segunda = {
            "gastos": len(db.get_gastos(self.conn)),
            "ingresos": len(db.get_ingresos(self.conn)),
            "gastos_fijos": len(db.get_gastos_fijos(self.conn, solo_activos=False)),
            "tarjetas": len(db.get_tarjetas(self.conn)),
            "inventario": len(db.get_inventario_bienes(self.conn)),
            "categorias": len(db.get_categorias(self.conn)),
        }

        self.assertEqual(primera, segunda)

    def test_no_toca_gastos_de_otro_origen(self):
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-01", "monto": 17000.0, "categoria": "Entretenimiento",
                "descripcion_original": "cine con pinki", "origen": "texto",
                "confirmado": True,
            },
        )
        migracion.migrar_todo(self.conn, _finanzas_ejemplo(), _inventario_ejemplo())
        migracion.migrar_todo(self.conn, _finanzas_ejemplo(), _inventario_ejemplo())

        gastos_texto = [g for g in db.get_gastos(self.conn) if g["origen"] == "texto"]
        self.assertEqual(len(gastos_texto), 1)
        self.assertEqual(gastos_texto[0]["descripcion_original"], "cine con pinki")


if __name__ == "__main__":
    unittest.main()
