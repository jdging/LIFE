"""Tests de `lab/facturas_fijas.py` (mejora #4 de Juan, 2026-11-05).

Los textos de fixture son los que devuelve la extracción real de las 3
facturas que Juan mandó por Telegram (gas = Litoral Gas S.A., EPE = Empresa
Provincial de la Energía de Santa Fe, internet = Telecom Argentina),
recortados a las líneas que importan para el parseo determinista.
"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import datetime as _dt
from pathlib import Path
from wsgiref.simple_server import make_server

import pytest

import api
import db
import facturas_fijas
import telegram_ingesta

TEXTO_GAS = """
Litoral Gas S.A.
Av.Carballo 183 P2 (2000) Rosario
CLAVE DE DEBITO AUTOMATICO: **01268131023 TOTAL A PAGAR hasta el 10/11/2026 158.277,32** TARIFA APLICADA
"""

TEXTO_EPE = """
Empresa Provincial de la Energía de Santa Fe
## AV MORRISON 7728 Piso UNID 01 Cuota 1 24/11/2026 $115.997,55
R 000 19 3245 11221 01 5/26 **Cuota 2 28/12/2026 $115.997,54** Tarifa
"""

TEXTO_INTERNET = """
TELECOM ARGENTINA S.A. ORIGINAL
Tu saldo total es de $ 22.965,01 y vence el día 11/11/2026
"""

TEXTO_DESCONOCIDO = "Factura de un proveedor que no reconocemos todavía."


class _FakeDate(_dt.date):
    """Congela `date.today()` para que el test no dependa del reloj real
    (la cuota EPE elegida depende del mes vigente)."""
    _hoy = _dt.date(2026, 11, 5)

    @classmethod
    def today(cls):
        return cls._hoy


@pytest.fixture
def congelar_hoy(monkeypatch):
    def _congelar(hoy_iso):
        _FakeDate._hoy = _dt.date.fromisoformat(hoy_iso)
        monkeypatch.setattr(facturas_fijas, "date", _FakeDate)
    return _congelar


class TestDeteccionYParseo:
    def test_detecta_gas_y_extrae_monto_y_vencimiento(self):
        resultado = facturas_fijas.extraer_factura(TEXTO_GAS)
        assert resultado == {"proveedor": "gas", "monto": 158277.32,
            "vencimiento": "2026-11-10", "detalle": None, "formato_desconocido": False}

    def test_epe_usa_la_cuota_del_mes_vigente_si_hay_una_en_el_mes_actual(self, congelar_hoy):
        congelar_hoy("2026-11-05")  # cuota 1 vence en noviembre: mes vigente
        resultado = facturas_fijas.extraer_factura(TEXTO_EPE)
        assert resultado["proveedor"] == "epe"
        assert resultado["monto"] == 115997.55
        assert resultado["vencimiento"] == "2026-11-24"
        assert resultado["detalle"] == {"monto": 115997.54, "vencimiento": "2026-12-28"}
        assert resultado["formato_desconocido"] is False

    def test_epe_usa_la_otra_cuota_cuando_el_mes_vigente_es_el_de_esa_cuota(self, congelar_hoy):
        congelar_hoy("2026-12-10")  # cuota 2 vence en diciembre: mes vigente
        resultado = facturas_fijas.extraer_factura(TEXTO_EPE)
        assert resultado["monto"] == 115997.54
        assert resultado["vencimiento"] == "2026-12-28"
        assert resultado["detalle"] == {"monto": 115997.55, "vencimiento": "2026-11-24"}

    def test_epe_sin_coincidencia_de_mes_usa_la_proxima_por_vencer(self, congelar_hoy):
        congelar_hoy("2026-09-01")  # ninguna cuota vence en septiembre: usa la próxima (cuota 1)
        resultado = facturas_fijas.extraer_factura(TEXTO_EPE)
        assert resultado["monto"] == 115997.55
        assert resultado["vencimiento"] == "2026-11-24"

    def test_epe_con_ambas_cuotas_vencidas_usa_la_mas_reciente(self, congelar_hoy):
        congelar_hoy("2027-02-01")  # ambas cuotas ya vencieron: usa la más reciente (cuota 2)
        resultado = facturas_fijas.extraer_factura(TEXTO_EPE)
        assert resultado["monto"] == 115997.54
        assert resultado["vencimiento"] == "2026-12-28"

    def test_detecta_internet_telecom(self):
        resultado = facturas_fijas.extraer_factura(TEXTO_INTERNET)
        assert resultado == {"proveedor": "internet", "monto": 22965.01,
            "vencimiento": "2026-11-11", "detalle": None, "formato_desconocido": False}

    def test_formato_no_reconocido_no_inventa_nada(self):
        resultado = facturas_fijas.extraer_factura(TEXTO_DESCONOCIDO)
        assert resultado["formato_desconocido"] is True
        assert resultado["monto"] is None

    def test_proveedor_explicito_fuerza_ese_parser_aunque_la_deteccion_falle(self):
        texto = "TOTAL A PAGAR hasta el 10/11/2026 158.277,32"
        assert facturas_fijas.detectar_proveedor(texto) is None
        resultado = facturas_fijas.extraer_factura(texto, proveedor="gas")
        assert resultado["proveedor"] == "gas"
        assert resultado["monto"] == 158277.32

    def test_parse_monto_es_rechaza_formato_no_esperado(self):
        with pytest.raises(telegram_ingesta.CliError):
            facturas_fijas._parse_monto_es("45k")


class TestCliExtraer:
    def test_cmd_extraer_devuelve_exit_0_si_reconoce_el_formato(self, tmp_path, capsys):
        archivo = tmp_path / "gas.txt"
        archivo.write_text(TEXTO_GAS, encoding="utf-8")
        codigo = facturas_fijas.main(["extraer", "--texto", str(archivo)])
        assert codigo == 0
        salida = json.loads(capsys.readouterr().out)
        assert salida["monto"] == 158277.32

    def test_cmd_extraer_devuelve_exit_1_si_no_reconoce_el_formato(self, tmp_path, capsys):
        archivo = tmp_path / "rara.txt"
        archivo.write_text(TEXTO_DESCONOCIDO, encoding="utf-8")
        codigo = facturas_fijas.main(["extraer", "--texto", str(archivo)])
        assert codigo == 1
        salida = json.loads(capsys.readouterr().out)
        assert salida["formato_desconocido"] is True


class ActualizarContraApiRealTests(unittest.TestCase):
    """Cliente HTTP contra la app WSGI real (mismo patrón que
    `test_telegram_ingesta.py::_ApiServerTestCase`), nunca contra datos
    reales ni una base persistente."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "api.sqlite")
        self.secret = "test-secret-facturas-fijas"
        self.secret_path = str(Path(self.tempdir.name) / "secret.txt")
        Path(self.secret_path).write_text(self.secret, encoding="utf-8")
        os.chmod(self.secret_path, 0o600)

        self.app = api.create_app(self.db_path, self.secret)
        self.server = make_server("127.0.0.1", 0, self.app)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.app.close()
        self.tempdir.cleanup()

    def run_cli(self, argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = facturas_fijas.main([
                "--api-base", self.base_url, "--secret-file", self.secret_path, *argv,
            ])
        contenido = salida.getvalue().strip()
        return codigo, (json.loads(contenido) if contenido else None)

    def test_actualizar_sin_confirmado_no_llama_a_la_api(self):
        codigo, salida = self.run_cli(["actualizar", "--fixed-id", "1", "--monto", "158277.32"])
        self.assertNotEqual(codigo, 0)
        self.assertIn("error", salida)

    def test_listar_fijos_vacio_al_arrancar(self):
        codigo, salida = self.run_cli(["listar-fijos"])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida, [])

    def test_actualizar_confirmado_crea_una_version_nueva_sin_perder_la_anterior(self):
        client = telegram_ingesta.ApiClient(self.base_url, self.secret)
        creado = client._request("POST", "/api/fixed", json_body={
            "nombre": "Gas", "monto_estimado": 150000.0, "periodicidad": "mensual",
            "responsable": "Común", "tipo_proporcion": "dinamica",
            "categoria": "Hogar", "subcategoria": "Servicios",
            "medio_pago": "Crédito", "vigente_desde": "2026-10-10",
        })
        fijo_id = creado["fixed"]["id"]
        grupo_id = creado["fixed"].get("fijo_grupo_id") or fijo_id

        codigo, salida = self.run_cli([
            "actualizar", "--fixed-id", str(fijo_id), "--monto", "158277.32",
            "--vigente-desde", "2026-11-05", "--confirmado",
        ])
        self.assertEqual(codigo, 0, salida)

        # PATCH crea una VERSIÓN NUEVA (id distinto, mismo fijo_grupo_id) en
        # vez de mutar la fila -- igual que el resto de /api/fixed. Se busca
        # la versión vigente por grupo, no por el id viejo. (vigente_desde
        # tiene que ser hoy o antes para que GET /api/fixed ya la muestre
        # como la versión activa en vez de la anterior.)
        _, fijos = self.run_cli(["listar-fijos"])
        vigente = next(f for f in fijos if (f.get("fijo_grupo_id") or f["id"]) == grupo_id)
        self.assertEqual(vigente["monto_estimado"], 158277.32)
        self.assertEqual(vigente["vigente_desde"], "2026-11-05")

        historial = client._request("GET", f"/api/fixed/{vigente['id']}/historial")
        montos = {v["monto_estimado"] for v in historial["historial"]}
        self.assertIn(150000.0, montos, "la versión anterior se conserva en el historial")
        self.assertIn(158277.32, montos)
