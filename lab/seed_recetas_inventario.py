"""Carga datos de EJEMPLO para recetas, inventario de cocina y lista de compras.

IMPORTANTE: las recetas y cantidades de este script son inventadas para poder
probar `sugerir_receta_cocinable` / `descontar_stock_por_receta` con casos
reales. No es el recetario real de Juan ni un inventario real de su cocina
(ver README.md).

Uso: `python3 seed_recetas_inventario.py`
"""

from datetime import datetime, timezone
from pathlib import Path

import db

RECETAS = [
    {
        "nombre": "Milanesas con puré",
        "porciones": 4,
        "tiempo_preparacion_min": 45,
        "notas": "Ejemplo — milanesas de carne al horno o fritas + puré de papas.",
        "ingredientes": [
            ("carne para milanesa", 4, "unidad"),
            ("pan rallado", 200, "g"),
            ("huevo", 2, "unidad"),
            ("papa", 1, "kg"),
            ("leche", 200, "ml"),
            ("sal", None, None),
        ],
    },
    {
        "nombre": "Tallarines con salsa",
        "porciones": 4,
        "tiempo_preparacion_min": 30,
        "notas": "Ejemplo — salsa de tomate simple.",
        "ingredientes": [
            ("tallarines", 500, "g"),
            ("tomate", 800, "g"),
            ("cebolla", 1, "unidad"),
            ("ajo", 2, "diente"),
            ("aceite", None, None),
        ],
    },
    {
        "nombre": "Tortilla de papas",
        "porciones": 3,
        "tiempo_preparacion_min": 35,
        "notas": "Ejemplo — tortilla española simplificada.",
        "ingredientes": [
            ("papa", 0.8, "kg"),
            ("huevo", 6, "unidad"),
            ("cebolla", 1, "unidad"),
            ("aceite", None, None),
        ],
    },
    {
        "nombre": "Ensalada de arroz",
        "porciones": 4,
        "tiempo_preparacion_min": 25,
        "notas": "Ejemplo — ensalada fría con arroz, verdura y atún.",
        "ingredientes": [
            ("arroz", 300, "g"),
            ("zanahoria", 2, "unidad"),
            ("arveja", 200, "g"),
            ("atun", 2, "lata"),
            ("aceite", None, None),
        ],
    },
    {
        "nombre": "Guiso de lentejas",
        "porciones": 5,
        "tiempo_preparacion_min": 60,
        "notas": "Ejemplo — guiso casero con panceta y verdura.",
        "ingredientes": [
            ("lentejas", 400, "g"),
            ("panceta", 150, "g"),
            ("cebolla", 1, "unidad"),
            ("zanahoria", 1, "unidad"),
            ("papa", 0.3, "kg"),
            ("sal", None, None),
        ],
    },
    {
        "nombre": "Pollo al horno con verduras",
        "porciones": 4,
        "tiempo_preparacion_min": 70,
        "notas": "Ejemplo — pollo entero con papa y zanahoria al horno.",
        "ingredientes": [
            ("pollo", 1.5, "kg"),
            ("papa", 0.6, "kg"),
            ("zanahoria", 3, "unidad"),
            ("aceite", None, None),
        ],
    },
    {
        "nombre": "Tarta de jamón y queso",
        "porciones": 6,
        "tiempo_preparacion_min": 50,
        "notas": "Ejemplo — tarta con tapa comprada.",
        "ingredientes": [
            ("tapa de tarta", 2, "unidad"),
            ("jamon", 200, "g"),
            ("queso", 200, "g"),
            ("huevo", 3, "unidad"),
        ],
    },
    {
        "nombre": "Panqueques dulces",
        "porciones": 4,
        "tiempo_preparacion_min": 30,
        "notas": "Ejemplo — panqueques simples con dulce de leche.",
        "ingredientes": [
            ("harina", 250, "g"),
            ("leche", 500, "ml"),
            ("huevo", 2, "unidad"),
            ("dulce de leche", 200, "g"),
        ],
    },
]

