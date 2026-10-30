"""Generate reproducible synthetic PDF layout demos without a DB or service."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir

from supermercado_pdf import _item_lines, _pdf_text, _plan_pages, build_pdf


DEFAULT_OUT = Path(gettempdir()) / "f4-qa3-pdf"


def item(name, category, desired, current, missing, unit):
    return {
        "producto": name,
        "categoria": category,
        "stock_deseado": desired,
        "stock_actual": current,
        "a_comprar": missing,
        "unidad": unit,
    }


def layout_rows(page_count, last_columns):
    """Find a compact synthetic list with the requested occupied page shape."""
    rows = []
    prepared = []
    for index in range(1, 1001):
        entry = item(f"Producto sintético {index:04d}", "Almacén sintético",
                     2.5, 0.5, 2, "kg")
        rows.append(entry)
        prepared.append((_pdf_text(entry["categoria"]), _item_lines(entry)))
        pages = _plan_pages(prepared)
        if len(pages) == page_count and len(pages[-1]) == last_columns:
            return rows
    raise RuntimeError("No se encontró el escenario sintético solicitado")


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
    demos = {
        "f4-qa3-1-columna.pdf": short,
        "f4-qa3-2-columnas.pdf": layout_rows(1, 2),
        "f4-qa3-3-columnas.pdf": layout_rows(1, 3),
        "f4-qa3-ultima-1-columna.pdf": layout_rows(2, 1),
        "f4-qa3-ultima-2-columnas.pdf": layout_rows(2, 2),
    }
    for filename, rows in demos.items():
        (args.out / filename).write_bytes(build_pdf(rows, when))


if __name__ == "__main__":
    main()
