"""Lista A4 generada desde las filas canónicas del servidor."""
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


def _pdf_text(value):
    return str(value).encode("cp1252", errors="replace").decode("cp1252")


def _wrap(value, width, font="Helvetica", size=10):
    text = _pdf_text(value)
    lines, line = [], ""
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


def build_pdf(rows, generated_at=None):
    missing = [row for row in rows if row["a_comprar"] > 0]
    if not missing:
        raise ValueError("No falta nada")
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    margin = 42
    y = 0
    page = 0

    def new_page():
        nonlocal y, page
        if page:
            pdf.showPage()
        page += 1
        y = height - margin
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(margin, y, "LISTA DEL SUPERMERCADO")
        y -= 23
        pdf.setFont("Helvetica", 9)
        when = generated_at or datetime.now(timezone.utc)
        pdf.drawString(margin, y, f"{when.strftime('%d/%m/%Y %H:%M')} UTC  |  {len(missing)} productos  |  Página {page}")
        y -= 24

    def category_heading(title):
        nonlocal y
        lines = _wrap(title.upper(), width - 2 * margin, "Helvetica-Bold", 11)
        if y - 20 - len(lines) * 14 < margin:
            new_page()
        y -= 9
        pdf.setFont("Helvetica-Bold", 11)
        for line in lines:
            pdf.drawString(margin, y, line)
            y -= 14
        pdf.line(margin, y + 3, width - margin, y + 3)
        y -= 8

    new_page()
    last_category = object()
    for row in missing:
        category = row["categoria"] or "Sin categoría"
        if category != last_category:
            category_heading(category)
            last_category = category
        quantity = f'{row["a_comprar"]:.6f}'.rstrip("0").rstrip(".") + " " + row["unidad"]
        qty_lines = _wrap(quantity, 105)
        name_lines = _wrap(row["producto"], width - 2 * margin - 146)
        row_height = max(len(name_lines), len(qty_lines)) * 13 + 8
        if y - row_height < margin:
            new_page()
            category_heading(category + " (CONT.)")
        pdf.rect(margin, y - 10, 9, 9, stroke=1, fill=0)
        pdf.setFont("Helvetica", 10)
        for index, line in enumerate(name_lines):
            pdf.drawString(margin + 20, y - 8 - index * 13, line)
        for index, line in enumerate(qty_lines):
            pdf.drawRightString(width - margin, y - 8 - index * 13, line)
        y -= row_height
    pdf.save()
    return output.getvalue()
