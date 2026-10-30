"""PDF layout checks with synthetic canonical rows; no DB or service access."""
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth

import supermercado_pdf as shopping_pdf

try:
    import fitz
except ImportError:  # Optional inspection dependency, not needed to generate PDFs.
    fitz = None


WHEN = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def row(product, category="Almacén", desired=2.5, current=0.5,
        missing=2, unit="kg"):
    return {
        "producto": product,
        "categoria": category,
        "stock_deseado": desired,
        "stock_actual": current,
        "a_comprar": missing,
        "unidad": unit,
    }


def rows_for_shape(page_count, last_columns):
    rows = []
    prepared = []
    for index in range(1000):
        entry = row(f"P{index:04d}")
        rows.append(entry)
        prepared.append((entry["categoria"], shopping_pdf._item_lines(entry)))
        pages = shopping_pdf._plan_pages(prepared)
        if len(pages) == page_count and len(pages[-1]) == last_columns:
            return rows
    raise AssertionError("Synthetic page shape could not be constructed")


class RecordingCanvas:
    instances = []

    def __init__(self, output, pagesize):
        self.output = output
        self.pagesize = pagesize
        self.page = 1
        self.font = "Helvetica"
        self.size = 9
        self.events = []
        self.instances.append(self)

    def setFont(self, font, size):
        self.font, self.size = font, size

    def setFillColor(self, color):
        self.events.append(("fill", self.page, color))

    def setStrokeColor(self, color):
        self.events.append(("stroke", self.page, color))

    def setLineWidth(self, width):
        self.events.append(("width", self.page, width))

    def drawString(self, x, y, value):
        self.events.append(("text", self.page, x, y, value, self.font, self.size))

    def drawRightString(self, x, y, value):
        self.events.append(("right", self.page, x, y, value, self.font, self.size))

    def rect(self, x, y, width, height, stroke=1, fill=0):
        self.events.append(("rect", self.page, x, y, width, height, stroke, fill))

    def line(self, x1, y1, x2, y2):
        self.events.append(("line", self.page, x1, y1, x2, y2))

    def showPage(self):
        self.page += 1

    def save(self):
        self.output.write(b"%PDF-recording")


