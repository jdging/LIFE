"""Tests del módulo Finanzas completo: categorías, gastos fijos, ingresos,
inversiones, cuotas, proporción dinámica y deudas.
"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import seed_categorias  # noqa: E402


class TestCategorias(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_crear_categoria_nueva(self):
        cat = db.crear_categoria_si_no_existe(
            self.conn, "Gasto", "Hogar", "Alquiler", creada_por="seed"
        )
        self.assertEqual(cat["tipo"], "Gasto")
        self.assertEqual(cat["categoria"], "Hogar")
        self.assertEqual(cat["subcategoria"], "Alquiler")
        self.assertEqual(cat["creada_por"], "seed")

        categorias = db.get_categorias(self.conn)
        self.assertEqual(len(categorias), 1)

    def test_crear_categoria_sin_subcategoria(self):
        cat = db.crear_categoria_si_no_existe(
            self.conn, "Ingreso", "Salario", None, creada_por="seed"
        )
        self.assertIsNone(cat["subcategoria"])

    def test_crear_categoria_es_idempotente(self):
        primera = db.crear_categoria_si_no_existe(
            self.conn, "Gasto", "Comida", "Supermercado", creada_por="seed"
        )
        segunda = db.crear_categoria_si_no_existe(
            self.conn, "Gasto", "Comida", "Supermercado", creada_por="bot"
        )
        self.assertEqual(primera["id"], segunda["id"])
        self.assertEqual(len(db.get_categorias(self.conn)), 1)
        # No pisa creada_por de la fila existente.
        self.assertEqual(segunda["creada_por"], "seed")

    def test_crear_categoria_idempotente_sin_subcategoria(self):
        primera = db.crear_categoria_si_no_existe(
            self.conn, "Ingreso", "Extra", None, creada_por="bot"
        )
        segunda = db.crear_categoria_si_no_existe(
            self.conn, "Ingreso", "Extra", None, creada_por="bot"
        )
        self.assertEqual(primera["id"], segunda["id"])
        self.assertEqual(len(db.get_categorias(self.conn, tipo="Ingreso")), 1)

    def test_get_categorias_filtra_por_tipo(self):
        db.crear_categoria_si_no_existe(self.conn, "Gasto", "Hogar", "Alquiler")
        db.crear_categoria_si_no_existe(self.conn, "Ingreso", "Salario", None)

        self.assertEqual(len(db.get_categorias(self.conn, tipo="Gasto")), 1)
        self.assertEqual(len(db.get_categorias(self.conn, tipo="Ingreso")), 1)
        self.assertEqual(len(db.get_categorias(self.conn)), 2)

    def test_seed_categorias_siembra_catalogo_completo_e_idempotente(self):
        primera = seed_categorias.seed_categorias(self.conn)
        segunda = seed_categorias.seed_categorias(self.conn)
        self.assertEqual(len(primera), len(segunda))
        self.assertEqual(len(db.get_categorias(self.conn)), len(primera))
        self.assertTrue(
            any(c["categoria"] == "Salario" for c in db.get_categorias(self.conn, "Ingreso"))
        )


class TestGastosFijos(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_y_get_gastos_fijos(self):
        gasto_fijo_id = db.insert_gasto_fijo(
            self.conn,
            {
                "nombre": "Alquiler",
                "monto_estimado": 150000.0,
                "periodicidad": "mensual",
                "dia_vencimiento": 10,
                "categoria": "Hogar",
                "subcategoria": "Alquiler",
            },
        )
        self.assertIsInstance(gasto_fijo_id, int)

        fijos = db.get_gastos_fijos(self.conn)
        self.assertEqual(len(fijos), 1)
        self.assertEqual(fijos[0]["nombre"], "Alquiler")
        self.assertEqual(fijos[0]["activo"], 1)

    def test_get_gastos_fijos_solo_activos_filtra_inactivos(self):
        db.insert_gasto_fijo(
            self.conn,
            {
                "nombre": "Streaming viejo",
                "monto_estimado": 3000.0,
                "periodicidad": "mensual",
                "activo": False,
            },
        )
        db.insert_gasto_fijo(
            self.conn,
            {
                "nombre": "Expensas",
                "monto_estimado": 50000.0,
                "periodicidad": "mensual",
            },
        )
        self.assertEqual(len(db.get_gastos_fijos(self.conn, solo_activos=True)), 1)
        self.assertEqual(len(db.get_gastos_fijos(self.conn, solo_activos=False)), 2)

    def test_actualizar_monto_fijo(self):
        gasto_fijo_id = db.insert_gasto_fijo(
            self.conn,
            {"nombre": "Internet", "monto_estimado": 8000.0, "periodicidad": "mensual"},
        )
        db.actualizar_monto_fijo(self.conn, gasto_fijo_id, 9500.0)

        # La fila original conserva su monto: el versionado no pisa el
        # histórico (bug de UPDATE in-place corregido en t_65096083).
        fila_original = self.conn.execute(
            "SELECT * FROM gastos_fijos WHERE id = ?", (gasto_fijo_id,)
        ).fetchone()
        self.assertEqual(fila_original["monto_estimado"], 8000.0)

        # La versión vigente hoy es la nueva, con el monto actualizado.
        vigentes = db.get_fijos_vigentes(self.conn)
        fijo_internet = next(f for f in vigentes if f["fijo_grupo_id"] == gasto_fijo_id)
        self.assertEqual(fijo_internet["monto_estimado"], 9500.0)

    def test_insert_gasto_fijo_con_responsable_personal_reparto_implicito(self):
        # Un fijo de responsable JD/Pinki no admite tipo_proporcion/proporcion_jd
        # explícitos (ver db.resolve_fixed_split): el reparto 100/0 es implícito
        # al responsable, pasarlo a mano es redundante y db.py lo rechaza.
        db.insert_gasto_fijo(
            self.conn,
            {
                "nombre": "Pilates",
                "monto_estimado": 56000.0,
                "periodicidad": "mensual",
                "responsable": "Pinki",
                "medio_pago": "Transferencia",
            },
        )
        fijo = db.get_gastos_fijos(self.conn)[0]
        self.assertEqual(fijo["responsable"], "Pinki")
        self.assertIsNone(fijo["tipo_proporcion"])
        self.assertEqual(fijo["proporcion_jd"], 0.0)
        self.assertEqual(fijo["medio_pago"], "Transferencia")

    def test_insert_gasto_fijo_responsable_personal_rechaza_reparto_explicito(self):
        with self.assertRaises(db.FixedSplitError):
            db.insert_gasto_fijo(
                self.conn,
                {
                    "nombre": "Pilates",
                    "monto_estimado": 56000.0,
                    "periodicidad": "mensual",
                    "responsable": "Pinki",
                    "tipo_proporcion": "custom",
                    "proporcion_jd": 0.0,
                },
            )

    def test_insert_gasto_fijo_sin_responsable_queda_null(self):
        db.insert_gasto_fijo(
            self.conn,
            {"nombre": "Internet", "monto_estimado": 8000.0, "periodicidad": "mensual"},
        )
        fijo = db.get_gastos_fijos(self.conn)[0]
        self.assertIsNone(fijo["responsable"])
        self.assertIsNone(fijo["tipo_proporcion"])
        self.assertIsNone(fijo["proporcion_jd"])
        self.assertIsNone(fijo["medio_pago"])


class TestIngresos(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_ingreso_confirmado_ok(self):
        ingreso_id = db.insert_ingreso(
            self.conn,
            {
                "fecha": "2026-01-05",
                "monto": 500000.0,
                "categoria": "Salario",
                "persona": "JD",
                "confirmado": True,
            },
        )
        self.assertIsInstance(ingreso_id, int)

        ingresos = db.get_ingresos(self.conn)
        self.assertEqual(len(ingresos), 1)
        self.assertEqual(ingresos[0]["persona"], "JD")
        self.assertEqual(ingresos[0]["moneda"], "ARS")

    def test_insert_ingreso_sin_confirmar_falla(self):
        with self.assertRaises(ValueError):
            db.insert_ingreso(
                self.conn,
                {
                    "fecha": "2026-01-05",
                    "monto": 500000.0,
                    "categoria": "Salario",
                    "persona": "JD",
                    "confirmado": False,
                },
            )
        with self.assertRaises(ValueError):
            db.insert_ingreso(
                self.conn,
                {"monto": 100.0, "categoria": "Extra", "persona": "Pinki"},
            )
        self.assertEqual(db.get_ingresos(self.conn), [])

    def test_get_ingresos_filtra_por_mes(self):
        db.insert_ingreso(
            self.conn,
            {"fecha": "2026-01-05", "monto": 100.0, "categoria": "Salario",
             "persona": "JD", "confirmado": True},
        )
        db.insert_ingreso(
            self.conn,
            {"fecha": "2026-02-05", "monto": 100.0, "categoria": "Salario",
             "persona": "JD", "confirmado": True},
        )
        self.assertEqual(len(db.get_ingresos(self.conn, mes="2026-01")), 1)
        self.assertEqual(len(db.get_ingresos(self.conn)), 2)


class TestInversiones(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_inversion_confirmado_ok(self):
        inversion_id = db.insert_inversion(
            self.conn,
            {
                "fecha": "2026-01-10",
                "monto": 200000.0,
                "categoria": "Plazo fijo",
                "confirmado": True,
            },
        )
        self.assertIsInstance(inversion_id, int)

        inversiones = db.get_inversiones(self.conn)
        self.assertEqual(len(inversiones), 1)
        self.assertIsNone(inversiones[0]["persona"])

    def test_insert_inversion_sin_confirmar_falla(self):
        with self.assertRaises(ValueError):
            db.insert_inversion(
                self.conn,
                {"monto": 100.0, "categoria": "Crypto", "confirmado": False},
            )
        self.assertEqual(db.get_inversiones(self.conn), [])


class TestCuotas(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _gasto_base(self, **overrides):
        gasto = {
            "fecha": "2026-01-15",
            "monto": 90000.0,
            "categoria": "Personal",
            "descripcion_original": "notebook nueva",
            "confirmado": True,
        }
        gasto.update(overrides)
        return gasto

    def test_una_cuota_es_comportamiento_normal(self):
        resultado = db.insert_gasto_con_cuotas(self.conn, self._gasto_base(), 1)
        self.assertIsInstance(resultado, int)

        gastos = db.get_gastos(self.conn)
        self.assertEqual(len(gastos), 1)
        self.assertEqual(gastos[0]["cuotas_total"], 1)
        self.assertEqual(gastos[0]["cuota_nro"], 1)
        self.assertIsNone(gastos[0]["cuota_ref"])
        self.assertEqual(gastos[0]["monto"], 90000.0)

    def test_tres_cuotas_genera_tres_filas_vinculadas(self):
        ids = db.insert_gasto_con_cuotas(self.conn, self._gasto_base(), 3)
        self.assertEqual(len(ids), 3)

        gastos = db.get_gastos(self.conn)
        self.assertEqual(len(gastos), 3)

        primer_id = ids[0]
        for gasto in gastos:
            self.assertEqual(gasto["cuota_ref"], primer_id)
            self.assertEqual(gasto["cuotas_total"], 3)
            self.assertAlmostEqual(gasto["monto"], 30000.0)
            self.assertEqual(gasto["categoria"], "Personal")

        cuotas_ordenadas = sorted(gastos, key=lambda g: g["cuota_nro"])
        self.assertEqual([g["cuota_nro"] for g in cuotas_ordenadas], [1, 2, 3])
        self.assertEqual(
            [g["fecha"] for g in cuotas_ordenadas],
            ["2026-01-15", "2026-02-15", "2026-03-15"],
        )

    def test_cuotas_heredan_tarjeta_y_tipo_proporcion(self):
        db.insert_tarjeta(
            self.conn,
            {"id": "TC1", "nombre": "Visa", "tipo": "Crédito", "titular": "Común"},
        )
        ids = db.insert_gasto_con_cuotas(
            self.conn,
            self._gasto_base(
                tarjeta_id="TC1", tipo_proporcion="custom",
                proporcion_jd=60, proporcion_pinki=40,
            ),
            2,
        )
        gastos = db.get_gastos(self.conn)
        self.assertEqual(len(gastos), 2)
        for gasto in gastos:
            self.assertEqual(gasto["tarjeta_id"], "TC1")
            self.assertEqual(gasto["tipo_proporcion"], "custom")
            self.assertEqual(gasto["proporcion_jd"], 60)


class TestProporcionDinamica(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _ingreso_salario(self, fecha, persona, monto):
        db.insert_ingreso(
            self.conn,
            {
                "fecha": fecha,
                "monto": monto,
                "categoria": "Salario",
                "persona": persona,
                "confirmado": True,
            },
        )

    def test_proporcion_con_salarios_del_mes(self):
        self._ingreso_salario("2026-01-05", "JD", 570000.0)
        self._ingreso_salario("2026-01-05", "Pinki", 430000.0)

        proporcion = db.calcular_proporcion_mes(self.conn, "2026-01")
        self.assertAlmostEqual(proporcion["JD"], 57.0)
        self.assertAlmostEqual(proporcion["Pinki"], 43.0)

    def test_proporcion_fallback_a_mes_anterior(self):
        self._ingreso_salario("2026-01-05", "JD", 600000.0)
        self._ingreso_salario("2026-01-05", "Pinki", 400000.0)
        # Febrero no tiene salarios cargados.

        proporcion = db.calcular_proporcion_mes(self.conn, "2026-02")
        self.assertAlmostEqual(proporcion["JD"], 60.0)
        self.assertAlmostEqual(proporcion["Pinki"], 40.0)

    def test_proporcion_default_50_50_sin_ningun_salario(self):
        proporcion = db.calcular_proporcion_mes(self.conn, "2026-03")
        self.assertEqual(proporcion, {"JD": 50.0, "Pinki": 50.0})

    def test_proporcion_usa_mes_anterior_mas_reciente_no_el_primero(self):
        self._ingreso_salario("2026-01-05", "JD", 500000.0)
        self._ingreso_salario("2026-01-05", "Pinki", 500000.0)
        self._ingreso_salario("2026-02-05", "JD", 800000.0)
        self._ingreso_salario("2026-02-05", "Pinki", 200000.0)
        # Marzo no tiene datos: debe usar febrero (el más reciente anterior).

        proporcion = db.calcular_proporcion_mes(self.conn, "2026-03")
        self.assertAlmostEqual(proporcion["JD"], 80.0)
        self.assertAlmostEqual(proporcion["Pinki"], 20.0)


class TestCalcularDeudasMes(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_jd_paga_gasto_comun_pinki_le_debe_su_proporcion(self):
        db.insert_ingreso(
            self.conn,
            {"fecha": "2026-01-05", "monto": 570000.0, "categoria": "Salario",
             "persona": "JD", "confirmado": True},
        )
        db.insert_ingreso(
            self.conn,
            {"fecha": "2026-01-05", "monto": 430000.0, "categoria": "Salario",
             "persona": "Pinki", "confirmado": True},
        )
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-10",
                "monto": 100000.0,
                "categoria": "Hogar",
                "pagado_por": "JD",
                "confirmado": True,
            },
        )

        deuda = db.calcular_deudas_mes(self.conn, "2026-01")
        self.assertEqual(deuda["deudor"], "Pinki")
        self.assertEqual(deuda["acreedor"], "JD")
        self.assertAlmostEqual(deuda["monto"], 43000.0)

    def test_pagado_por_comun_no_genera_deuda(self):
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-10",
                "monto": 50000.0,
                "categoria": "Hogar",
                "pagado_por": "Común",
                "confirmado": True,
            },
        )
        deuda = db.calcular_deudas_mes(self.conn, "2026-01")
        self.assertEqual(deuda, {"deudor": None, "acreedor": None, "monto": 0.0})

    def test_gasto_custom_usa_su_propia_proporcion_no_la_dinamica(self):
        # Proporción dinámica del mes sería 50/50 (sin salarios cargados),
        # pero este gasto es 100% de Pinki explícitamente.
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-10",
                "monto": 20000.0,
                "categoria": "Personal",
                "pagado_por": "JD",
                "tipo_proporcion": "custom",
                "proporcion_jd": 0,
                "proporcion_pinki": 100,
                "confirmado": True,
            },
        )
        deuda = db.calcular_deudas_mes(self.conn, "2026-01")
        self.assertEqual(deuda["deudor"], "Pinki")
        self.assertEqual(deuda["acreedor"], "JD")
        self.assertAlmostEqual(deuda["monto"], 20000.0)

    def test_multiples_gastos_del_mes_se_netean(self):
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-05",
                "monto": 100000.0,
                "categoria": "Hogar",
                "pagado_por": "JD",
                "tipo_proporcion": "custom",
                "proporcion_jd": 50,
                "proporcion_pinki": 50,
                "confirmado": True,
            },
        )
        db.insert_gasto(
            self.conn,
            {
                "fecha": "2026-01-20",
                "monto": 40000.0,
                "categoria": "Comida",
                "pagado_por": "Pinki",
                "tipo_proporcion": "custom",
                "proporcion_jd": 50,
                "proporcion_pinki": 50,
                "confirmado": True,
            },
        )
        # JD puso 100k (Pinki le debe 50k), Pinki puso 40k (JD le debe 20k).
        # Neto: Pinki le debe a JD 50k - 20k = 30k.
        deuda = db.calcular_deudas_mes(self.conn, "2026-01")
        self.assertEqual(deuda["deudor"], "Pinki")
        self.assertEqual(deuda["acreedor"], "JD")
        self.assertAlmostEqual(deuda["monto"], 30000.0)


class TestSaldarTodasLasDeudas(unittest.TestCase):
    """`db.saldar_todas_las_deudas` (brief t_38a7253f, punto 2)."""

    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_salda_todas_las_pendientes_de_una_vez(self):
        jd_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 100000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        pinki_id = db.insert_gasto(self.conn, {
            "fecha": "2026-02-05", "monto": 40000.0, "categoria": "Comida",
            "pagado_por": "Pinki", "confirmado": True,
        })
        comun_id = db.insert_gasto(self.conn, {
            "fecha": "2026-02-10", "monto": 50000.0, "categoria": "Hogar",
            "pagado_por": "Común", "confirmado": True,
        })

        resultado = db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual(resultado["count"], 2)
        self.assertAlmostEqual(resultado["total"], 140000.0)
        self.assertEqual({f["id"] for f in resultado["expenses"]}, {jd_id, pinki_id})
        self.assertTrue(all(f["saldado"] is not None for f in resultado["expenses"]))

        gastos = {row["id"]: row for row in db.get_gastos(self.conn)}
        self.assertIsNotNone(gastos[jd_id]["saldado"])
        self.assertIsNotNone(gastos[pinki_id]["saldado"])
        self.assertIsNone(gastos[comun_id]["saldado"], "Un gasto Común nunca genera deuda; no se salda.")

        auditoria = self.conn.execute(
            "SELECT fila_id FROM auditoria WHERE tabla = 'gastos' AND accion = 'saldar'"
        ).fetchall()
        self.assertEqual({row["fila_id"] for row in auditoria}, {jd_id, pinki_id})

    def test_sin_deudas_pendientes_levanta_value_error_sin_tocar_nada(self):
        db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "Común", "confirmado": True,
        })
        with self.assertRaises(ValueError):
            db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 0,
        )

    def test_gasto_borrado_o_ya_saldado_queda_fuera(self):
        activo_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        borrado_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-11", "monto": 2000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        db.eliminar_gasto_logico(self.conn, borrado_id, "test")
        ya_saldado_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-12", "monto": 3000.0, "categoria": "Hogar",
            "pagado_por": "Pinki", "confirmado": True,
        })
        db.saldar_gasto(self.conn, ya_saldado_id, "test")

        resultado = db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual(resultado["count"], 1)
        self.assertEqual(resultado["expenses"][0]["id"], activo_id)

    def test_gasto_100_por_ciento_propio_no_genera_deuda_y_no_se_salda(self):
        """Brief t_38a7253f fix4, hallazgo 1 del revisor: mismo universo que
        `getDebtRows()` del dashboard -- un gasto pagado 100% por quien lo
        pagó (contraparte en 0%) no genera deuda real y no debe tocarse."""
        jd_100_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "tipo_proporcion": "custom",
            "proporcion_jd": 100, "proporcion_pinki": 0, "confirmado": True,
        })
        pinki_100_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-11", "monto": 2000.0, "categoria": "Hogar",
            "pagado_por": "Pinki", "tipo_proporcion": "custom",
            "proporcion_jd": 0, "proporcion_pinki": 100, "confirmado": True,
        })
        compartido_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-12", "monto": 3000.0, "categoria": "Hogar",
            "pagado_por": "JD", "tipo_proporcion": "custom",
            "proporcion_jd": 50, "proporcion_pinki": 50, "confirmado": True,
        })
        contraparte_100_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-13", "monto": 4000.0, "categoria": "Hogar",
            "pagado_por": "JD", "tipo_proporcion": "custom",
            "proporcion_jd": 0, "proporcion_pinki": 100, "confirmado": True,
        })

        resultado = db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual({f["id"] for f in resultado["expenses"]}, {compartido_id, contraparte_100_id})
        self.assertAlmostEqual(resultado["total"], 7000.0)

        gastos = {row["id"]: row for row in db.get_gastos(self.conn)}
        self.assertIsNone(gastos[jd_100_id]["saldado"], "100% JD: Pinki no participa, no hay deuda que saldar.")
        self.assertIsNone(gastos[pinki_100_id]["saldado"], "100% Pinki: JD no participa, no hay deuda que saldar.")
        self.assertIsNotNone(gastos[compartido_id]["saldado"])
        self.assertIsNotNone(gastos[contraparte_100_id]["saldado"])

    def test_custom_contraparte_derivada_de_proporcion_jd_payer_jd(self):
        """Brief t_38a7253f fix6, hallazgo 1: para `tipo_proporcion='custom'`
        el % de la contraparte se deriva SIEMPRE de `proporcion_jd` (Pinki =
        100 - proporcion_jd), igual que `getRowPct` en app.js -- nunca se lee
        `proporcion_pinki` de la fila. `proporcion_jd=100` implica contraparte
        Pinki = 0% exacto, aunque el dato legacy en `proporcion_pinki` diga
        0.001 (ruido dentro de la tolerancia de `validar_expense`, ±0.01)."""
        jd_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "tipo_proporcion": "custom",
            "proporcion_jd": 100, "proporcion_pinki": 0.001, "confirmado": True,
        })
        comun_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-11", "monto": 500.0, "categoria": "Hogar",
            "pagado_por": "JD", "tipo_proporcion": "custom",
            "proporcion_jd": 50, "proporcion_pinki": 50, "confirmado": True,
        })

        resultado = db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual({f["id"] for f in resultado["expenses"]}, {comun_id})

        gastos = {row["id"]: row for row in db.get_gastos(self.conn)}
        self.assertIsNone(
            gastos[jd_id]["saldado"],
            "proporcion_jd=100 implica contraparte Pinki=0% exacto; "
            "el ruido en proporcion_pinki (0.001) no debe generar deuda.",
        )
        self.assertIsNotNone(gastos[comun_id]["saldado"])

    def test_custom_contraparte_derivada_de_proporcion_jd_payer_pinki(self):
        """Caso simétrico: pagado por Pinki. La contraparte es JD y su % se
        lee directo de `proporcion_jd` (no de una resta sobre
        `proporcion_pinki`). `proporcion_jd=0` implica contraparte JD = 0%
        exacto, aunque `proporcion_pinki` tenga ruido legacy (99.999 en vez
        de 100, dentro de la tolerancia de `validar_expense`)."""
        pinki_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "Pinki", "tipo_proporcion": "custom",
            "proporcion_jd": 0, "proporcion_pinki": 99.999, "confirmado": True,
        })
        comun_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-11", "monto": 500.0, "categoria": "Hogar",
            "pagado_por": "Pinki", "tipo_proporcion": "custom",
            "proporcion_jd": 50, "proporcion_pinki": 50, "confirmado": True,
        })

        resultado = db.saldar_todas_las_deudas(self.conn, "test")
        self.assertEqual({f["id"] for f in resultado["expenses"]}, {comun_id})

        gastos = {row["id"]: row for row in db.get_gastos(self.conn)}
        self.assertIsNone(
            gastos[pinki_id]["saldado"],
            "proporcion_jd=0 implica contraparte JD=0% exacto; "
            "el ruido en proporcion_pinki (99.999) no debe generar deuda.",
        )
        self.assertIsNotNone(gastos[comun_id]["saldado"])

    def test_monto_legacy_invalido_no_salda_ninguna_fila(self):
        """Brief t_38a7253f fix4, hallazgo 2 del revisor: la validación de
        montos corre ANTES del UPDATE/commit -- un monto corrupto no debe
        dejar ninguna fila saldada."""
        gasto_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        # Simula un monto legacy corrupto (más de dos decimales) que nunca
        # podría insertarse vía `insert_gasto` -- se fuerza con SQL directo.
        self.conn.execute("UPDATE gastos SET monto = 1000.001 WHERE id = ?", (gasto_id,))
        self.conn.commit()

        with self.assertRaises(ValueError):
            db.saldar_todas_las_deudas(self.conn, "test")

        fila = next(row for row in db.get_gastos(self.conn) if row["id"] == gasto_id)
        self.assertIsNone(fila["saldado"], "Un monto inválido no debe dejar ninguna fila saldada.")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 0,
        )

    def test_monto_legacy_cero_no_salda_ninguna_fila(self):
        """Brief t_38a7253f fix6, hallazgo 2: `_validar_monto_saldable` exige
        monto > 0, igual que `api._valid_money` (default `positive=True`)."""
        gasto_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        self.conn.execute("UPDATE gastos SET monto = 0 WHERE id = ?", (gasto_id,))
        self.conn.commit()

        with self.assertRaises(ValueError):
            db.saldar_todas_las_deudas(self.conn, "test")

        fila = next(row for row in db.get_gastos(self.conn) if row["id"] == gasto_id)
        self.assertIsNone(fila["saldado"], "Un monto legacy de 0 no debe dejar ninguna fila saldada.")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 0,
        )

    def test_monto_legacy_negativo_no_salda_ninguna_fila(self):
        """Mismo criterio que el test anterior, con un monto negativo."""
        gasto_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        self.conn.execute("UPDATE gastos SET monto = -500 WHERE id = ?", (gasto_id,))
        self.conn.commit()

        with self.assertRaises(ValueError):
            db.saldar_todas_las_deudas(self.conn, "test")

        fila = next(row for row in db.get_gastos(self.conn) if row["id"] == gasto_id)
        self.assertIsNone(fila["saldado"], "Un monto legacy negativo no debe dejar ninguna fila saldada.")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 0,
        )

    def test_fallo_de_auditoria_fuerza_rollback_completo(self):
        """Brief t_38a7253f fix4, hallazgo 3 del revisor: si falla el INSERT
        de auditoría (o cualquier paso posterior al UPDATE), el UPDATE
        también se revierte -- no debe quedar un saldado sin su rastro."""
        gasto_id = db.insert_gasto(self.conn, {
            "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
            "pagado_por": "JD", "confirmado": True,
        })
        self.conn.execute("DROP TABLE auditoria")

        with self.assertRaises(sqlite3.OperationalError):
            db.saldar_todas_las_deudas(self.conn, "test")

        fila = next(row for row in db.get_gastos(self.conn) if row["id"] == gasto_id)
        self.assertIsNone(fila["saldado"], "Si falla la auditoría, el UPDATE de saldado también debe revertirse.")

    def test_dos_conexiones_la_segunda_no_puede_escribir_mientras_la_primera_reserva(self):
        """Brief t_38a7253f fix4, hallazgo 3 del revisor ('si podés, test con
        dos conexiones'): `BEGIN IMMEDIATE` ANTES del SELECT (mismo patrón
        que `delete_expense` en api.py) reserva el escritor para que ninguna
        otra conexión pueda mutar las filas entre el SELECT (snapshot de
        auditoría) y el UPDATE."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "dos_conexiones.sqlite")
            conn1 = db.get_connection(db_path)
            db.init_db(conn1)
            gasto_id = db.insert_gasto(conn1, {
                "fecha": "2026-01-10", "monto": 1000.0, "categoria": "Hogar",
                "pagado_por": "JD", "confirmado": True,
            })
            conn2 = db.get_connection(db_path)
            conn2.execute("PRAGMA busy_timeout = 0")
            try:
                # Mismo primer paso que `saldar_todas_las_deudas`: reservar el
                # escritor antes de leer.
                conn1.execute("BEGIN IMMEDIATE")
                conn1.execute("SELECT * FROM gastos")
                with self.assertRaises(sqlite3.OperationalError):
                    conn2.execute(
                        "UPDATE gastos SET saldado = '2026-01-01' WHERE id = ?", (gasto_id,),
                    )
            finally:
                conn1.rollback()
                conn2.close()
                conn1.close()


if __name__ == "__main__":
    unittest.main()
