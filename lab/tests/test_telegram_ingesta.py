"""Tests del CLI determinista de ingesta por Telegram (brief S2/S3, T3).

Cubre: parseo de montos AR, normalización (categorías con/sin acento,
medio de pago sin identificación, defaults por usuario), cálculo de campos faltantes,
armado de la pregunta consolidada (snapshot de texto), bloqueo de `guardar`
sin confirmación o con campos faltantes, dedupe que bloquea un guardado
(y `--forzar-duplicado` que lo permite), armado de mensaje de aviso de
crédito, extracción de PDF (con y sin texto, con un PDF generado en el
test; se salta si falta `pymupdf`) y el cliente HTTP contra la app WSGI
real (`api.create_app`) corriendo en un thread -- nunca contra datos
reales ni contra una base persistente.
"""

import contextlib
import hashlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import unittest.mock
from datetime import date
from pathlib import Path
from wsgiref.simple_server import make_server

import pytest

import api
import db
import telegram_ingesta
import telegram_retencion


# Fixture SINTÉTICA (brief t_a3f2bbb5, parte C): mismo formato EXACTO que un
# comprobante real de transferencia de Mercado Pago, pero con nombres/CUIT/
# CVU ya reemplazados por el coordinador antes de pegarlo en el brief --
# nunca se usa ni se copia el PDF real (`fixtures-reales/` queda fuera de
# los tests y del repo).
TEXTO_COMPROBANTE_MERCADOPAGO = """\
Comprobante de transferencia
Martes, 11 de agosto de 2026 a las 10:00 hs
$ 27.000
Motivo: Varios
De
Ignacio Torres
CUIT/CUIL: 20-11111111-1
Mercado Pago
CVU: 0000000000000000000001
Para
Lucía Fernández
CUIT/CUIL: 20-22222222-2
Mercado Pago
CVU: 0000000000000000000002
Número de operación de Mercado Pago
173192245876
"""


# --- Harness común: app real + servidor HTTP real en un thread -------------


