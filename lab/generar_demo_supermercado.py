"""Generate two clearly synthetic PDF demos without using a DB or service."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from supermercado_pdf import build_pdf


DEFAULT_OUT = Path(__file__).resolve().parents[1] / "evidencia"


def item(name, category, desired, current, missing, unit):
    return {
        "producto": name,
        "categoria": category,
        "stock_deseado": desired,
        "stock_actual": current,
        "a_comprar": missing,
        "unidad": unit,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="Directorio para los PDF sintéticos")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    when = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    short = [
        item("Arroz sintético", "Almacén", 2.5, 0.5, 2, "kg"),
        item("Leche sintética", "Lácteos", 3, 1, 2, "L"),
        item("Pilas sintéticas", None, 4, 0, 4, "u"),
    ]
    long = []
    categories = [
        "Verduras sintéticas",
        "Almacén sintético de prueba con categoría larga y acentos",
        "Lácteos sintéticos",
        "Limpieza sintética",
        None,
    ]
    for index in range(240):
        category = categories[min(index // 48, len(categories) - 1)]
        name = f"Producto sintético {index:03d} " + ("nombre muy largo " * 4)
        long.append(item(name, category, 2.5, 0.125, 2.375,
                         "medidasuperlarguisimaabc" if index % 17 == 0 else "kg"))
    (args.out / "f4-lista-demo-sintetica.pdf").write_bytes(build_pdf(short, when))
    (args.out / "f4-lista-larga-demo-sintetica.pdf").write_bytes(build_pdf(long, when))


if __name__ == "__main__":
    main()
