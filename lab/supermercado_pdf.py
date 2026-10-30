"""Printable A4 shopping list from the server's canonical, ordered rows."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 30
GUTTER = 12
COLUMN_WIDTH = (PAGE_WIDTH - 2 * MARGIN - 2 * GUTTER) / 3
CONTENT_TOP = PAGE_HEIGHT - 101
CONTENT_BOTTOM = MARGIN
ITEM_TEXT_WIDTH = COLUMN_WIDTH - 14
BODY_SIZE = 9
BODY_LEADING = 11
BODY_FONT = "Courier"
DETAIL_SIZE = 8
DETAIL_LEADING = 10
DETAIL_FONT = "Courier"
HEADING_SIZE = 9
HEADING_LEADING = 11
INK = HexColor("#332d22")
INK_SOFT = HexColor("#6e6552")
GREEN = HexColor("#8fb87a")
GREEN_DEEP = HexColor("#5f7d52")


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
    return (_wrap(primary, ITEM_TEXT_WIDTH, font=BODY_FONT, size=BODY_SIZE),
            _wrap(detail, ITEM_TEXT_WIDTH, font=DETAIL_FONT, size=DETAIL_SIZE))


def _item_height(lines):
    primary, detail = lines
    return (9 + len(primary) * BODY_LEADING +
            (len(detail) - 1) * DETAIL_LEADING + 8)


def _heading_lines(category, continued=False):
    title = category.upper() + (" (CONT.)" if continued else "")
    return _wrap(title, COLUMN_WIDTH, "Helvetica-Bold", HEADING_SIZE)


def _heading_height(lines, after_item=False):
    return (7 if after_item else 0) + 9 + len(lines) * HEADING_LEADING + 3


def _column_positions(count):
    """Center the fixed-width occupied columns on the physical page."""
    if not 1 <= count <= 3:
        raise ValueError("Column count must be between one and three")
    cluster_width = count * COLUMN_WIDTH + (count - 1) * GUTTER
    start = (PAGE_WIDTH - cluster_width) / 2
    return [start + index * (COLUMN_WIDTH + GUTTER)
            for index in range(count)]


def _plan_pages(prepared):
    """Measure every heading and item before drawing, preserving input order."""
    pages = [[[]]]
    y = CONTENT_TOP
    active_category = None
    has_item = False

    for category, item_lines in prepared:
        heading = None
        if category != active_category or not has_item:
            heading = _heading_lines(
                category, continued=category == active_category and not has_item)
        heading_height = _heading_height(heading, has_item) if heading else 0
        item_height = _item_height(item_lines)

        if y - heading_height - item_height < CONTENT_BOTTOM:
            if len(pages[-1]) == 3:
                pages.append([[]])
            else:
                pages[-1].append([])
            y = CONTENT_TOP
            has_item = False
            heading = _heading_lines(category, continued=category == active_category)
            heading_height = _heading_height(heading)

        if y - heading_height - item_height < CONTENT_BOTTOM:
            raise ValueError("Shopping item is too tall for an A4 column")

        if heading:
            pages[-1][-1].append(("heading", heading, has_item))
            y -= heading_height
        pages[-1][-1].append(("item", item_lines))
        y -= item_height
        active_category = category
        has_item = True

    return pages


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
    pages = _plan_pages(prepared)

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    when = generated_at or datetime.now(timezone.utc)

    def draw_header(page_number):
        pdf.setFillColor(GREEN_DEEP)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(MARGIN, PAGE_HEIGHT - 36, "LIFE")
        pdf.setFillColor(INK)
        pdf.setFont("Times-Roman", 20)
        pdf.drawString(MARGIN, PAGE_HEIGHT - 59, "Lista del supermercado")
        pdf.setFillColor(INK_SOFT)
        pdf.setFont("Courier", 8)
        stamp = when.strftime("%d/%m/%Y %H:%M")
        pdf.drawString(MARGIN, PAGE_HEIGHT - 76,
                       f"{stamp} UTC  ·  {len(missing)} productos")
        pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 76,
                            f"Página {page_number}")
        pdf.setStrokeColor(GREEN)
        pdf.setLineWidth(1.2)
        pdf.line(MARGIN, PAGE_HEIGHT - 85, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 85)

    def draw_heading(x, y, lines, after_item):
        if after_item:
            y -= 7
        pdf.setFillColor(GREEN_DEEP)
        pdf.setFont("Helvetica-Bold", HEADING_SIZE)
        for index, line in enumerate(lines):
            pdf.drawString(x, y - 9 - index * HEADING_LEADING, line)
        rule_y = y - 9 - len(lines) * HEADING_LEADING + 3
        pdf.setStrokeColor(GREEN)
        pdf.setLineWidth(0.6)
        pdf.line(x, rule_y, x + COLUMN_WIDTH, rule_y)
        return y - 9 - len(lines) * HEADING_LEADING - 3

    def draw_item(x, y, lines):
        primary, detail = lines
        pdf.setStrokeColor(INK_SOFT)
        pdf.setLineWidth(0.8)
        pdf.rect(x, y - 10, 8, 8, stroke=1, fill=0)
        pdf.setFillColor(INK)
        pdf.setFont(BODY_FONT, BODY_SIZE)
        for index, line in enumerate(primary):
            pdf.drawString(x + 14, y - 9 - index * BODY_LEADING, line)
        pdf.setFillColor(INK_SOFT)
        pdf.setFont(DETAIL_FONT, DETAIL_SIZE)
        detail_y = y - 9 - len(primary) * BODY_LEADING
        for index, line in enumerate(detail):
            pdf.drawString(x + 14, detail_y - index * DETAIL_LEADING, line)
        return y - _item_height(lines)

    for page_number, columns in enumerate(pages, start=1):
        if page_number > 1:
            pdf.showPage()
        draw_header(page_number)
        for x, blocks in zip(_column_positions(len(columns)), columns):
            y = CONTENT_TOP
            for block in blocks:
                if block[0] == "heading":
                    y = draw_heading(x, y, block[1], block[2])
                else:
                    y = draw_item(x, y, block[1])

    pdf.save()
    return output.getvalue()