class _ApiServerTestCase(unittest.TestCase):
    """Levanta `api.create_app` sobre un archivo SQLite efímero, servido por
    un `wsgiref` real en un thread (mismo patrón que
    `tests/test_api.py::test_local_http_roundtrip`), y siembra un catálogo
    mínimo de categorías para que el CLI pueda normalizar contra
    datos reales de la API (nunca inventados del lado del cliente)."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "api.sqlite")
        self.secret = "test-secret-telegram-cli"
        self.secret_path = str(Path(self.tempdir.name) / "secret.txt")
        Path(self.secret_path).write_text(self.secret, encoding="utf-8")
        os.chmod(self.secret_path, 0o600)

        self.app = api.create_app(self.db_path, self.secret)
        self.server = make_server("127.0.0.1", 0, self.app)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        conn = db.get_connection(self.db_path)
        try:
            self._seed(conn)
        finally:
            conn.close()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.app.close()
        self.tempdir.cleanup()

    def _seed(self, conn):
        categorias_gasto = (
            ("Hogar", ["Alquiler", "Expensas"]),
            ("Comida", ["Delivery", "Supermercado", "Verdulería"]),
            ("Mascotas", ["Veterinaria"]),
        )
        for categoria, subcategorias in categorias_gasto:
            for subcategoria in subcategorias:
                db.crear_categoria_si_no_existe(conn, "Gasto", categoria, subcategoria, creada_por="test")
        for categoria in ("Salario", "Extra"):
            db.crear_categoria_si_no_existe(conn, "Ingreso", categoria, None, creada_por="test")
        db.insert_tarjeta(conn, {
            "id": "TC1", "nombre": "Visa", "tipo": "Crédito", "banco": "BNA", "titular": "JD",
        })
        db.insert_tarjeta(conn, {
            "id": "TD1", "nombre": "Mastercard Débito", "tipo": "Débito", "banco": "Galicia", "titular": "JD",
        })

    def _write_json(self, datos, nombre="datos.json"):
        ruta = Path(self.tempdir.name) / nombre
        contador = 0
        while ruta.exists():
            contador += 1
            ruta = Path(self.tempdir.name) / f"{contador}-{nombre}"
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return str(ruta)

    def run_cli(self, argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = telegram_ingesta.main([
                "--api-base", self.base_url, "--secret-file", self.secret_path, *argv,
            ])
        contenido = salida.getvalue().strip()
        return codigo, (json.loads(contenido) if contenido else None)


# --- Parseo de montos AR -----------------------------------------------------


class ParseMontoArTests(unittest.TestCase):
    def test_formatos_soportados(self):
        self.assertEqual(telegram_ingesta.parse_monto_ar("45.000"), 45000.0)
        self.assertEqual(telegram_ingesta.parse_monto_ar("45 mil"), 45000.0)
        self.assertEqual(telegram_ingesta.parse_monto_ar("$45.000,50"), 45000.50)
        self.assertEqual(telegram_ingesta.parse_monto_ar("45k"), 45000.0)

    def test_passthrough_numerico(self):
        self.assertEqual(telegram_ingesta.parse_monto_ar(1500), 1500.0)
        self.assertEqual(telegram_ingesta.parse_monto_ar(1500.5), 1500.5)

    def test_formato_invalido_levanta_value_error(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar("no es un monto")
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(True)

    def test_agrupacion_de_miles_multiple_valida(self):
        self.assertEqual(telegram_ingesta.parse_monto_ar("1.500.000"), 1500000.0)

    def test_agrupacion_de_miles_invalida(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar("1.2.3")

    def test_decimal_con_mas_de_dos_digitos_invalido(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar("1.500,123")

    def test_decimal_con_dos_digitos_valido(self):
        self.assertEqual(telegram_ingesta.parse_monto_ar("1.500,12"), 1500.12)

    def test_rechaza_cero_string_y_numerico(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar("0")
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(0)

    def test_rechaza_negativo(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(-500.0)

    def test_rechaza_nan_e_infinito(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(float("nan"))
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(float("inf"))

    def test_rechaza_mayor_al_maximo_de_la_api(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(float(telegram_ingesta.MONTO_MAXIMO) + 1)

    def test_rechaza_numerico_con_mas_de_dos_decimales(self):
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(1500.567)

    def test_entero_enorme_da_value_error_limpio_sin_overflow_error(self):
        # `float(10**400)` levanta `OverflowError` directo -- `parse_monto_ar`
        # tiene que compararlo como `Decimal` contra el máximo antes de
        # convertirlo, y seguir devolviendo `ValueError` (nunca una
        # excepción sin capturar).
        with self.assertRaises(ValueError):
            telegram_ingesta.parse_monto_ar(10**400)


class FormatearMontoArTests(unittest.TestCase):
    def test_entero_sin_decimales(self):
        self.assertEqual(telegram_ingesta.formatear_monto_ar(12350), "$12.350")
        self.assertEqual(telegram_ingesta.formatear_monto_ar(200000), "$200.000")

    def test_con_decimales(self):
        self.assertEqual(telegram_ingesta.formatear_monto_ar(212350.5), "$212.350,50")


# --- Resolución tolerante de categoría/subcategoría (unidad) ---------------


class ResolverHelpersTests(unittest.TestCase):
    def test_resolver_categoria_tolerante_sin_acento_y_mayusculas(self):
        categorias = [{"categoria": "Comida", "subcategorias": ["Delivery", "Verdulería"]}]
        resultado = telegram_ingesta._resolver_categoria(categorias, "COMIDA", "verduleria")
        self.assertEqual(resultado, {"categoria": "Comida", "subcategoria": "Verdulería"})

    def test_resolver_categoria_desconocida_devuelve_none(self):
        categorias = [{"categoria": "Comida", "subcategorias": []}]
        self.assertIsNone(telegram_ingesta._resolver_categoria(categorias, "transporte", None))



# --- campos obligatorios por tipo -------------------------------------------


class CamposFaltantesTests(unittest.TestCase):
    def test_gasto_credito_no_requiere_identificacion(self):
        borrador = {
            "monto": 100.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Crédito", "pagado_por": "JD",
        }
        self.assertEqual(telegram_ingesta.calcular_campos_faltantes("gasto", borrador), [])

    def test_gasto_sin_tarjeta_obligatoria_con_efectivo(self):
        borrador = {
            "monto": 100.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
        }
        self.assertEqual(telegram_ingesta.calcular_campos_faltantes("gasto", borrador), [])

    def test_ingreso(self):
        faltan = telegram_ingesta.calcular_campos_faltantes("ingreso", {"monto": 100.0, "fecha": "2026-04-10"})
        self.assertEqual(faltan, ["categoria", "persona"])


# --- mensaje-aviso -----------------------------------------------------------


class MensajeAvisoTests(unittest.TestCase):
    def test_un_solo_mensaje_con_el_maximo(self):
        items = [
            {"mes": "2026-10", "umbral": 100000, "total": 212350.0},
            {"mes": "2026-10", "umbral": 150000, "total": 212350.0},
            {"mes": "2026-10", "umbral": 200000, "total": 212350.0},
        ]
        self.assertEqual(
            telegram_ingesta.armar_mensaje_aviso(items),
            "🚨 Los gastos en crédito de octubre superaron $200.000 (van $212.350)",
        )

    def test_acepta_formato_de_avisos_pendientes(self):
        items = [{"mes": "2026-04", "umbral": 100000, "total_al_detectar": 150000.0, "enviado_en": None}]
        self.assertEqual(
            telegram_ingesta.armar_mensaje_aviso(items),
            "🚨 Los gastos en crédito de abril superaron $100.000 (van $150.000)",
        )

    def test_rechaza_varios_meses_a_la_vez(self):
        items = [
            {"mes": "2026-04", "umbral": 100000, "total": 1.0},
            {"mes": "2026-05", "umbral": 100000, "total": 1.0},
        ]
        with self.assertRaises(telegram_ingesta.CliError):
            telegram_ingesta.armar_mensaje_aviso(items)

    def test_rechaza_lista_vacia(self):
        with self.assertRaises(telegram_ingesta.CliError):
            telegram_ingesta.armar_mensaje_aviso([])


# --- hash --------------------------------------------------------------------


class HashCommandTests(_ApiServerTestCase):
    def test_hash_sha256(self):
        contenido = b"hola mundo, esto es un comprobante de prueba"
        ruta = Path(self.tempdir.name) / "comprobante.txt"
        ruta.write_bytes(contenido)
        codigo, salida = self.run_cli(["hash", str(ruta)])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["sha256"], hashlib.sha256(contenido).hexdigest())

    def test_hash_archivo_inexistente_falla_claro(self):
        codigo, salida = self.run_cli(["hash", str(Path(self.tempdir.name) / "no-existe.txt")])
        self.assertNotEqual(codigo, 0)
        self.assertIn("error", salida)


# --- extraer-pdf -------------------------------------------------------------


class ExtraerPdfTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = telegram_ingesta.main(argv)
        contenido = salida.getvalue().strip()
        return codigo, (json.loads(contenido) if contenido else None)

    def _managed_pdf(self, path):
        root = Path(self.tempdir.name) / f"managed-{Path(path).stem}"
        root.mkdir()
        telegram_retencion.crear_raiz(root)
        staged = root / "incoming" / Path(path).name
        staged.write_bytes(Path(path).read_bytes())
        original = telegram_retencion.registrar_original(root, staged)
        return str(original), str(root / "adjuntos")

    def test_archivo_inexistente_rechazado_antes_del_subproceso(self):
        codigo, salida = self._run(["extraer-pdf", "no-importa.pdf"])
        self.assertNotEqual(codigo, 0)
        self.assertIn("PDF", salida["error"])

    def test_con_texto_y_sin_texto_con_pdf_generado_en_el_test(self):
        pymupdf = pytest.importorskip("pymupdf")

        ruta_texto = str(Path(self.tempdir.name) / "con-texto.pdf")
        doc = pymupdf.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "Factura de prueba $1500")
        doc.save(ruta_texto)
        doc.close()

        codigo, salida = self._run(["extraer-pdf", ruta_texto])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["fuente"], "pdf_texto")
        self.assertEqual(salida["paginas"], 1)
        self.assertIn("Factura", salida["texto"])
        self.assertEqual(salida["imagenes"], [])

        ruta_sin_texto = str(Path(self.tempdir.name) / "sin-texto.pdf")
        doc2 = pymupdf.open()
        doc2.new_page()
        doc2.new_page()
        doc2.save(ruta_sin_texto)
        doc2.close()

        managed_pdf, out_dir = self._managed_pdf(ruta_sin_texto)
        codigo, salida = self._run(["extraer-pdf", managed_pdf, "--out-dir", out_dir])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["fuente"], "sin_texto")
        self.assertEqual(salida["paginas"], 2)
        self.assertEqual(len(salida["imagenes"]), 2)
        for ruta_imagen in salida["imagenes"]:
            self.assertTrue(Path(ruta_imagen).is_file())

        codigo, salida = self._run(["extraer-pdf", ruta_sin_texto])
        self.assertNotEqual(codigo, 0)
        self.assertIn("out-dir", salida["error"])

    def test_out_dir_inexistente_da_error_sin_crearlo(self):
        pytest.importorskip("pymupdf")
        import pymupdf

        ruta_sin_texto = str(Path(self.tempdir.name) / "sin-texto-2.pdf")
        doc = pymupdf.open()
        doc.new_page()
        doc.save(ruta_sin_texto)
        doc.close()

        out_dir = str(Path(self.tempdir.name) / "no-existe")
        codigo, salida = self._run(["extraer-pdf", ruta_sin_texto, "--out-dir", out_dir])
        self.assertNotEqual(codigo, 0)
        self.assertIn("out-dir", salida["error"])
        self.assertFalse(Path(out_dir).exists())

    def test_out_dir_no_gestionado_rechazado_sin_png(self):
        pymupdf = pytest.importorskip("pymupdf")
        ruta = str(Path(self.tempdir.name) / "unmanaged.pdf")
        doc = pymupdf.open()
        doc.new_page()
        doc.save(ruta, deflate=True)
        doc.close()
        out_dir = Path(self.tempdir.name) / "unmanaged"
        out_dir.mkdir()
        codigo, salida = self._run(["extraer-pdf", ruta, "--out-dir", str(out_dir)])
        self.assertNotEqual(codigo, 0)
        self.assertIn("dedicada", salida["error"])
        self.assertEqual(list(out_dir.iterdir()), [])

    def test_archivo_grande_rechazado_antes_de_abrirlo(self):
        ruta = Path(self.tempdir.name) / "grande.pdf"
        with ruta.open("wb") as fh:
            fh.seek(telegram_ingesta.PDF_MAX_BYTES + 1)
            fh.write(b"\0")
        codigo, salida = self._run(["extraer-pdf", str(ruta)])
        self.assertNotEqual(codigo, 0)
        self.assertIn("error", salida)

    def test_pdf_corrupto_da_error_claro_sin_traceback(self):
        pytest.importorskip("pymupdf")
        ruta = Path(self.tempdir.name) / "corrupto.pdf"
        ruta.write_bytes(b"%PDF-1.4 esto no es un PDF valido" + b"\xff" * 200)
        codigo, salida = self._run(["extraer-pdf", str(ruta)])
        self.assertNotEqual(codigo, 0)
        self.assertIn("error", salida)

    def test_pdf_cifrado_da_error_claro(self):
        pymupdf = pytest.importorskip("pymupdf")

        ruta = str(Path(self.tempdir.name) / "cifrado.pdf")
        doc = pymupdf.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "contenido secreto")
        doc.save(
            ruta,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="clave-usuario",
            owner_pw="clave-owner",
        )
        doc.close()

        codigo, salida = self._run(["extraer-pdf", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("cifrado", salida["error"])

    def test_mas_de_20_paginas_trunca_y_limita_caracteres(self):
        pymupdf = pytest.importorskip("pymupdf")

        ruta = str(Path(self.tempdir.name) / "muchas-paginas.pdf")
        doc = pymupdf.open()
        texto_por_pagina = "X" * 3000
        total_paginas = 25
        for indice in range(total_paginas):
            pagina = doc.new_page()
            pagina.insert_text((72, 72), f"{texto_por_pagina}-{indice}")
        doc.save(ruta)
        doc.close()

        codigo, salida = self._run(["extraer-pdf", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["fuente"], "pdf_texto")
        self.assertEqual(salida["paginas"], total_paginas)
        self.assertTrue(salida["truncado"])
        self.assertLessEqual(len(salida["texto"]), telegram_ingesta.PDF_MAX_CARACTERES)
        self.assertNotIn(f"-{total_paginas - 1}", salida["texto"])

    def test_una_sola_pagina_con_texto_larguisimo_trunca(self):
        # Una página muy comprimida debe quedar limitada por el proceso
        # aislado y la respuesta de texto debe truncarse a 50.000 caracteres.
        #
        # El fixture usa `insert_textbox` (no `insert_text`) para que
        # pymupdf envuelva el texto DENTRO del rectángulo de la página: con
        # `insert_text` en un solo punto, sin textbox, un string de 60.000
        # caracteres a fontsize=1 se dibuja en una sola línea que se
        # extiende muy por fuera del ancho real de la página -- y
        # `get_text()` solo extrae lo que cae dentro del rectángulo de la
        # página, así que la mayor parte del texto nunca se podía extraer
        # (el bug estaba en este fixture, no en `cmd_extraer_pdf`: nunca se
        # llegaba a superar el límite de 50.000 caracteres para disparar el
        # truncado). Se usan palabras cortas separadas por espacios para que
        # el wrap de `insert_textbox` tenga dónde cortar línea.
        pymupdf = pytest.importorskip("pymupdf")

        ruta = str(Path(self.tempdir.name) / "texto-larguisimo.pdf")
        doc = pymupdf.open()
        pagina = doc.new_page()
        texto = ("AAAAAAAAAAAAAAAAAAAA " * 3000)  # 63.000 caracteres > PDF_MAX_CARACTERES
        rc = pagina.insert_textbox(pagina.rect, texto, fontsize=1)
        assert rc >= 0, "el texto del fixture no entró en la página a fontsize=1"
        doc.save(ruta, deflate=True)
        doc.close()

        codigo, salida = self._run(["extraer-pdf", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["fuente"], "pdf_texto")
        self.assertTrue(salida["truncado"])
        self.assertLessEqual(len(salida["texto"]), telegram_ingesta.PDF_MAX_CARACTERES)

    def test_mediabox_enorme_reduce_el_zoom_en_vez_de_un_pixmap_gigante(self):
        pymupdf = pytest.importorskip("pymupdf")

        ruta = str(Path(self.tempdir.name) / "mediabox-enorme.pdf")
        doc = pymupdf.open()
        doc.new_page(width=3000, height=3000)
        doc.save(ruta)
        doc.close()

        managed_pdf, out_dir = self._managed_pdf(ruta)
        codigo, salida = self._run(["extraer-pdf", managed_pdf, "--out-dir", out_dir])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["fuente"], "sin_texto")
        self.assertEqual(len(salida["imagenes"]), 1)
        self.assertTrue(any("zoom reducido" in advertencia for advertencia in salida["advertencias"]))

        pixmap_generado = pymupdf.Pixmap(salida["imagenes"][0])
        self.assertLessEqual(
            pixmap_generado.width * pixmap_generado.height, telegram_ingesta.PDF_MAX_PIXELS_RENDER,
        )

    def test_pagina_alargada_limita_cada_dimension(self):
        pymupdf = pytest.importorskip("pymupdf")
        ruta = str(Path(self.tempdir.name) / "alargada.pdf")
        doc = pymupdf.open()
        doc.new_page(width=10, height=10000)
        doc.save(ruta)
        doc.close()
        managed_pdf, out_dir = self._managed_pdf(ruta)
        codigo, salida = self._run(["extraer-pdf", managed_pdf, "--out-dir", out_dir])
        self.assertEqual(codigo, 0)
        for image_path in salida["imagenes"]:
            pixmap = pymupdf.Pixmap(image_path)
            self.assertLessEqual(pixmap.width, telegram_ingesta.PDF_MAX_DIMENSION_RENDER)
            self.assertLessEqual(pixmap.height, telegram_ingesta.PDF_MAX_DIMENSION_RENDER)

    def test_timeout_del_subproceso_es_json_limpio(self):
        ruta = Path(self.tempdir.name) / "synthetic.pdf"
        ruta.write_bytes(b"%PDF-1.4")
        with unittest.mock.patch("telegram_ingesta.subprocess.run", side_effect=telegram_ingesta.subprocess.TimeoutExpired("pdf", 20)):
            codigo, salida = self._run(["extraer-pdf", str(ruta)])
        self.assertNotEqual(codigo, 0)
        self.assertIn("tiempo máximo", salida["error"])


# --- extraer-campos (parseo determinista de comprobantes, brief parte C) ---


class ExtraerCamposComprobanteTests(unittest.TestCase):
    """Unidad de `extraer_campos_comprobante` -- solo regex, sin red ni
    archivos (ver `ExtraerCamposCliTests` para el subcomando completo)."""

    def test_mercadopago_transferencia_desde_texto(self):
        campos = telegram_ingesta.extraer_campos_comprobante(TEXTO_COMPROBANTE_MERCADOPAGO)
        self.assertFalse(campos["formato_desconocido"])
        self.assertEqual(campos["monto"], 27000.0)
        self.assertEqual(campos["fecha"], "2026-08-11")
        self.assertEqual(campos["medio_pago"], "Transferencia")
        self.assertEqual(campos["comercio"], "Lucía Fernández")
        self.assertIsNone(campos["descripcion"])  # "Motivo: Varios" es el motivo genérico default
        self.assertEqual(campos["nro_operacion"], "173192245876")
        self.assertEqual(campos["titular_origen"], "Ignacio Torres")
        self.assertEqual(campos["emisor"], "Mercado Pago")

    def test_formato_mp_alterado_es_desconocido(self):
        for altered in (
            TEXTO_COMPROBANTE_MERCADOPAGO.replace("Mercado Pago\nCVU", "Otro Banco\nCVU", 1),
            TEXTO_COMPROBANTE_MERCADOPAGO.replace("Mercado Pago\nCVU: 0000000000000000000002", "Otro Banco\nCVU: 0000000000000000000002"),
            TEXTO_COMPROBANTE_MERCADOPAGO + "Línea adicional\n",
        ):
            with self.subTest(altered=altered[-30:]):
                result = telegram_ingesta.extraer_campos_comprobante(altered)
                self.assertTrue(result["formato_desconocido"])
                self.assertIsNone(result["monto"])

    def test_mercadopago_transferencia_motivo_no_generico_se_muestra(self):
        texto = TEXTO_COMPROBANTE_MERCADOPAGO.replace("Motivo: Varios", "Motivo: Alquiler agosto")
        campos = telegram_ingesta.extraer_campos_comprobante(texto)
        self.assertEqual(campos["descripcion"], "Motivo: Alquiler agosto")

    def test_formato_desconocido_no_inventa_nada(self):
        campos = telegram_ingesta.extraer_campos_comprobante(
            "esto no es un comprobante conocido\notra línea de texto libre"
        )
        self.assertTrue(campos["formato_desconocido"])
        for campo in telegram_ingesta.CAMPOS_EXTRAER_CAMPOS:
            self.assertIsNone(campos[campo])

    def test_formato_vacio_es_desconocido(self):
        campos = telegram_ingesta.extraer_campos_comprobante("")
        self.assertTrue(campos["formato_desconocido"])

    def test_comprobante_incompleto_es_desconocido_no_explota(self):
        # Corta el texto a mitad del bloque "De" -- `_siguiente()` se queda
        # sin líneas antes de completar el parseo: tiene que devolver
        # `formato_desconocido=True`, nunca una excepción sin capturar.
        texto_incompleto = "\n".join(TEXTO_COMPROBANTE_MERCADOPAGO.strip().splitlines()[:6])
        campos = telegram_ingesta.extraer_campos_comprobante(texto_incompleto)
        self.assertTrue(campos["formato_desconocido"])


class ExtraerCamposCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = telegram_ingesta.main(argv)
        contenido = salida.getvalue().strip()
        return codigo, (json.loads(contenido) if contenido else None)

    def test_extraer_campos_desde_archivo_de_texto(self):
        ruta = Path(self.tempdir.name) / "comprobante.txt"
        ruta.write_text(TEXTO_COMPROBANTE_MERCADOPAGO, encoding="utf-8")
        codigo, salida = self._run(["extraer-campos", "--texto", str(ruta)])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["monto"], 27000.0)
        self.assertEqual(salida["nro_operacion"], "173192245876")
        # El titular sintético del fixture no figura entre los dos mapeados.
        self.assertIsNone(salida["pagado_por_sugerido"])

    def test_extraer_campos_desde_stdin(self):
        with unittest.mock.patch("sys.stdin", io.StringIO(TEXTO_COMPROBANTE_MERCADOPAGO)):
            codigo, salida = self._run(["extraer-campos", "--texto", "-"])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["titular_origen"], "Ignacio Torres")

    def test_extraer_campos_sugiere_pagado_por_con_titular_mapeado(self):
        usuarios_ruta = Path(self.tempdir.name) / "usuarios.json"
        usuarios_ruta.write_text(
            json.dumps({"titulares": {"ignacio torres": "JD"}}, ensure_ascii=False), encoding="utf-8",
        )
        ruta = Path(self.tempdir.name) / "comprobante.txt"
        ruta.write_text(TEXTO_COMPROBANTE_MERCADOPAGO, encoding="utf-8")
        codigo, salida = self._run([
            "--usuarios-file", str(usuarios_ruta), "extraer-campos", "--texto", str(ruta),
        ])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["pagado_por_sugerido"], "JD")

    def test_titulares_configurados_jd_y_pinki(self):
        for titular, esperado in (("Juan David Guzmán", "JD"), ("Regina Pinchetti", "Pinki")):
            ruta = Path(self.tempdir.name) / "titular.txt"
            ruta.write_text(
                TEXTO_COMPROBANTE_MERCADOPAGO.replace("Ignacio Torres", titular),
                encoding="utf-8",
            )
            codigo, salida = self._run(["extraer-campos", "--texto", str(ruta)])
            self.assertEqual(codigo, 0)
            self.assertEqual(salida["titular_origen"], titular)
            self.assertEqual(salida["pagado_por_sugerido"], esperado)

    def test_extraer_campos_titular_sin_mapeo_no_sugiere_nada(self):
        usuarios_ruta = Path(self.tempdir.name) / "usuarios.json"
        usuarios_ruta.write_text(
            json.dumps({"titulares": {"otra persona": "JD"}}, ensure_ascii=False), encoding="utf-8",
        )
        ruta = Path(self.tempdir.name) / "comprobante.txt"
        ruta.write_text(TEXTO_COMPROBANTE_MERCADOPAGO, encoding="utf-8")
        codigo, salida = self._run([
            "--usuarios-file", str(usuarios_ruta), "extraer-campos", "--texto", str(ruta),
        ])
        self.assertEqual(codigo, 0)
        self.assertIsNone(salida["pagado_por_sugerido"])

    def test_extraer_campos_desde_pdf_generado_en_el_test(self):
        # PDF SINTÉTICO generado en el propio test (nunca el real de
        # `fixtures-reales/`) -- mismo formato exacto, una línea por
        # `insert_text` para que `extraer-pdf` devuelva el texto con los
        # mismos saltos de línea que espera el parser de `extraer-campos`.
        pymupdf = pytest.importorskip("pymupdf")
        ruta_pdf = str(Path(self.tempdir.name) / "comprobante.pdf")
        doc = pymupdf.open()
        pagina = doc.new_page()
        y = 72
        for linea in TEXTO_COMPROBANTE_MERCADOPAGO.strip().splitlines():
            pagina.insert_text((72, y), linea, fontsize=10)
            y += 14
        doc.save(ruta_pdf)
        doc.close()

        codigo, extraido = self._run(["extraer-pdf", ruta_pdf])
        self.assertEqual(codigo, 0)
        self.assertEqual(extraido["fuente"], "pdf_texto")

        ruta_texto = Path(self.tempdir.name) / "texto-del-pdf.txt"
        ruta_texto.write_text(extraido["texto"], encoding="utf-8")
        codigo, campos = self._run(["extraer-campos", "--texto", str(ruta_texto)])
        self.assertEqual(codigo, 0)
        self.assertFalse(campos["formato_desconocido"])
        self.assertEqual(campos["monto"], 27000.0)
        self.assertEqual(campos["fecha"], "2026-08-11")
        self.assertEqual(campos["nro_operacion"], "173192245876")


# --- normalizar ---------------------------------------------------------


class NormalizarTests(_ApiServerTestCase):
    def test_categoria_y_subcategoria_sin_acento_sin_default_pagado_por(self):
        # Juan, 2026-10-25: "tenés que preguntar siempre quién hizo el
        # gasto" -- `pagado_por` NUNCA se completa a partir de quién cargó
        # el mensaje de Telegram (`telegram.user_id`), aunque sea un
        # usuario conocido: siempre queda en `campos_faltantes` salvo que
        # venga explícito en la entrada.
        entrada = {
            "monto": "1.500", "fecha": "2026-04-10", "comercio": "Super",
            "categoria": "comida", "subcategoria": "delivery", "medio_pago": "Efectivo",
            "telegram": {"chat_id": "-5500256401", "user_id": "7355824354", "message_id": "42"},
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["categoria"], "Comida")
        self.assertEqual(salida["borrador"]["subcategoria"], "Delivery")
        self.assertEqual(salida["borrador"]["monto"], 1500.0)
        self.assertNotIn("pagado_por", salida["borrador"])
        self.assertEqual(salida["borrador"]["descripcion_original"], "Super")
        self.assertEqual(salida["borrador"]["chat_id"], "-5500256401")
        self.assertEqual(salida["borrador"]["telegram_user_id"], "7355824354")
        self.assertNotIn(
            "pagado_por", [d["campo"] for d in salida["defaults_aplicados"]],
        )
        self.assertIn({"campo": "cuotas_total", "valor": 1}, salida["defaults_aplicados"])
        self.assertEqual(salida["campos_faltantes"], ["pagado_por"])

    def test_titular_origen_mapeado_sugiere_pagado_por_pero_sigue_en_faltantes(self):
        # Juan, 2026-10-25 (brief parte C): un comprobante con titular
        # mapeado en `telegram_usuarios.json["titulares"]` propone
        # `pagado_por_sugerido`, pero `pagado_por` sigue en
        # `campos_faltantes` -- la sugerencia se confirma, nunca se asume.
        usuarios_ruta = self._write_json(
            {
                "7355824354": {"persona": "JD", "nombre": "Juan"},
                "8842208210": {"persona": "Pinki", "nombre": "Regi"},
                "titulares": {"ignacio torres": "JD"},
            },
            nombre="usuarios-con-titulares.json",
        )
        entrada = {
            "monto": 27000, "fecha": "2026-08-11", "categoria": "Comida",
            "medio_pago": "Transferencia", "titular_origen": "Ignacio Torres",
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli([
            "--usuarios-file", usuarios_ruta, "normalizar", "--tipo", "gasto", "--json", ruta,
        ])
        self.assertEqual(codigo, 0)
        self.assertNotIn("pagado_por", salida["borrador"])
        self.assertIn("pagado_por", salida["campos_faltantes"])
        self.assertEqual(salida["pagado_por_sugerido"], "JD")
        self.assertTrue(any("inferido del comprobante" in a for a in salida["advertencias"]))

    def test_titular_origen_sin_mapeo_no_sugiere_nada(self):
        entrada = {
            "monto": 27000, "fecha": "2026-08-11", "categoria": "Comida",
            "medio_pago": "Transferencia", "titular_origen": "Alguien Sin Mapear",
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("pagado_por", salida["campos_faltantes"])
        self.assertNotIn("pagado_por_sugerido", salida)

    def test_pinki_carga_comprobante_de_jd_sin_confirmarlo(self):
        entrada = {
            "monto": 27000, "fecha": "2026-08-11", "categoria": "Comida",
            "medio_pago": "Transferencia", "titular_origen": "Juan David Guzmán",
            "telegram": {"chat_id": "-5500256401", "user_id": "8842208210", "message_id": "99"},
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["telegram_user_id"], "8842208210")
        self.assertEqual(salida["pagado_por_sugerido"], "JD")
        self.assertIn("pagado_por", salida["campos_faltantes"])
        self.assertNotIn("pagado_por", salida["borrador"])

    def test_subcategoria_con_acento_en_catalogo_input_sin_acento(self):
        entrada = {
            "monto": 500, "fecha": "2026-04-10", "categoria": "comida", "subcategoria": "verduleria",
            "medio_pago": "Efectivo", "pagado_por": "JD",
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["subcategoria"], "Verdulería")

    def test_credito_ignora_identificacion_legacy_y_conserva_default(self):
        entrada = {
            "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Crédito", "tarjeta": "Visa", "banco": "Banco de prueba",
            "pagado_por": "Común",
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["campos_faltantes"], [])
        self.assertNotIn("tarjeta_id", salida["borrador"])
        self.assertNotIn("tarjeta", salida["borrador"])
        self.assertNotIn("banco", salida["borrador"])
        self.assertEqual(salida["borrador"]["tipo_proporcion"], "dinamico")

    def test_default_tipo_proporcion_dinamico_tambien_para_jd_y_pinki(self):
        for pagado_por in ("JD", "Pinki"):
            with self.subTest(pagado_por=pagado_por):
                entrada = {
                    "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
                    "medio_pago": "Efectivo", "pagado_por": pagado_por,
                }
                ruta = self._write_json(entrada, nombre=f"entrada-{pagado_por}.json")
                codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
                self.assertEqual(codigo, 0)
                self.assertEqual(salida["borrador"]["tipo_proporcion"], "dinamico")
                self.assertIn({"campo": "tipo_proporcion", "valor": "dinamico"}, salida["defaults_aplicados"])

    def test_usuario_telegram_desconocido_da_error_explicito(self):
        entrada = {
            "monto": 100, "fecha": "2026-04-10", "categoria": "Comida",
            "telegram": {"user_id": "000000"},
        }
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("desconocido", salida["error"])

    def test_fecha_faltante_usa_hoy_y_advierte(self):
        entrada = {"monto": 100, "categoria": "Comida", "medio_pago": "Efectivo", "pagado_por": "JD"}
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        hoy = date.today().isoformat()
        self.assertEqual(salida["borrador"]["fecha"], hoy)
        self.assertTrue(any("fecha" in advertencia for advertencia in salida["advertencias"]))

    def test_medio_pago_faltante_no_se_inventa(self):
        entrada = {"monto": 100, "fecha": "2026-04-10", "categoria": "Comida", "pagado_por": "JD"}
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("medio_pago", salida["campos_faltantes"])
        self.assertNotIn("medio_pago", salida["borrador"])

    def test_cuotas_estrictas_en_normalizacion(self):
        base = {"monto": 500, "fecha": "2026-04-10", "categoria": "Comida", "medio_pago": "Efectivo", "pagado_por": "JD"}
        for value in (2.9, True, 0, 121):
            with self.subTest(value=value):
                path = self._write_json({**base, "cuotas_total": value})
                status, result = self.run_cli(["normalizar", "--tipo", "gasto", "--json", path])
                self.assertNotEqual(status, 0)
                self.assertIn("cuotas_total", result["error"])
        for value in (1, 3, 120):
            with self.subTest(value=value):
                path = self._write_json({**base, "cuotas_total": value})
                status, result = self.run_cli(["normalizar", "--tipo", "gasto", "--json", path])
                self.assertEqual(status, 0)
                self.assertEqual(result["borrador"]["cuotas_total"], value)

    def test_ingreso_salario_advierte_cambio_de_proporcion(self):
        entrada = {"monto": 500000, "fecha": "2026-04-01", "categoria": "Salario", "persona": "JD"}
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "ingreso", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("cambia la proporción del mes.", salida["advertencias"])

    def test_monto_entero_enorme_da_error_de_validacion_limpio(self):
        # 10**400 hace que `float()` levante `OverflowError`, no `ValueError`
        # -- tiene que seguir siendo un error de validación claro (sin
        # traceback), nunca una excepción sin capturar por `main()`.
        entrada = {"monto": 10**400, "fecha": "2026-04-10", "categoria": "Comida", "pagado_por": "JD"}
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("monto", salida["error"])


# --- proporción custom (CLI + backend) --------------------------------------


class ProporcionCustomTests(_ApiServerTestCase):
    def _entrada_custom(self, proporcion_jd, nombre="custom.json"):
        entrada = {
            "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
            "tipo_proporcion": "custom", "proporcion_jd": proporcion_jd,
        }
        return self._write_json(entrada, nombre=nombre)

    def test_cli_rechaza_proporcion_jd_mayor_a_100(self):
        ruta = self._entrada_custom(120)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("proporcion_jd", salida["error"])

    def test_cli_rechaza_proporcion_jd_negativa(self):
        ruta = self._entrada_custom(-5)
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("proporcion_jd", salida["error"])

    def test_cli_rechaza_proporcion_jd_nan(self):
        ruta = self._entrada_custom(float("nan"))
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("proporcion_jd", salida["error"])

    def test_cli_rechaza_proporcion_jd_string(self):
        ruta = self._entrada_custom("cincuenta")
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("proporcion_jd", salida["error"])

    def test_cli_acepta_proporcion_personal_100_y_0(self):
        for pct in (100, 0):
            with self.subTest(proporcion_jd=pct):
                ruta = self._entrada_custom(pct, nombre=f"personal-{pct}.json")
                codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
                self.assertEqual(codigo, 0)
                self.assertEqual(salida["borrador"]["proporcion_jd"], pct)
                self.assertEqual(salida["borrador"]["proporcion_pinki"], 100 - pct)

    def _borrador_gasto_custom(self, proporcion_jd, proporcion_pinki):
        return {
            "monto": 1000.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
            "tipo_proporcion": "custom",
            "proporcion_jd": proporcion_jd, "proporcion_pinki": proporcion_pinki,
        }

    def test_backend_rechaza_proporciones_fuera_de_rango_vía_guardar(self):
        # `guardar` no vuelve a correr `normalizar`: un borrador armado a
        # mano con proporciones inválidas debe seguir siendo rechazado por
        # la API (`validaciones.validar_expense`), no solo por el CLI.
        ruta = self._write_json(self._borrador_gasto_custom(120, -20))
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta, "--confirmado"])
        self.assertNotEqual(codigo, 0)
        self.assertIn("error", salida)

    def test_backend_acepta_proporcion_personal_100_0_vía_guardar(self):
        ruta = self._write_json(self._borrador_gasto_custom(100, 0))
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta, "--confirmado"])
        self.assertEqual(codigo, 0)
        self.assertIsInstance(salida["id"], int)

    def test_custom_sin_porcentaje_queda_en_campos_faltantes_y_la_pregunta_lo_pide(self):
        entrada = {
            "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD", "tipo_proporcion": "custom",
        }
        ruta = self._write_json(entrada, nombre="custom-sin-pct.json")
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("proporcion_jd", salida["campos_faltantes"])
        self.assertNotIn("proporcion_jd", salida["borrador"])
        self.assertEqual(salida["borrador"]["tipo_proporcion"], "custom")

        ruta_normalizado = self._write_json(salida, nombre="normalizado-custom-sin-pct.json")
        codigo, pregunta = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta_normalizado])
        self.assertEqual(codigo, 0)
        self.assertIn("¿Qué % pone JD?", pregunta["mensaje"])

    def test_dinamico_explicito_con_proporcion_jd_se_ignora_con_advertencia(self):
        entrada = {
            "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
            "tipo_proporcion": "dinamico", "proporcion_jd": 70,
        }
        ruta = self._write_json(entrada, nombre="dinamico-con-pct.json")
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["tipo_proporcion"], "dinamico")
        self.assertNotIn("proporcion_jd", salida["borrador"])
        self.assertNotIn("proporcion_pinki", salida["borrador"])
        self.assertTrue(any("proporcion_jd" in a for a in salida["advertencias"]))

    def test_default_dinamico_con_proporcion_jd_tambien_se_ignora(self):
        # Mismo caso, pero sin `tipo_proporcion` explícito (toma el default
        # 'dinamico') -- la proporción igual debe ignorarse con advertencia.
        entrada = {
            "monto": 1000, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD", "proporcion_jd": 70,
        }
        ruta = self._write_json(entrada, nombre="default-dinamico-con-pct.json")
        codigo, salida = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["tipo_proporcion"], "dinamico")
        self.assertNotIn("proporcion_jd", salida["borrador"])
        self.assertTrue(any("proporcion_jd" in a for a in salida["advertencias"]))


# --- pregunta (snapshot de texto) -------------------------------------------


class PreguntaTests(_ApiServerTestCase):
    def test_pregunta_final_muestra_cuotas_explicitas(self):
        entrada = {"monto": 300, "fecha": "2026-10-09", "categoria": "Comida", "medio_pago": "Efectivo", "pagado_por": "JD", "cuotas_total": 3}
        path = self._write_json(entrada)
        status, normalizado = self.run_cli(["normalizar", "--tipo", "gasto", "--json", path])
        self.assertEqual(status, 0)
        path_normalizado = self._write_json(normalizado)
        status, pregunta = self.run_cli(["pregunta", "--tipo", "gasto", "--json", path_normalizado])
        self.assertEqual(status, 0)
        self.assertIn("Cuotas: 3", pregunta["mensaje"])

    def test_pregunta_sin_faltantes_snapshot(self):
        entrada = {
            "monto": "12.350", "fecha": "2026-10-09", "categoria": "Comida", "subcategoria": "Delivery",
            "medio_pago": "Crédito", "tarjeta": "Visa", "pagado_por": "Común",
        }
        ruta = self._write_json(entrada)
        codigo, normalizado = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(normalizado["campos_faltantes"], [])

        ruta_normalizado = self._write_json(normalizado, nombre="normalizado.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta_normalizado])
        self.assertEqual(codigo, 0)
        esperado = (
            "Che, esto es lo que entendí — avisame si hay que corregir algo:\n"
            "💰 $12.350 · Comida > Delivery · 💳 Crédito · Pagó: Común · "
            "Reparto: dinámico (según sueldos del mes) · Cuotas: 1 · 📅 09/10\n"
            "¿Subo así o cambio algo?"
        )
        self.assertEqual(salida["mensaje"], esperado)

    def test_pregunta_sin_faltantes_snapshot_reparto_custom(self):
        entrada = {
            "monto": "12.350", "fecha": "2026-10-09", "categoria": "Comida", "subcategoria": "Delivery",
            "medio_pago": "Efectivo", "pagado_por": "JD",
            "tipo_proporcion": "custom", "proporcion_jd": 70,
        }
        ruta = self._write_json(entrada)
        codigo, normalizado = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(normalizado["campos_faltantes"], [])

        ruta_normalizado = self._write_json(normalizado, nombre="normalizado.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta_normalizado])
        self.assertEqual(codigo, 0)
        esperado = (
            "Che, esto es lo que entendí — avisame si hay que corregir algo:\n"
            "💰 $12.350 · Comida > Delivery · 💳 Efectivo · Pagó: JD · "
            "Reparto: 70% JD / 30% Pinki · Cuotas: 1 · 📅 09/10\n"
            "¿Subo así o cambio algo?"
        )
        self.assertEqual(salida["mensaje"], esperado)

    def test_pregunta_credito_sin_identificacion_pide_confirmacion(self):
        entrada = {"monto": 500, "fecha": "2026-04-10", "categoria": "Comida",
                   "medio_pago": "Crédito", "pagado_por": "JD"}
        ruta = self._write_json(entrada)
        codigo, normalizado = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(normalizado["campos_faltantes"], [])
        ruta_normalizado = self._write_json(normalizado, nombre="normalizado.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta_normalizado])
        self.assertEqual(codigo, 0)
        self.assertIn("💳 Crédito", salida["mensaje"])
        self.assertIn("¿Subo así o cambio algo?", salida["mensaje"])
        self.assertNotIn("tarjeta", salida["mensaje"].lower())

    def test_pregunta_consolida_todos_los_faltantes_sin_identificacion(self):
        entrada = {"monto": 500, "fecha": "2026-04-10", "medio_pago": "Crédito"}
        ruta = self._write_json(entrada)
        codigo, normalizado = self.run_cli(["normalizar", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(normalizado["campos_faltantes"], ["categoria", "pagado_por"])
        ruta_normalizado = self._write_json(normalizado, nombre="normalizado.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta_normalizado])
        self.assertEqual(codigo, 0)
        self.assertIn("1) ¿Categoría?", salida["mensaje"])
        self.assertIn("2) ¿Quién pagó?", salida["mensaje"])
        self.assertNotIn("tarjeta", salida["mensaje"].lower())

    def test_pregunta_tipo_proporcion_faltante_muestra_opciones_dinamico_custom(self):
        borrador = {
            "monto": 500, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
        }
        entrada = {"borrador": borrador, "campos_faltantes": ["tipo_proporcion"], "advertencias": []}
        ruta = self._write_json(entrada, nombre="pregunta-tipo-proporcion.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        esperado = (
            "Me falta esto para subirlo, contestame junto:\n"
            "1) ¿Cómo repartimos este gasto? (opciones: dinámico / custom (indicá %))"
        )
        self.assertEqual(salida["mensaje"], esperado)

    def test_pregunta_no_formatea_none_aunque_el_json_de_entrada_sea_inconsistente(self):
        # `pregunta` puede recibir un JSON armado a mano (no necesariamente
        # la salida real de `normalizar`): un `campos_faltantes` vacío con
        # `tipo_proporcion='custom'` y `proporcion_jd` ausente no debe
        # romper con un `TypeError` al armar el resumen del reparto.
        borrador = {
            "monto": 1500.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD", "tipo_proporcion": "custom",
        }
        entrada = {"borrador": borrador, "campos_faltantes": [], "advertencias": []}
        ruta = self._write_json(entrada, nombre="pregunta-custom-sin-pct.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("Reparto: dinámico (según sueldos del mes)", salida["mensaje"])


# --- pregunta --con-comprobante (brief parte D) -----------------------------


class PreguntaConComprobanteTests(_ApiServerTestCase):
    def test_snapshot_pide_solo_lo_minimo(self):
        borrador = {
            "monto": 27000.0, "fecha": "2026-08-11", "medio_pago": "Transferencia",
            "descripcion_original": "Ignacio T.", "tipo_proporcion": "dinamico",
        }
        entrada = {"borrador": borrador, "campos_faltantes": ["pagado_por", "categoria"], "advertencias": []}
        ruta = self._write_json(entrada, nombre="pregunta-comprobante.json")
        codigo, salida = self.run_cli([
            "pregunta", "--tipo", "gasto", "--json", ruta, "--con-comprobante",
        ])
        self.assertEqual(codigo, 0)
        esperado = (
            "Leí del comprobante: $27.000 · transferencia a Ignacio T. · 11/08\n"
            "1) ¿Quién lo pagó? (JD / Pinki / Común)\n"
            "2) ¿Categoría? (opciones: Hogar, Comida, Mascotas)\n"
            "Reparto: dinámico (según sueldos del mes)"
        )
        self.assertEqual(salida["mensaje"], esperado)

    def test_muestra_pagado_por_sugerido_del_comprobante(self):
        borrador = {
            "monto": 27000.0, "fecha": "2026-08-11", "medio_pago": "Transferencia",
            "descripcion_original": "Ignacio T.",
        }
        entrada = {
            "borrador": borrador, "campos_faltantes": ["pagado_por", "categoria"],
            "advertencias": [], "pagado_por_sugerido": "JD",
        }
        ruta = self._write_json(entrada, nombre="pregunta-comprobante-sugerido.json")
        codigo, salida = self.run_cli([
            "pregunta", "--tipo", "gasto", "--json", ruta, "--con-comprobante",
        ])
        self.assertEqual(codigo, 0)
        self.assertIn(
            "1) Veo que salió de la cuenta de Juan/JD, ¿lo pagó JD? (JD / Pinki / Común)",
            salida["mensaje"],
        )

    def test_muestra_inferencia_pinki_para_confirmar(self):
        borrador = {
            "monto": 27000.0, "fecha": "2026-08-11", "medio_pago": "Transferencia",
            "descripcion_original": "Destino", "categoria": "Comida",
        }
        entrada = {"borrador": borrador, "pagado_por_sugerido": "Pinki"}
        ruta = self._write_json(entrada)
        codigo, salida = self.run_cli([
            "pregunta", "--tipo", "gasto", "--json", ruta, "--con-comprobante",
        ])
        self.assertEqual(codigo, 0)
        self.assertIn("Veo que salió de la cuenta de Regina/Pinki, ¿lo pagó Pinki?", salida["mensaje"])

    def test_sin_faltantes_cierra_igual_que_la_pregunta_normal(self):
        borrador = {
            "monto": 27000.0, "fecha": "2026-08-11", "medio_pago": "Transferencia",
            "descripcion_original": "Ignacio T.", "categoria": "Comida", "pagado_por": "JD",
            "tipo_proporcion": "dinamico",
        }
        entrada = {"borrador": borrador, "campos_faltantes": [], "advertencias": []}
        ruta = self._write_json(entrada, nombre="pregunta-comprobante-completo.json")
        codigo, salida = self.run_cli([
            "pregunta", "--tipo", "gasto", "--json", ruta, "--con-comprobante",
        ])
        self.assertEqual(codigo, 0)
        esperado = (
            "Leí del comprobante: $27.000 · transferencia a Ignacio T. · 11/08\n"
            "Categoría: Comida · Pagó: JD\n"
            "Reparto: dinámico (según sueldos del mes)\n"
            "Cuotas: 1\n"
            "¿Subo así o cambio algo?"
        )
        self.assertEqual(salida["mensaje"], esperado)

    def test_flag_equivalente_a_campo_con_comprobante_en_el_borrador(self):
        # Brief: "flag --con-comprobante o campo en el borrador" -- ambas
        # formas tienen que activar el mismo resumen.
        borrador = {
            "monto": 27000.0, "fecha": "2026-08-11", "medio_pago": "Transferencia",
            "descripcion_original": "Ignacio T.", "con_comprobante": True,
        }
        entrada = {"borrador": borrador, "campos_faltantes": ["pagado_por", "categoria"], "advertencias": []}
        ruta = self._write_json(entrada, nombre="pregunta-comprobante-campo.json")
        codigo, salida = self.run_cli(["pregunta", "--tipo", "gasto", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertTrue(salida["mensaje"].startswith("Leí del comprobante:"))


# --- guardar (único subcomando que escribe) ---------------------------------


class GuardarTests(_ApiServerTestCase):
    def _borrador_gasto(self, **cambios):
        base = {
            "monto": 1500.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
        }
        base.update(cambios)
        return base

    def _contar_gastos(self):
        with db.get_connection(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"]

    def test_guardar_sin_confirmado_no_escribe_nada(self):
        ruta = self._write_json(self._borrador_gasto())
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta])
        self.assertNotEqual(codigo, 0)
        self.assertIn("confirmado", salida["error"])
        self.assertEqual(self._contar_gastos(), 0)

    def test_guardar_con_campos_faltantes_no_escribe_nada(self):
        borrador = self._borrador_gasto()
        del borrador["categoria"]
        ruta = self._write_json(borrador)
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta, "--confirmado"])
        self.assertNotEqual(codigo, 0)
        self.assertEqual(salida["campos_faltantes"], ["categoria"])
        self.assertEqual(self._contar_gastos(), 0)

    def test_guardar_exitoso_devuelve_id_y_avisos(self):
        ruta = self._write_json(self._borrador_gasto())
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta, "--confirmado"])
        self.assertEqual(codigo, 0)
        self.assertIsInstance(salida["id"], int)
        self.assertEqual(salida["avisos_credito_nuevos"], [])
        self.assertEqual(self._contar_gastos(), 1)

    def test_dedupe_bloquea_guardado_y_forzar_duplicado_lo_permite(self):
        ruta_borrador1 = self._write_json(self._borrador_gasto())
        ruta_comprobante1 = self._write_json(
            {"hash_archivo": "hash-1", "monto_detectado": 1500.0, "fecha_detectada": "2026-04-10"},
            nombre="comprobante1.json",
        )
        codigo, salida = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador1,
            "--comprobante", ruta_comprobante1, "--confirmado",
        ])
        self.assertEqual(codigo, 0)
        self.assertEqual(self._contar_gastos(), 1)

        ruta_borrador2 = self._write_json(
            self._borrador_gasto(descripcion_original="otro comercio"), nombre="borrador2.json",
        )
        ruta_comprobante2 = self._write_json(
            {"hash_archivo": "hash-2", "monto_detectado": 1500.0, "fecha_detectada": "2026-04-10"},
            nombre="comprobante2.json",
        )

        codigo, salida = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador2,
            "--comprobante", ruta_comprobante2, "--confirmado",
        ])
        self.assertNotEqual(codigo, 0)
        self.assertTrue(salida["duplicado"])
        self.assertEqual(salida["dedupe"]["coincidencia"], "aproximada")
        self.assertEqual(self._contar_gastos(), 1)

        codigo, salida = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador2,
            "--comprobante", ruta_comprobante2, "--confirmado", "--forzar-duplicado",
        ])
        self.assertEqual(codigo, 0)
        self.assertEqual(self._contar_gastos(), 2)

    def test_dedupe_por_nro_operacion_bloquea_aunque_cambie_monto_y_fecha(self):
        # Brief parte C: mismo `nro_operacion` -> duplicado, aunque no
        # coincida ni el hash del archivo ni monto/fecha (ej. se tipeó mal
        # un dato la primera vez).
        ruta_borrador1 = self._write_json(self._borrador_gasto())
        ruta_comprobante1 = self._write_json(
            {
                "hash_archivo": "hash-op-1", "monto_detectado": 1500.0,
                "fecha_detectada": "2026-04-10", "nro_operacion": "173192245876",
            },
            nombre="comprobante-op-1.json",
        )
        codigo, salida = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador1,
            "--comprobante", ruta_comprobante1, "--confirmado",
        ])
        self.assertEqual(codigo, 0)
        self.assertEqual(self._contar_gastos(), 1)

        ruta_borrador2 = self._write_json(
            self._borrador_gasto(monto=9999.0), nombre="borrador-op-2.json",
        )
        ruta_comprobante2 = self._write_json(
            {
                "hash_archivo": "hash-op-2", "monto_detectado": 9999.0,
                "fecha_detectada": "2026-09-01", "nro_operacion": "173192245876",
            },
            nombre="comprobante-op-2.json",
        )
        codigo, salida = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador2,
            "--comprobante", ruta_comprobante2, "--confirmado",
        ])
        self.assertNotEqual(codigo, 0)
        self.assertTrue(salida["duplicado"])
        self.assertEqual(salida["dedupe"]["coincidencia"], "operacion")
        self.assertEqual(self._contar_gastos(), 1)


class DedupeCliTests(_ApiServerTestCase):
    def test_dedupe_con_nro_operacion_proxy_directo(self):
        ruta_borrador = self._write_json({
            "monto": 1500.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Efectivo", "pagado_por": "JD",
        })
        ruta_comprobante = self._write_json(
            {"hash_archivo": "hash-dedupe-op", "nro_operacion": "173192245876"},
            nombre="comprobante-dedupe-op.json",
        )
        codigo, _ = self.run_cli([
            "guardar", "--tipo", "gasto", "--json", ruta_borrador,
            "--comprobante", ruta_comprobante, "--confirmado",
        ])
        self.assertEqual(codigo, 0)

        codigo, salida = self.run_cli(["dedupe", "--hash", "otro-hash", "--nro-operacion", "173192245876"])
        self.assertEqual(codigo, 0)
        self.assertTrue(salida["duplicado"])
        self.assertEqual(salida["coincidencia"], "operacion")

        codigo, salida = self.run_cli(["dedupe", "--hash", "otro-hash", "--nro-operacion", "000000000"])
        self.assertEqual(codigo, 0)
        self.assertFalse(salida["duplicado"])


# --- avisos-pendientes / marcar-avisos / borrador (cliente HTTP real) ------


class AvisosYBorradorTests(_ApiServerTestCase):
    def test_avisos_pendientes_y_marcar_enviados(self):
        borrador = {
            "monto": 150000.0, "fecha": "2026-04-10", "categoria": "Comida",
            "medio_pago": "Crédito", "pagado_por": "JD",
        }
        ruta = self._write_json(borrador)
        codigo, salida = self.run_cli(["guardar", "--tipo", "gasto", "--json", ruta, "--confirmado"])
        self.assertEqual(codigo, 0)
        self.assertEqual([a["umbral"] for a in salida["avisos_credito_nuevos"]], [100000, 150000])

        codigo, pendientes = self.run_cli(["avisos-pendientes"])
        self.assertEqual(codigo, 0)
        self.assertEqual({a["umbral"] for a in pendientes["avisos_credito"]}, {100000, 150000})

        ruta_items = self._write_json([{"mes": "2026-04", "umbral": 100000}], nombre="items.json")
        codigo, resultado = self.run_cli(["marcar-avisos", "--items", ruta_items])
        self.assertEqual(codigo, 0)
        self.assertEqual(resultado["actualizados"], [{"mes": "2026-04", "umbral": 100000}])

    def test_borrador_get_set_clear(self):
        codigo, salida = self.run_cli(["borrador", "get", "--chat", "chat-1", "--usuario", "JD"])
        self.assertEqual(codigo, 0)
        self.assertIsNone(salida["borrador"])

        datos_set = {
            "estado": "esperando_campo", "campo_pendiente": "monto",
            "payload_parcial": {"categoria": "Comida"},
        }
        ruta = self._write_json(datos_set)
        codigo, salida = self.run_cli(["borrador", "set", "--chat", "chat-1", "--usuario", "JD", "--json", ruta])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["estado"], "esperando_campo")
        self.assertEqual(salida["borrador"]["payload_parcial"], {"categoria": "Comida"})

        codigo, salida = self.run_cli(["borrador", "get", "--chat", "chat-1", "--usuario", "JD"])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida["borrador"]["campo_pendiente"], "monto")

        # Un usuario distinto del mismo chat tiene su propio borrador.
        codigo, salida = self.run_cli(["borrador", "get", "--chat", "chat-1", "--usuario", "Pinki"])
        self.assertEqual(codigo, 0)
        self.assertIsNone(salida["borrador"])

        codigo, salida = self.run_cli(["borrador", "clear", "--chat", "chat-1", "--usuario", "JD"])
        self.assertEqual(codigo, 0)
        self.assertTrue(salida["cleared"])

        codigo, salida = self.run_cli(["borrador", "get", "--chat", "chat-1", "--usuario", "JD"])
        self.assertEqual(codigo, 0)
        self.assertIsNone(salida["borrador"])

    def test_secreto_invalido_devuelve_error_claro_sin_filtrar_el_secreto_bueno(self):
        secreto_malo = str(Path(self.tempdir.name) / "secreto-malo.txt")
        Path(secreto_malo).write_text("otro-secreto-totalmente-distinto", encoding="utf-8")
        os.chmod(secreto_malo, 0o600)
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida):
            codigo = telegram_ingesta.main([
                "--api-base", self.base_url, "--secret-file", secreto_malo, "avisos-pendientes",
            ])
        self.assertNotEqual(codigo, 0)
        contenido = buffer_salida.getvalue()
        salida = json.loads(contenido)
        self.assertIn("error", salida)
        self.assertNotIn(self.secret, contenido)

    def test_sin_secret_file_ni_variable_de_entorno_da_error_explicito(self):
        buffer_salida = io.StringIO()
        previo = os.environ.pop("LIFE_API_SECRET_FILE", None)
        try:
            with contextlib.redirect_stdout(buffer_salida):
                codigo = telegram_ingesta.main(["--api-base", self.base_url, "avisos-pendientes"])
        finally:
            if previo is not None:
                os.environ["LIFE_API_SECRET_FILE"] = previo
        self.assertNotEqual(codigo, 0)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("secreto", salida["error"])

    def test_secret_file_symlink_rechazado(self):
        enlace = Path(self.tempdir.name) / "secret-symlink.txt"
        enlace.symlink_to(self.secret_path)
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida):
            codigo = telegram_ingesta.main([
                "--api-base", self.base_url, "--secret-file", str(enlace), "avisos-pendientes",
            ])
        self.assertNotEqual(codigo, 0)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("symlink", salida["error"])

    def test_secret_file_con_permisos_de_grupo_u_otros_rechazado(self):
        secreto_abierto = Path(self.tempdir.name) / "secreto-abierto.txt"
        secreto_abierto.write_text(self.secret, encoding="utf-8")
        os.chmod(secreto_abierto, 0o644)
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida):
            codigo = telegram_ingesta.main([
                "--api-base", self.base_url, "--secret-file", str(secreto_abierto), "avisos-pendientes",
            ])
        self.assertNotEqual(codigo, 0)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("permisos", salida["error"])


class ClienteSinRedireccionesTests(unittest.TestCase):
    """El opener del CLI nunca sigue redirecciones -- el secreto interno no
    debe reenviarse a otro origen (brief: punto 5)."""

    class _RedirectHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://otro-host.invalido/robo-secreto")
            self.end_headers()

        def log_message(self, *args):
            pass

    def setUp(self):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), self._RedirectHandler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.tempdir = tempfile.TemporaryDirectory()
        self.secret_path = str(Path(self.tempdir.name) / "secret.txt")
        Path(self.secret_path).write_text("secreto", encoding="utf-8")
        os.chmod(self.secret_path, 0o600)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tempdir.cleanup()

    def test_no_sigue_la_redireccion(self):
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida):
            codigo = telegram_ingesta.main([
                "--api-base", self.base_url, "--secret-file", self.secret_path, "avisos-pendientes",
            ])
        self.assertNotEqual(codigo, 0)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("redirec", salida["error"])


# --- --api-base (solo http/https, http solo contra loopback) ---------------


class ApiBaseTests(unittest.TestCase):
    def test_rechaza_esquema_no_http(self):
        with self.assertRaises(telegram_ingesta.CliError):
            telegram_ingesta._validar_api_base("ftp://127.0.0.1")

    def test_rechaza_http_contra_host_no_loopback(self):
        with self.assertRaises(telegram_ingesta.CliError):
            telegram_ingesta._validar_api_base("http://ejemplo-remoto.invalido")

    def test_acepta_http_contra_loopback(self):
        self.assertEqual(
            telegram_ingesta._validar_api_base("http://127.0.0.1:8765"), "http://127.0.0.1:8765",
        )

    def test_acepta_https_contra_host_no_loopback(self):
        self.assertEqual(
            telegram_ingesta._validar_api_base("https://ejemplo-remoto.invalido"),
            "https://ejemplo-remoto.invalido",
        )


# --- argumentos de línea de comandos ----------------------------------------


class CliArgumentosTests(unittest.TestCase):
    def test_no_existe_opcion_para_pasar_el_secreto_en_claro(self):
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = telegram_ingesta.main(["--secret", "x", "avisos-pendientes"])
        self.assertEqual(codigo, 2)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("error", salida)

    def test_subcomando_desconocido_da_salida_json_con_exit_2(self):
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = telegram_ingesta.main(["no-existe"])
        self.assertEqual(codigo, 2)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("error", salida)

    def test_falta_argumento_requerido_da_salida_json_con_exit_2(self):
        buffer_salida = io.StringIO()
        with contextlib.redirect_stdout(buffer_salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = telegram_ingesta.main(["normalizar", "--tipo", "gasto"])
        self.assertEqual(codigo, 2)
        salida = json.loads(buffer_salida.getvalue())
        self.assertIn("error", salida)


# --- main(): red de contención contra excepciones no previstas -------------


class MainErrorHandlingTests(unittest.TestCase):
    def test_excepcion_no_prevista_da_error_interno_sin_traceback_ni_datos(self):
        def _boom(args):
            raise RuntimeError("algo no previsto, con datos sensibles adentro")

        buffer_salida = io.StringIO()
        with unittest.mock.patch.object(telegram_ingesta, "cmd_hash", _boom):
            with contextlib.redirect_stdout(buffer_salida):
                codigo = telegram_ingesta.main(["hash", "no-importa.txt"])
        self.assertEqual(codigo, 1)
        salida = json.loads(buffer_salida.getvalue())
        self.assertEqual(salida, {"error": "error interno: RuntimeError"})


if __name__ == "__main__":
    unittest.main()
