"""Script de datos de prueba: inicializa la SQLite local, inserta gastos de
ejemplo y exporta la tabla `gastos` a data/gastos.json para el dashboard estático.

Uso: python3 seed_and_export.py

Estos datos son 100% ficticios (ver README.md), pensados solo para validar
el dashboard antes de que exista integración real con el bot conversacional.
"""

import json
from pathlib import Path

import db

BASE_DIR = Path(__file__).parent
OUTPUT_PATH = BASE_DIR.parent / "src" / "lab-dashboard" / "data" / "gastos.json"

# Gastos de ejemplo: categorías, medios de pago y pagado_por variados,
# distribuidos en los últimos ~2 meses (referencia: hoy = 2026-09-24).
GASTOS_EJEMPLO = [
    {"fecha": "2026-07-28", "monto": 45000, "categoria": "Comida", "subcategoria": "Supermercado", "medio_pago": "Débito", "pagado_por": "Común", "descripcion_original": "Super de la semana"},
    {"fecha": "2026-07-30", "monto": 8500, "categoria": "Transporte", "subcategoria": "Nafta", "medio_pago": "Crédito", "pagado_por": "JD", "descripcion_original": "Carga de nafta"},
    {"fecha": "2026-08-02", "monto": 120000, "categoria": "Hogar", "subcategoria": "Alquiler", "medio_pago": "Transferencia", "pagado_por": "Común", "descripcion_original": "Alquiler agosto"},
    {"fecha": "2026-08-04", "monto": 6200, "categoria": "Salud", "subcategoria": "Farmacia", "medio_pago": "Débito", "pagado_por": "Pinki", "descripcion_original": "Farmacia"},
    {"fecha": "2026-08-06", "monto": 15400, "categoria": "Entretenimiento", "subcategoria": "Restaurantes", "medio_pago": "Crédito", "pagado_por": "Común", "descripcion_original": "Cena afuera"},
    {"fecha": "2026-08-09", "monto": 32000, "categoria": "Comida", "subcategoria": "Verdulería", "medio_pago": "Efectivo", "pagado_por": "Pinki", "descripcion_original": "Verdulería"},
    {"fecha": "2026-08-11", "monto": 9800, "categoria": "Transporte", "subcategoria": "SUBE", "medio_pago": "Débito", "pagado_por": "JD", "descripcion_original": "Carga SUBE"},
    {"fecha": "2026-08-13", "monto": 18000, "categoria": "Hogar", "subcategoria": "Electricidad", "medio_pago": "Transferencia", "pagado_por": "Común", "descripcion_original": "Factura de luz"},
    {"fecha": "2026-08-16", "monto": 22500, "categoria": "Salud", "subcategoria": "Consultas", "medio_pago": "Crédito", "pagado_por": "JD", "descripcion_original": "Consulta médica"},
    {"fecha": "2026-08-19", "monto": 11900, "categoria": "Entretenimiento", "subcategoria": "Streaming", "medio_pago": "Crédito", "pagado_por": "Común", "descripcion_original": "Suscripciones streaming"},
    {"fecha": "2026-08-21", "monto": 41000, "categoria": "Comida", "subcategoria": "Supermercado", "medio_pago": "Débito", "pagado_por": "Pinki", "descripcion_original": "Super de la semana"},
    {"fecha": "2026-08-24", "monto": 7300, "categoria": "Transporte", "subcategoria": "Peajes", "medio_pago": "Efectivo", "pagado_por": "JD", "descripcion_original": "Peajes viaje"},
    {"fecha": "2026-08-27", "monto": 9600, "categoria": "Hogar", "subcategoria": "Limpieza", "medio_pago": "Débito", "pagado_por": "Común", "descripcion_original": "Artículos de limpieza"},
    {"fecha": "2026-08-30", "monto": 13200, "categoria": "Salud", "subcategoria": "Farmacia", "medio_pago": "Efectivo", "pagado_por": "Pinki", "descripcion_original": "Farmacia"},
    {"fecha": "2026-09-02", "monto": 120000, "categoria": "Hogar", "subcategoria": "Alquiler", "medio_pago": "Transferencia", "pagado_por": "Común", "descripcion_original": "Alquiler septiembre"},
    {"fecha": "2026-09-05", "monto": 26800, "categoria": "Entretenimiento", "subcategoria": "Cine/Teatro", "medio_pago": "Crédito", "pagado_por": "Común", "descripcion_original": "Cine"},
    {"fecha": "2026-09-08", "monto": 38500, "categoria": "Comida", "subcategoria": "Delivery", "medio_pago": "Crédito", "pagado_por": "JD", "descripcion_original": "Delivery viernes"},
    {"fecha": "2026-09-11", "monto": 10200, "categoria": "Transporte", "subcategoria": "Nafta", "medio_pago": "Débito", "pagado_por": "Pinki", "descripcion_original": "Carga de nafta"},
    {"fecha": "2026-09-15", "monto": 17500, "categoria": "Salud", "subcategoria": "Obra social", "medio_pago": "Transferencia", "pagado_por": "Común", "descripcion_original": "Cuota obra social"},
    {"fecha": "2026-09-20", "monto": 29900, "categoria": "Comida", "subcategoria": "Supermercado", "medio_pago": "Débito", "pagado_por": "Común", "descripcion_original": "Super de la semana"},
]


def seed(conn) -> None:
    for gasto in GASTOS_EJEMPLO:
        db.insert_gasto(conn, {**gasto, "moneda": "ARS", "origen": "texto", "confirmado": True})


def export(conn) -> None:
    rows = db.get_gastos(conn)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Exportados {len(rows)} gastos a {OUTPUT_PATH}")


def main() -> None:
    conn = db.get_connection()
    db.init_db(conn)
    seed(conn)
    export(conn)
    conn.close()


if __name__ == "__main__":
    main()
