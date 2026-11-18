"""Recipe contract against real, disposable SQLite databases."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import db
from tests.test_api import WsgiApiTestCase


class RecetasApiTest(WsgiApiTestCase):
    def payload(self, **overrides):
        return {"titulo": "Tarta de limón", "pasos": ["Mezclar", "Hornear"],
                "ingredientes": [{"nombre": "Limón", "cantidad": 1.5, "unidad": "u"},
                                 {"nombre": "Sal", "cantidad": None, "unidad": "a gusto"}],
                **overrides}

    def test_create_persists_order_and_marks_recipe_real(self):
        payload = self.payload()
        status, recipe, _ = self.request("POST", "/api/recetas", payload)
        self.assertEqual(status, 201)
        self.assertEqual(recipe, {**payload, "id": recipe["id"], "version": 1,
                                  "notas": None, "porciones": 1, "tiempo_preparacion_min": None})
        self.assertEqual(self.request("GET", f"/api/recetas/{recipe['id']}")[:2], (200, recipe))

    def test_create_rejects_invalid_sections(self):
        for invalid in ({"titulo": ""}, {"ingredientes": []}, {"pasos": []},
                        {"pasos": [" "]}, {"ingredientes": [{"nombre": " ", "cantidad": True}]},
                        {"ingredientes": [{"nombre": "Sal", "cantidad": -1}]}, {"es_real": True},
                        {"allow_duplicado": 1}, {"clave_ingesta": " "}, {"titulo": "\ud800"}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.request("POST", "/api/recetas", self.payload(**invalid))[0], 400)
        self.assertEqual(self.request("POST", "/api/recetas", {"titulo": "Sopa"})[0], 400)
        self.assertEqual(self.request("GET", "/api/recetas")[1], {"recetas": []})

    def test_duplicate_title_requires_explicit_override(self):
        self.assertEqual(self.request("POST", "/api/recetas", self.payload(titulo="Ｔarta  de limón"))[0], 201)
        payload = self.payload(titulo="  tARTA de LIMÓN ")
        status, body, _ = self.request("POST", "/api/recetas", payload)
        self.assertEqual((status, body.get("code")), (409, "receta_duplicada"))
        self.assertEqual(self.request("POST", "/api/recetas", {**payload, "allow_duplicado": True})[0], 201)
        self.assertEqual(len(self.request("GET", "/api/recetas")[1]["recetas"]), 2)

    def test_concurrent_ingest_replays_one_recipe_without_overwrite(self):
        payload = self.payload(clave_ingesta="telegram:chat:1", allow_duplicado=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.request("POST", "/api/recetas", payload), range(2)))
        self.assertEqual(sorted(status for status, _, _ in results), [200, 201])
        recipe = results[0][1]
        self.assertEqual(results[1][1], recipe)
        self.assertEqual(self.request("POST", "/api/recetas", {**payload, "titulo": "No reemplazar"})[:2], (200, recipe))
        self.assertEqual(self.request("GET", "/api/recetas")[1], {"recetas": [recipe]})

    def test_legacy_export_reader_does_not_expose_ingest_key(self):
        self.assertEqual(self.request("POST", "/api/recetas", self.payload(clave_ingesta="telegram:chat:1"))[0], 201)
        with db.get_connection(self.db_path) as conn:
            row, = db.get_recetas(conn, activa=True)
        self.assertNotIn("clave_ingesta", row)

    def test_patch_preserves_legacy_metadata_and_empty_sections(self):
        with db.get_connection(self.db_path) as conn:
            recipe_id = db.insert_receta(conn, {"nombre": "Legado", "notas": "Original", "porciones": 2,
                                                 "tiempo_preparacion_min": 15})
            db.marcar_receta_real(conn, recipe_id)
        path = f"/api/recetas/{recipe_id}"
        status, recipe, _ = self.request("PATCH", path, {"titulo": "Tradicional", "version": 1, "pasos": []})
        self.assertEqual((status, recipe), (200, {"id": recipe_id, "titulo": "Tradicional",
                         "pasos": [], "ingredientes": [], "notas": "Original", "porciones": 2,
                         "tiempo_preparacion_min": 15, "version": 2}))
        self.assertEqual(self.request("GET", path)[:2], (200, recipe))

    def test_patch_replaces_only_supplied_sections_and_rejects_stale_version(self):
        _, original, _ = self.request("POST", "/api/recetas", self.payload())
        path = f"/api/recetas/{original['id']}"
        ingredients = list(reversed(original["ingredientes"]))
        status, recipe, _ = self.request("PATCH", path, {"version": 1, "ingredientes": ingredients})
        self.assertEqual((status, recipe), (200, {**original, "ingredientes": ingredients, "version": 2}))
        status, body, _ = self.request("PATCH", path, {"version": 1, "titulo": "No sobrescribir"})
        self.assertEqual((status, body.get("code")), (409, "version_desactualizada"))
        for invalid in ({"titulo": "Sin versión"}, {"version": True, "titulo": "Inválido"},
                        {"version": 2, "ingredientes": []}, {"version": 2, "pasos": []}):
            self.assertEqual(self.request("PATCH", path, invalid)[0], 400)
        self.assertEqual(self.request("PATCH", "/api/recetas/999", {"version": 1, "titulo": "X"})[0], 404)
        self.assertEqual(self.request("GET", path)[:2], (200, recipe))

    def test_patch_rolls_back_recipe_when_ingredient_insert_fails(self):
        _, original, _ = self.request("POST", "/api/recetas", self.payload())
        path = f"/api/recetas/{original['id']}"
        with db.get_connection(self.db_path) as conn:
            conn.execute("""CREATE TRIGGER reject_ingredient BEFORE INSERT ON receta_ingredientes
                WHEN NEW.ingrediente_nombre = 'Rechazado' BEGIN SELECT RAISE(ABORT, 'test'); END""")
        status, _, _ = self.request("PATCH", path, {"version": 1, "titulo": "No guardar",
                         "ingredientes": [{"nombre": "Permitido"}, {"nombre": "Rechazado"}]})
        self.assertEqual(status, 500)
        self.assertEqual(self.request("GET", path)[:2], (200, original))

    def test_read_only_active_real_recipes(self):
        with db.get_connection(self.db_path) as conn:
            real = db.insert_receta(conn, {"nombre": "Sopa", "notas": "De la abuela", "porciones": 4})
            db.marcar_receta_real(conn, real)
            db.insert_receta_ingrediente(conn, {"receta_id": real, "ingrediente_nombre": "Sal", "unidad": "a gusto"})
            demo = db.insert_receta(conn, {"nombre": "Demo"})
            inactive = db.insert_receta(conn, {"nombre": "Archivada", "activa": False})
            db.marcar_receta_real(conn, inactive)
        recipe = {"id": real, "titulo": "Sopa", "notas": "De la abuela", "porciones": 4,
                  "tiempo_preparacion_min": None, "version": 1, "pasos": [],
                  "ingredientes": [{"nombre": "Sal", "cantidad": None, "unidad": "a gusto"}]}
        self.assertEqual(self.request("GET", "/api/recetas")[:2], (200, {"recetas": [recipe]}))
        self.assertEqual(self.request("GET", f"/api/recetas/{real}")[:2], (200, recipe))
        for hidden in (demo, inactive):
            self.assertEqual(self.request("GET", f"/api/recetas/{hidden}")[0], 404)
        self.assertEqual(self.request("GET", "/api/recetas", auth=False)[0], 401)


class RecetasMigrationTest(WsgiApiTestCase):
    def test_migration_preserves_pre_version_rows(self):
        path = self.db_path + ".legacy"
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE recetas (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
                    porciones INTEGER NOT NULL, tiempo_preparacion_min INTEGER,
                    notas TEXT, activa INTEGER NOT NULL, es_real INTEGER NOT NULL);
                INSERT INTO recetas VALUES (12, 'Tarta', 3, 25, 'Nota original', 1, 1);
            """)
        with db.get_connection(path) as conn:
            db.init_db(conn)
            db.init_db(conn)
            row = dict(conn.execute("SELECT * FROM recetas WHERE id = 12").fetchone())
        self.assertEqual(row, {"id": 12, "nombre": "Tarta", "porciones": 3,
                              "tiempo_preparacion_min": 25, "notas": "Nota original",
                              "activa": 1, "es_real": 1, "version": 1,
                              "pasos": "[]", "clave_ingesta": None})