class SupermercadoPdfTest(TestCase):
    def render_recorded(self, rows):
        RecordingCanvas.instances.clear()
        with patch.object(shopping_pdf.canvas, "Canvas", RecordingCanvas):
            result = shopping_pdf.build_pdf(rows, WHEN)
        self.assertEqual(result, b"%PDF-recording")
        return RecordingCanvas.instances[0]

    def test_empty_and_missing_stocks_are_not_synthesized(self):
        with self.assertRaisesRegex(ValueError, "No falta nada"):
            shopping_pdf.build_pdf([], WHEN)
        with self.assertRaisesRegex(ValueError, "No falta nada"):
            shopping_pdf.build_pdf([row("Suficiente", missing=0)], WHEN)
        for key in ("stock_actual", "stock_deseado"):
            invalid = row("Sin dato")
            del invalid[key]
            with self.subTest(key=key), self.assertRaises(KeyError):
                shopping_pdf.build_pdf([invalid], WHEN)

    def test_short_list_keeps_product_quantity_and_stock_together(self):
        rendered = self.render_recorded([
            row("Arroz", desired=2.5, current=0.5, missing=2),
            row("Leche", "Lácteos", desired=3, current=1, missing=2, unit="L"),
            row("Pilas", None, desired=4, current=0, missing=4, unit="u"),
            row("Completo", None, desired=1, current=1, missing=0),
        ])
        text = [event[4] for event in rendered.events if event[0] == "text"]
        self.assertIn("Arroz — Comprar 2 kg", text)
        self.assertIn("Actual 0,5 kg · Deseado 2,5 kg", text)
        self.assertIn("Leche — Comprar 2 L", text)
        self.assertIn("Actual 1 L · Deseado 3 L", text)
        self.assertIn("Pilas — Comprar 4 u", text)
        self.assertIn("Actual 0 u · Deseado 4 u", text)
        self.assertNotIn("Completo", " ".join(text))
        self.assertEqual(len([event for event in rendered.events if event[0] == "rect"]), 3)
        self.assertEqual(rendered.page, 1)
        self.assertEqual([event[4] for event in rendered.events if event[0] == "right"],
                         ["Página 1"])

    def test_decimal_precision_and_received_missing_are_preserved(self):
        rendered = self.render_recorded([
            row("Pequeño", desired=0.125001, current=0.125,
                missing=0.000001, unit="kg"),
            row("Fracción", desired=0.25, current=0.125,
                missing=0.125, unit="L"),
            row("Valor servidor", desired=3, current=1, missing=1.5, unit="u"),
        ])
        text = " ".join(event[4] for event in rendered.events if event[0] == "text")
        for fragment in ("Comprar 0,000001 kg", "Actual 0,125 kg",
                         "Deseado 0,125001 kg", "Comprar 0,125 L",
                         "Comprar 1,5 u", "Actual 1 u", "Deseado 3 u"):
            self.assertIn(fragment, text)
        self.assertNotIn("Comprar 2 u", text)

    def test_server_category_and_product_order_are_not_resorted(self):
        rendered = self.render_recorded([
            row("Zeta", "Verduras"),
            row("Alfa", "Verduras"),
            row("Beta", "Bebidas"),
            row("Último", None),
        ])
        text = [event[4] for event in rendered.events if event[0] == "text"]
        markers = ["VERDURAS", "Zeta — Comprar 2 kg", "Alfa — Comprar 2 kg",
                   "BEBIDAS", "Beta — Comprar 2 kg", "SIN CATEGORÍA",
                   "Último — Comprar 2 kg"]
        self.assertEqual([text.index(value) for value in markers],
                         sorted(text.index(value) for value in markers))

    def test_exact_center_for_one_two_three_and_partial_last_pages(self):
        for pages, columns in ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2)):
            with self.subTest(pages=pages, columns=columns):
                rendered = self.render_recorded(rows_for_shape(pages, columns))
                self.assertEqual(rendered.page, pages)
                for page in range(1, pages + 1):
                    xs = sorted({event[2] for event in rendered.events
                                 if event[0] == "rect" and event[1] == page})
                    count = 3 if page < pages else columns
                    self.assertEqual(len(xs), count)
                    for actual, expected in zip(xs, shopping_pdf._column_positions(count)):
                        self.assertAlmostEqual(actual, expected, places=5)
                    center = (xs[0] + xs[-1] + shopping_pdf.COLUMN_WIDTH) / 2
                    self.assertAlmostEqual(center, A4[0] / 2, places=5)
                    if count == 3:
                        self.assertAlmostEqual(xs[0], shopping_pdf.MARGIN, places=5)

    def test_life_header_green_accent_and_light_printable_page(self):
        rendered = self.render_recorded([row("Arroz")])
        text = [(event[4], event[5], event[6]) for event in rendered.events
                if event[0] == "text"]
        self.assertIn(("LIFE", "Helvetica-Bold", 11), text)
        self.assertIn(("Lista del supermercado", "Times-Roman", 20), text)
        self.assertTrue(any(event[0] == "stroke" and event[2] == shopping_pdf.GREEN
                            for event in rendered.events))
        self.assertTrue(any(event[0] == "fill" and event[2] == shopping_pdf.GREEN_DEEP
                            for event in rendered.events))
        self.assertFalse(any(event[0] == "rect" and event[7] for event in rendered.events))

    def test_120_character_fields_and_24_character_unit_keep_all_text(self):
        category = "Categoría " + "L" * 110
        product = "Producto " + "X" * 111
        unit = "medidasuperlarguisimaabc"
        self.assertEqual((len(category), len(product), len(unit)), (120, 120, 24))
        entry = row(product, category, desired=2.5, current=0.125,
                    missing=2.375, unit=unit)
        primary, detail = shopping_pdf._item_lines(entry)
        normalize = lambda value: "".join(value.split())
        self.assertEqual(normalize("".join(primary)),
                         normalize(f"{product} — Comprar 2,375 {unit}"))
        self.assertEqual(normalize("".join(detail)),
                         normalize(f"Actual 0,125 {unit} · Deseado 2,5 {unit}"))
        heading = shopping_pdf._heading_lines(category)
        self.assertEqual(normalize("".join(heading)), normalize(category.upper()))
        rendered = self.render_recorded([entry])
        self.assertEqual(len([event for event in rendered.events if event[0] == "rect"]), 1)

    def test_three_columns_long_text_and_no_content_outside_page(self):
        long_category = "Categoría " + "L" * 110
        long_word = "X" * 114  # Six-character ID prefix makes a 120-char name.
        long_unit = "medidasuperlarguisimaabc"  # 24 characters
        self.assertEqual((len(long_category), len(long_word) + 6, len(long_unit)),
                         (120, 120, 24))
        rows = [
            row(f"P{index:04d} {long_word}" if index % 7 == 0 else f"P{index:04d}",
                long_category if index < 75 else "Bebidas",
                desired=2.5, current=0.125, missing=2.375,
                unit=long_unit if index % 11 == 0 else "kg")
            for index in range(150)
        ]
        rendered = self.render_recorded(rows)
        boxes = [event for event in rendered.events if event[0] == "rect"]
        self.assertEqual(len(boxes), 150)
        self.assertGreater(rendered.page, 1)
        first_page_x = {round(event[2], 2) for event in boxes if event[1] == 1}
        expected_x = {round(shopping_pdf.MARGIN + i *
                            (shopping_pdf.COLUMN_WIDTH + shopping_pdf.GUTTER), 2)
                      for i in range(3)}
        self.assertEqual(first_page_x, expected_x)
        for page in range(1, rendered.page + 1):
            page_boxes = [event for event in boxes if event[1] == page]
            column_xs = sorted({event[2] for event in page_boxes})
            self.assertTrue(1 <= len(column_xs) <= 3)
            for actual, expected in zip(column_xs,
                                        shopping_pdf._column_positions(len(column_xs))):
                self.assertAlmostEqual(actual, expected, places=5)
            for column_x in column_xs:
                first_box = next(event for event in page_boxes if event[2] == column_x)
                headings = [event for event in rendered.events
                            if event[0] == "text" and event[1] == page
                            and event[2] == column_x and
                            event[5:7] == ("Helvetica-Bold", shopping_pdf.HEADING_SIZE)]
                self.assertTrue(headings)
                self.assertGreater(headings[0][3], first_box[3])
        for event in rendered.events:
            if event[0] == "rect":
                _, _, x, y, width, height, stroke, fill = event
                self.assertGreaterEqual(y, shopping_pdf.CONTENT_BOTTOM)
                self.assertLessEqual(y + height, shopping_pdf.CONTENT_TOP)
                self.assertEqual((width, height, stroke, fill), (8, 8, 1, 0))
                self.assertGreaterEqual(x, shopping_pdf.MARGIN)
                self.assertLessEqual(x + width, A4[0] - shopping_pdf.MARGIN)
            if event[0] == "text" and event[3] < shopping_pdf.CONTENT_TOP:
                _, page, x, y, value, font, size = event
                column_xs = {box[2] for box in boxes if box[1] == page}
                column_x = next((candidate for candidate in column_xs
                                 if abs(x - candidate) < 0.01
                                 or abs(x - candidate - 14) < 0.01), None)
                self.assertIsNotNone(column_x)
                self.assertGreaterEqual(y, shopping_pdf.CONTENT_BOTTOM)
                self.assertLessEqual(x + stringWidth(value, font, size),
                                     column_x + shopping_pdf.COLUMN_WIDTH + 0.01)
        labels = [event[4].split()[0] for event in rendered.events
                  if event[0] == "text" and event[4].startswith("P")]
        self.assertEqual(labels, [f"P{index:04d}" for index in range(150)])
        headings = [(position, event) for position, event in
                    enumerate(rendered.events)
                    if event[0] == "text" and event[5:7] == ("Helvetica-Bold", 9)]
        self.assertTrue(any("CONT." in event[4] for _, event in headings))
        for position, heading in headings:
            following = next(event for event in rendered.events[position + 1:]
                             if event[0] == "rect")
            self.assertEqual(heading[1], following[1])
            self.assertAlmostEqual(heading[2], following[2], places=2)
            self.assertGreater(heading[3], following[3])

    def test_1000_items_have_one_checkbox_each_without_blank_page(self):
        rows = [row(f"P{index:04d}", "Almacén") for index in range(1000)]
        with patch("tempfile.NamedTemporaryFile",
                   side_effect=AssertionError("Temporary file used")), \
             patch("tempfile.mkstemp", side_effect=AssertionError("Temporary file used")):
            rendered = self.render_recorded(rows)
        boxes = [event for event in rendered.events if event[0] == "rect"]
        self.assertEqual(len(boxes), 1000)
        self.assertGreater(rendered.page, 1)
        self.assertEqual({event[1] for event in boxes},
                         set(range(1, rendered.page + 1)))
        self.assertEqual(len([event for event in rendered.events
                              if event[0] == "right"]), rendered.page)
        labels = [event[4].split()[0] for event in rendered.events
                  if event[0] == "text" and event[4].startswith("P")]
        self.assertEqual(labels, [f"P{index:04d}" for index in range(1000)])

    def test_real_pdf_is_a4_and_contains_every_product_when_fitz_is_available(self):
        rows = [row(f"P{index:04d}", "Almacén") for index in range(130)]
        pdf = shopping_pdf.build_pdf(rows, WHEN)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        if fitz is None:
            self.skipTest("PyMuPDF is optional")
        with fitz.open(stream=pdf, filetype="pdf") as document:
            self.assertGreater(document.page_count, 1)
            for page in document:
                self.assertAlmostEqual(page.rect.width, A4[0], places=1)
                self.assertAlmostEqual(page.rect.height, A4[1], places=1)
            content = " ".join(page.get_text() for page in document)
            self.assertIn("LIFE", content)
            self.assertIn("Lista del supermercado", content)
            self.assertIn("Comprar 2 kg", content)
            self.assertIn("Actual 0,5 kg", content)
            self.assertIn("Deseado 2,5 kg", content)
            for index in range(130):
                self.assertEqual(content.count(f"P{index:04d}"), 1)
            squares = [rect for page in document for drawing in page.get_drawings()
                       for kind, rect, *_ in drawing["items"]
                       if kind == "re" and abs(rect.width - 8) < 0.1
                       and abs(rect.height - 8) < 0.1]
            self.assertEqual(len(squares), 130)
