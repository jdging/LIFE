"""Tests unitarios de recetas / inventario de cocina / lista de compras (Fase 3).

Usa `sqlite3.connect(":memory:")` por test, sin depender de la base real.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402


class TestSchemaYCrudBasico(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_init_db_crea_las_tablas_nuevas(self):
        tablas = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for esperada in (
            "recetas",
            "receta_ingredientes",
            "inventario_bienes",
            "inventario_cocina",
            "lista_compras",
        ):
            self.assertIn(esperada, tablas)

    def test_insert_y_get_receta_con_ingredientes(self):
        receta_id = db.insert_receta(
            self.conn, {"nombre": "Milanesas con puré", "porciones": 4}
        )
        db.insert_receta_ingrediente(
            self.conn,
            {"receta_id": receta_id, "ingrediente_nombre": "papa", "cantidad": 1, "unidad": "kg"},
        )

        recetas = db.get_recetas(self.conn)
        self.assertEqual(len(recetas), 1)
        self.assertEqual(recetas[0]["nombre"], "Milanesas con puré")

        ingredientes = db.get_receta_ingredientes(self.conn, receta_id)
        self.assertEqual(len(ingredientes), 1)
        self.assertEqual(ingredientes[0]["ingrediente_nombre"], "papa")

    def test_get_recetas_filtra_por_activa(self):
        db.insert_receta(self.conn, {"nombre": "Activa", "activa": True})
        db.insert_receta(self.conn, {"nombre": "Inactiva", "activa": False})

        self.assertEqual(len(db.get_recetas(self.conn, activa=True)), 1)
        self.assertEqual(len(db.get_recetas(self.conn, activa=False)), 1)
        self.assertEqual(len(db.get_recetas(self.conn)), 2)

    def test_insert_y_get_inventario_bienes(self):
        db.insert_inventario_bien(
            self.conn,
            {"nombre": "Notebook", "categoria": "Electrónica", "valor_estimado": 500},
        )
        bienes = db.get_inventario_bienes(self.conn)
        self.assertEqual(len(bienes), 1)
        self.assertEqual(bienes[0]["nombre"], "Notebook")

    def test_insert_y_get_inventario_cocina_con_filtro_ubicacion(self):
        db.insert_inventario_cocina(
            self.conn,
            {"ingrediente_nombre": "Papa", "cantidad_actual": 2, "unidad": "kg", "ubicacion": "alacena"},
        )
        db.insert_inventario_cocina(
            self.conn,
            {"ingrediente_nombre": "Leche", "cantidad_actual": 1, "unidad": "L", "ubicacion": "heladera"},
        )

        self.assertEqual(len(db.get_inventario_cocina(self.conn)), 2)
        self.assertEqual(len(db.get_inventario_cocina(self.conn, ubicacion="heladera")), 1)

    def test_lista_compras_insert_get_y_marcar_comprado(self):
        item_id = db.insert_lista_compras(
            self.conn, {"item_nombre": "Pollo", "cantidad_deseada": 1, "unidad": "kg"}
        )

        pendientes = db.get_lista_compras(self.conn, comprado=False)
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["item_nombre"], "Pollo")

        db.marcar_comprado(self.conn, item_id)

        self.assertEqual(len(db.get_lista_compras(self.conn, comprado=False)), 0)
        comprados = db.get_lista_compras(self.conn, comprado=True)
        self.assertEqual(len(comprados), 1)
        self.assertIsNotNone(comprados[0]["fecha_comprado"])


def _crear_receta_con_ingredientes(conn, nombre, ingredientes):
    receta_id = db.insert_receta(conn, {"nombre": nombre, "activa": True})
    for ingrediente_nombre, cantidad, unidad in ingredientes:
        db.insert_receta_ingrediente(
            conn,
            {
                "receta_id": receta_id,
                "ingrediente_nombre": ingrediente_nombre,
                "cantidad": cantidad,
                "unidad": unidad,
            },
        )
    return receta_id


def _cargar_stock(conn, ingrediente_nombre, cantidad_actual, unidad="u"):
    return db.insert_inventario_cocina(
        conn,
        {
            "ingrediente_nombre": ingrediente_nombre,
            "cantidad_actual": cantidad_actual,
            "unidad": unidad,
        },
    )


class TestSugerirRecetaCocinable(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_receta_cocinable_cuando_hay_todo_el_stock(self):
        _crear_receta_con_ingredientes(
            self.conn,
            "Tallarines con salsa",
            [("tallarines", 500, "g"), ("tomate", 800, "g")],
        )
        _cargar_stock(self.conn, "tallarines", 500, "g")
        _cargar_stock(self.conn, "tomate", 800, "g")

        resultado = db.sugerir_receta_cocinable(self.conn)

        self.assertEqual(len(resultado["cocinables"]), 1)
        self.assertEqual(resultado["cocinables"][0]["nombre"], "Tallarines con salsa")
        self.assertEqual(resultado["casi_cocinables"], [])

    def test_receta_casi_cocinable_cuando_falta_un_ingrediente(self):
        _crear_receta_con_ingredientes(
            self.conn,
            "Guiso de lentejas",
            [("lentejas", 400, "g"), ("panceta", 150, "g")],
        )
        _cargar_stock(self.conn, "lentejas", 400, "g")
        _cargar_stock(self.conn, "panceta", 0, "g")

        resultado = db.sugerir_receta_cocinable(self.conn)

        self.assertEqual(resultado["cocinables"], [])
        self.assertEqual(len(resultado["casi_cocinables"]), 1)
        self.assertEqual(resultado["casi_cocinables"][0]["nombre"], "Guiso de lentejas")
        self.assertEqual(resultado["casi_cocinables"][0]["falta"], "panceta")

    def test_receta_no_cocinable_cuando_faltan_dos_o_mas_ingredientes(self):
        _crear_receta_con_ingredientes(
            self.conn,
            "Milanesas con puré",
            [("carne para milanesa", 4, "unidad"), ("papa", 1, "kg"), ("huevo", 2, "unidad")],
        )
        _cargar_stock(self.conn, "carne para milanesa", 0, "unidad")
        _cargar_stock(self.conn, "papa", 0, "kg")
        _cargar_stock(self.conn, "huevo", 2, "unidad")

        resultado = db.sugerir_receta_cocinable(self.conn)

        nombres_cocinables = [r["nombre"] for r in resultado["cocinables"]]
        nombres_casi = [r["nombre"] for r in resultado["casi_cocinables"]]
        self.assertNotIn("Milanesas con puré", nombres_cocinables)
        self.assertNotIn("Milanesas con puré", nombres_casi)

    def test_comparacion_de_ingrediente_es_case_insensitive(self):
        _crear_receta_con_ingredientes(
            self.conn, "Ensalada de arroz", [("Arroz", 300, "g")]
        )
        _cargar_stock(self.conn, "ARROZ", 300, "g")

        resultado = db.sugerir_receta_cocinable(self.conn)

        self.assertEqual(len(resultado["cocinables"]), 1)

    def test_casi_cocinables_no_se_devuelve_si_hay_recetas_cocinables(self):
        _crear_receta_con_ingredientes(
            self.conn, "Tallarines con salsa", [("tallarines", 500, "g")]
        )
        _cargar_stock(self.conn, "tallarines", 500, "g")

        _crear_receta_con_ingredientes(
            self.conn, "Guiso de lentejas", [("lentejas", 400, "g"), ("panceta", 150, "g")]
        )
        _cargar_stock(self.conn, "lentejas", 400, "g")
        _cargar_stock(self.conn, "panceta", 0, "g")

        resultado = db.sugerir_receta_cocinable(self.conn)

        self.assertEqual(len(resultado["cocinables"]), 1)
        self.assertEqual(resultado["casi_cocinables"], [])


class TestDescontarStockPorReceta(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _stock_de(self, ingrediente_nombre):
        fila = self.conn.execute(
            "SELECT cantidad_actual FROM inventario_cocina WHERE ingrediente_nombre = ?",
            (ingrediente_nombre,),
        ).fetchone()
        return fila["cantidad_actual"]

    def test_descuenta_cantidad_usada_de_cada_ingrediente(self):
        receta_id = _crear_receta_con_ingredientes(
            self.conn,
            "Tallarines con salsa",
            [("tallarines", 500, "g"), ("tomate", 800, "g")],
        )
        _cargar_stock(self.conn, "tallarines", 500, "g")
        _cargar_stock(self.conn, "tomate", 1000, "g")

        db.descontar_stock_por_receta(self.conn, receta_id)

        self.assertEqual(self._stock_de("tallarines"), 0)
        self.assertEqual(self._stock_de("tomate"), 200)

    def test_clampea_a_cero_si_el_stock_es_insuficiente(self):
        receta_id = _crear_receta_con_ingredientes(
            self.conn, "Ensalada de arroz", [("arroz", 300, "g")]
        )
        _cargar_stock(self.conn, "arroz", 100, "g")

        db.descontar_stock_por_receta(self.conn, receta_id)

        self.assertEqual(self._stock_de("arroz"), 0)

    def test_actualiza_ultima_actualizacion(self):
        receta_id = _crear_receta_con_ingredientes(
            self.conn, "Ensalada de arroz", [("arroz", 300, "g")]
        )
        _cargar_stock(self.conn, "arroz", 300, "g")

        db.descontar_stock_por_receta(self.conn, receta_id)

        fila = self.conn.execute(
            "SELECT ultima_actualizacion FROM inventario_cocina WHERE ingrediente_nombre = 'arroz'"
        ).fetchone()
        self.assertIsNotNone(fila["ultima_actualizacion"])


if __name__ == "__main__":
    unittest.main()