# (ingrediente_nombre, cantidad_actual, unidad, ubicacion)
INVENTARIO_COCINA = [
    ("carne para milanesa", 4, "unidad", "freezer"),
    ("pan rallado", 150, "g", "alacena"),  # insuficiente para milanesas (requiere 200)
    ("huevo", 10, "unidad", "heladera"),
    ("papa", 2, "kg", "alacena"),
    ("leche", 1000, "ml", "heladera"),
    ("sal", 500, "g", "alacena"),
    ("tallarines", 500, "g", "alacena"),
    ("tomate", 800, "g", "heladera"),
    ("cebolla", 3, "unidad", "alacena"),
    ("ajo", 5, "diente", "alacena"),
    ("aceite", 1000, "ml", "alacena"),
    ("arroz", 300, "g", "alacena"),
    ("zanahoria", 4, "unidad", "heladera"),
    ("arveja", 100, "g", "freezer"),  # insuficiente para ensalada de arroz (requiere 200)
    ("atun", 1, "lata", "alacena"),  # insuficiente para ensalada de arroz (requiere 2)
    ("lentejas", 400, "g", "alacena"),
    ("panceta", 0, "g", "heladera"),  # falta panceta -> guiso "casi cocinable"
    ("pollo", 0, "kg", "freezer"),  # falta pollo -> no cocinable (falta 1)
    ("harina", 250, "g", "alacena"),
    ("dulce de leche", 200, "g", "alacena"),
]

LISTA_COMPRAS = [
    ("panceta", 300, "g", "media", "JD"),
    ("pollo", 1.5, "kg", "alta", "Pinki"),
    ("pan rallado", 500, "g", "baja", "bot"),
    ("tapa de tarta", 2, "unidad", "media", "Pinki"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed(conn) -> None:
    db.init_db(conn)

    for receta in RECETAS:
        receta_id = db.insert_receta(
            conn,
            {
                "nombre": receta["nombre"],
                "porciones": receta["porciones"],
                "tiempo_preparacion_min": receta["tiempo_preparacion_min"],
                "notas": receta["notas"],
                "activa": True,
            },
        )
        for nombre, cantidad, unidad in receta["ingredientes"]:
            db.insert_receta_ingrediente(
                conn,
                {
                    "receta_id": receta_id,
                    "ingrediente_nombre": nombre,
                    "cantidad": cantidad,
                    "unidad": unidad,
                },
            )

    for nombre, cantidad_actual, unidad, ubicacion in INVENTARIO_COCINA:
        db.insert_inventario_cocina(
            conn,
            {
                "ingrediente_nombre": nombre,
                "cantidad_actual": cantidad_actual,
                "unidad": unidad,
                "ubicacion": ubicacion,
                "ultima_actualizacion": _now(),
                "actualizado_por": "bot",
            },
        )

    for item_nombre, cantidad_deseada, unidad, prioridad, agregado_por in LISTA_COMPRAS:
        db.insert_lista_compras(
            conn,
            {
                "item_nombre": item_nombre,
                "cantidad_deseada": cantidad_deseada,
                "unidad": unidad,
                "prioridad": prioridad,
                "agregado_por": agregado_por,
            },
        )


def _limpiar_tablas_propias(conn) -> None:
    """Borra solo las filas de las tablas que este script siembra, para ser
    idempotente sin pisar 'gastos'/'estado_conversacional' u otras tablas
    que puedan convivir en la misma base SQLite (ver seed_and_export.py)."""
    conn.execute("DELETE FROM lista_compras")
    conn.execute("DELETE FROM receta_ingredientes")
    conn.execute("DELETE FROM recetas")
    conn.execute("DELETE FROM inventario_cocina")
    conn.commit()


def main() -> None:
    conn = db.get_connection()
    db.init_db(conn)
    _limpiar_tablas_propias(conn)
    seed(conn)

    print("=== Datos de EJEMPLO cargados (recetas, inventario, lista de compras) ===\n")

    sugerencia = db.sugerir_receta_cocinable(conn)

    print(f"Recetas 100% cocinables con el inventario actual: {len(sugerencia['cocinables'])}")
    for receta in sugerencia["cocinables"]:
        print(f"  - {receta['nombre']} ({receta['porciones']} porciones)")

    if sugerencia["casi_cocinables"]:
        print("\nNinguna receta es 100% cocinable. Casi cocinables (falta 1 ingrediente):")
        for receta in sugerencia["casi_cocinables"]:
            print(f"  - {receta['nombre']} — falta: {receta['falta']}")

    conn.close()


if __name__ == "__main__":
    main()
