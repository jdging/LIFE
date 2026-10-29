"""Compact A4 shopping list from the server's canonical, ordered rows."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 30
GUTTER = 12
COLUMN_WIDTH = (PAGE_WIDTH - 2 * MARGIN - 2 * GUTTER) / 3
CONTENT_TOP = PAGE_HEIGHT - 83
CONTENT_BOTTOM = MARGIN
ITEM_TEXT_WIDTH = COLUMN_WIDTH - 14
BODY_SIZE = 9
BODY_LEADING = 11
DETAIL_SIZE = 8
DETAIL_LEADING = 10
HEADING_SIZE = 9
HEADING_LEADING = 11


def _pdf_text(value):
    return str(value).encode("cp1252", errors="replace").decode("cp1252")


def _quantity(value):
    # The server supplies quantities with at most six decimal places. Decimal's
    # fixed form also handles its float serialization of 0.000001 without loss.
    number = format(Decimal(str(value)), "f")
    return (number.rstrip("0").rstrip(".") if "." in number else number).replace(".", ",")


def _wrap(value, width, font="Helvetica", size=BODY_SIZE):
    text = _pdf_text(value)
    lines = []
    line = ""
    for word in text.split():
        candidate = (line + " " + word).strip()
        if stringWidth(candidate, font, size) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ""
        for char in word:
            if line and stringWidth(line + char, font, size) > width:
                lines.append(line)
                line = ""
            line += char
    if line:
        lines.append(line)
    return lines or [""]


def _item_lines(row):
    unit = _pdf_text(row["unidad"])
    quantity = _quantity(row["a_comprar"])
    current = _quantity(row["stock_actual"])
    desired = _quantity(row["stock_deseado"])
    primary = f'{_pdf_text(row["producto"])} — Comprar {quantity} {unit}'
    detail = f"Actual {current} {unit} · Deseado {desired} {unit}"
    return (_wrap(primary, ITEM_TEXT_WIDTH, size=BODY_SIZE),
            _wrap(detail, ITEM_TEXT_WIDTH, size=DETAIL_SIZE))


def _item_height(lines):
    primary, detail = lines
    return (9 + len(primary) * BODY_LEADING +
            (len(detail) - 1) * DETAIL_LEADING + 8)


def _heading_lines(category, continued=False):
    title = category.upper() + (" (CONT.)" if continued else "")
    return _wrap(title, COLUMN_WIDTH, "Helvetica-Bold", HEADING_SIZE)


def _heading_height(lines, after_item=False):
    return (7 if after_item else 0) + 9 + len(lines) * HEADING_LEADING + 3


def build_pdf(rows, generated_at=None):
    missing = [row for row in rows if row["a_comprar"] > 0]
    if not missing:
        raise ValueError("No falta nada")

    # Validate/measure the received values before drawing any page. No stock is
    # synthesized and no missing quantity is recomputed here.
    prepared = []
    for row in missing:
        category = _pdf_text(row["categoria"] or "Sin categoría")
        prepared.append((category, _item_lines(row)))

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    when = generated_at or datetime.now(timezone.utc)
    column = 0
    page = 1
    y = CONTENT_TOP

    def column_x():
        return MARGIN + column * (COLUMN_WIDTH + GUTTER)

    def draw_header():
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(MARGIN, PAGE_HEIGHT - 42, "LISTA DEL SUPERMERCADO")
        pdf.setFont("Helvetica", 8.5)
        stamp = when.strftime("%d/%m/%Y %H:%M")
        pdf.drawString(MARGIN, PAGE_HEIGHT - 58,
                       f"{stamp} UTC  ·  {len(missing)} productos")
        pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 58,
                            f"Página {page}")
        pdf.line(MARGIN, PAGE_HEIGHT - 67, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 67)

    def next_column():
        nonlocal column, page, y
        if column == 2:
            pdf.showPage()
            page += 1
            column = 0
            draw_header()
        else:
            column += 1
        y = CONTENT_TOP

    def draw_heading(lines, after_item):
        nonlocal y
        if after_item:
            y -= 7
        x = column_x()
        pdf.setFont("Helvetica-Bold", HEADING_SIZE)
        for index, line in enumerate(lines):
            pdf.drawString(x, y - 9 - index * HEADING_LEADING, line)
        rule_y = y - 9 - len(lines) * HEADING_LEADING + 3
        pdf.line(x, rule_y, x + COLUMN_WIDTH, rule_y)
        y -= 9 + len(lines) * HEADING_LEADING + 3

    def draw_item(lines):
        nonlocal y
        x = column_x()
        primary, detail = lines
        pdf.rect(x, y - 10, 8, 8, stroke=1, fill=0)
        pdf.setFont("Helvetica", BODY_SIZE)
        for index, line in enumerate(primary):
            pdf.drawString(x + 14, y - 9 - index * BODY_LEADING, line)
        pdf.setFont("Helvetica", DETAIL_SIZE)
        detail_y = y - 9 - len(primary) * BODY_LEADING
        for index, line in enumerate(detail):
            pdf.drawString(x + 14, detail_y - index * DETAIL_LEADING, line)
        y -= _item_height(lines)

    draw_header()
    active_category = None
    has_item_in_column = False
    for category, lines in prepared:
        needs_heading = category != active_category
        heading = _heading_lines(category) if needs_heading else None
        item_height = _item_height(lines)
        heading_height = _heading_height(heading, has_item_in_column) if heading else 0
        if y - heading_height - item_height < CONTENT_BOTTOM:
            next_column()
            has_item_in_column = False
            heading = _heading_lines(category, continued=not needs_heading)
        if heading:
            draw_heading(heading, has_item_in_column)
        draw_item(lines)
        active_category = category
        has_item_in_column = True

    pdf.save()
    return output.getvalue()
