"""Siembra el catálogo de categorías (hoja `Categorías` del sistema real).

Decisión de diseño: se crea como script standalone en vez de extender
`seed_and_export.py`, porque ese archivo no existe todavía en este workdir
(el brief lo menciona como "existente" pero no está presente) — crear uno
nuevo evita inventar contenido de un archivo que no se puede leer. Si más
adelante aparece `seed_and_export.py`, puede importar `CATALOGO` y
`seed_categorias` desde acá en vez de duplicar el catálogo.

Uso: `python3 seed_categorias.py` (usa la base default de `db.py`).
"""

import db

# (tipo, categoria, [subcategorias]) — subcategorias vacía = sin subcategoría
# (caso de Ingreso e Inversión en el modelo real).
CATALOGO = [
    ("Gasto", "Hogar", [
        "Alquiler", "Expensas", "Electricidad", "Gas", "Internet",
        "Ferretería", "Decoración", "Limpieza", "Mantenimiento",
    ]),
    ("Gasto", "Comida", [
        "Supermercado", "Verdulería", "Carnicería", "Delivery", "Almacén",
    ]),
    ("Gasto", "Entretenimiento", [
        "Restaurantes", "Bares", "Cine/Teatro", "Streaming", "Eventos",
    ]),
    ("Gasto", "Transporte", [
        "Nafta", "Peajes", "SUBE", "Mantenimiento vehículo",
    ]),
    ("Gasto", "Salud", [
        "Obra social", "Farmacia", "Consultas",
    ]),
    ("Gasto", "Personal", [
        "Ropa", "Cuidado personal", "Educación",
    ]),
    ("Gasto", "Mascotas", [
        "Veterinaria", "Alimento",
    ]),
    ("Inversión", "Plazo fijo", []),
    ("Inversión", "FCI", []),
    ("Inversión", "Dólar/MEP", []),
    ("Inversión", "Crypto", []),
    ("Inversión", "Otro", []),
    ("Ingreso", "Salario", []),
    ("Ingreso", "Extra", []),
    ("Ingreso", "Freelance", []),
    ("Ingreso", "Otro", []),
]


def seed_categorias(conn) -> list:
    """Crea (idempotente) todas las categorías del catálogo. Devuelve las filas."""
    creadas = []
    for tipo, categoria, subcategorias in CATALOGO:
        if subcategorias:
            for subcategoria in subcategorias:
                creadas.append(
                    db.crear_categoria_si_no_existe(
                        conn, tipo, categoria, subcategoria, creada_por="seed"
                    )
                )
        else:
            creadas.append(
                db.crear_categoria_si_no_existe(
                    conn, tipo, categoria, None, creada_por="seed"
                )
            )
    return creadas


if __name__ == "__main__":
    conn = db.get_connection()
    db.init_db(conn)
    resultado = seed_categorias(conn)
    print(f"Categorías sembradas/verificadas: {len(resultado)}")
    conn.close()
