"""Genera dos PDF de DEMO SINTÉTICA. No usa DB ni servicio."""
from datetime import datetime, timezone
from pathlib import Path
from supermercado_pdf import build_pdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencia"


def item(name, category, missing, unit):
    return {"producto": name, "categoria": category, "a_comprar": missing, "unidad": unit}


def main():
    OUT.mkdir(exist_ok=True)
    when = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    short = [item("Arroz sintético", "Almacén", 1.5, "kg"),
             item("Leche sintética", "Lácteos", 2, "L"),
             item("Pilas sintéticas", None, 4, "u")]
    long = [item(f"Producto sintético {i:03d} " + "nombre muy largo " * 5,
                 "Categoría sintética de prueba " + "larga " * 8, 0.125, "kg") for i in range(180)]
    (OUT / "f4-lista-demo-sintetica.pdf").write_bytes(build_pdf(short, when))
    (OUT / "f4-lista-larga-demo-sintetica.pdf").write_bytes(build_pdf(long, when))


if __name__ == "__main__":
    main()
