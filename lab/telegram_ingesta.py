"""CLI determinista de ingesta por Telegram (brief S2/S3, T3 de CTO-DISENO.md).

Cliente HTTP puro-stdlib (`urllib`) de la API candidata (`lab/api.py`). Nunca
importa `db.py`/`api.py` ni abre la base SQLite directo -- toda lectura y
escritura pasa por `/api/*` con el header `X-Internal-Proxy-Secret` (ver
justificación en CTO-DISENO.md §1(a): un segundo proceso escribiendo la base
directo compite por locks con la API, que ya es el único escritor).

Texto de comprobantes como DATO, nunca como instrucción: todo lo que llega en
campos de texto (comercio, descripción, texto extraído) se trata con regex y
comparaciones de string -- este módulo no ejecuta nada que venga de un
comprobante.

Subcomandos (ver `lab/README-telegram.md` para el contrato completo):
    extraer-pdf, hash, extraer-campos, normalizar, faltantes, pregunta,
    dedupe, guardar, avisos-pendientes, marcar-avisos, mensaje-aviso,
    borrador.

Cada subcomando imprime exactamente un objeto JSON por stdout y termina con
exit code 0. Cualquier fallo (de validación, de red, o de la API) imprime
`{"error": "..."}` (más contexto estructurado cuando aplica) y termina con
exit code != 0 -- nunca levanta una traza sin capturar hacia el usuario.

El secreto interno nunca se acepta como valor de argumento ni se imprime: se
lee de `--secret-file`, o de la variable de entorno `LIFE_API_SECRET_FILE` si
`--secret-file` no se especifica.
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import stat
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

DEFAULT_API_BASE = "http://127.0.0.1:8765"
DEFAULT_USUARIOS_FILE = str(Path(__file__).resolve().with_name("telegram_usuarios.json"))

# Mismo límite que `api.MAX_MONEY`/`api._valid_money` (lab/api.py) --
# duplicado a propósito, igual que el resto de las constantes de dominio de
# este módulo (ver comentario de MEDIOS_PAGO_VALIDOS más abajo): el CLI
# nunca importa `api.py`.
MONTO_MAXIMO = Decimal("1000000000000")

# Hosts considerados loopback para la regla "http solo contra loopback,
# https para cualquier otro host" de `--api-base`.
_HOSTS_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Mismos valores que las convenciones de dominio documentadas en
# `docs/CONTEXTO.md` / `lab/validaciones.py` (duplicados acá a propósito: el
# CLI es un cliente HTTP sin dependencia de los módulos del servidor, ver
# CTO-DISENO.md §1(a) -- "sin excepciones, ni para lectura ni para
# escritura" se refiere al transporte, pero mantener esta capa desacoplada
# de `db.py`/`validaciones.py` evita que un cambio interno del servidor
# rompa el CLI en silencio).
MEDIOS_PAGO_VALIDOS = ("Crédito", "Débito", "Efectivo", "Transferencia")
PAGADO_POR_VALIDOS = ("Común", "JD", "Pinki")
PERSONA_INGRESO_VALIDOS = ("JD", "Pinki")
TIPO_PROPORCION_VALIDOS = ("dinamico", "custom")

CAMPOS_OBLIGATORIOS_GASTO = ("monto", "fecha", "categoria", "medio_pago", "pagado_por")
CAMPOS_OBLIGATORIOS_INGRESO = ("monto", "fecha", "categoria", "persona")

API_TIPOS = {"gasto": "Gasto", "ingreso": "Ingreso"}

# Mismo patrón que `api._TELEGRAM_ID_RE`: dígitos con '-' inicial opcional
# (los chat_id de grupo de Telegram son negativos).
_TELEGRAM_ID_RE = re.compile(r"^-?\d{1,32}$")

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Alias simples de categoría/subcategoría (brief: "matching tolerante: sin
# acentos, sin mayúsculas, alias simples"). Lista deliberadamente chica y
# extensible -- el matching principal es por slug sin acento/mayúscula
# (`_slug`), esto solo cubre sinónimos que no son la misma palabra.
ALIASES_CATEGORIA = {}
ALIASES_SUBCATEGORIA = {
    "super": "supermercado",
}

PREGUNTAS_CAMPO_FIJAS = {
    "monto": "¿Cuánto fue?",
    "fecha": "¿Qué día fue?",
    "medio_pago": "¿Cómo pagaste? (Efectivo, Débito, Crédito o Transferencia)",
    "pagado_por": "¿Quién pagó? (Común, JD o Pinki)",
    "persona": "¿Para quién es este ingreso? (JD o Pinki)",
    "proporcion_jd": "¿Qué % pone JD?",
}


class CliError(Exception):
    """Error determinista del CLI (validación, archivo, usuario desconocido).

    `payload`, si viene, se mezcla en el JSON de error impreso por `main()`
    -- para que un fallo "esperable" (ej. dedupe bloqueando un guardado)
    devuelva datos estructurados, no solo un mensaje de texto.
    """

    def __init__(self, message, payload=None):
        super().__init__(message)
        self.payload = payload


class ApiError(Exception):
    """Error de red o de respuesta de la API (status >= 400, o sin conexión)."""

    def __init__(self, status, message, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class _SinRedireccionHandler(urllib.request.HTTPRedirectHandler):
    """Nunca sigue redirecciones HTTP: el header `X-Internal-Proxy-Secret` no
    debe reenviarse a un origen distinto del configurado en `--api-base`."""

    def redirect_request(self, req, fh, code, msg, headers, newurl):
        return None


def _validar_api_base(url):
    """`--api-base` solo acepta `http`/`https`; `http` solo contra loopback
    (127.0.0.1/localhost/::1) -- cualquier otro host exige `https` para no
    mandar el secreto interno en claro por la red."""
    partes = urllib.parse.urlparse(url)
    if partes.scheme not in ("http", "https"):
        raise CliError(f"--api-base inválido: {url!r} (debe empezar con http:// o https://).")
    host = (partes.hostname or "").lower()
    if partes.scheme == "http" and host not in _HOSTS_LOOPBACK:
        raise CliError(
            f"--api-base inválido: {url!r} (http solo se permite contra loopback; "
            "usar https:// para un host remoto)."
        )
    return url


class ApiClient:
    """Cliente HTTP puro-stdlib de la API candidata (ver `lab/api.py`)."""

    def __init__(self, base_url, secret, timeout=10):
        self.base_url = _validar_api_base(base_url).rstrip("/")
        self.secret = secret
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_SinRedireccionHandler())

    def _request(self, method, path, *, query=None, json_body=None):
        url = self.base_url + path
        if query:
            limpio = {k: v for k, v in query.items() if v is not None}
            qs = urllib.parse.urlencode(limpio)
            if qs:
                url = f"{url}?{qs}"

        data = None
        headers = {"X-Internal-Proxy-Secret": self.secret}
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            raise ApiError(0, f"no se pudo conectar con la API en {self.base_url}: {exc.reason}")

        if 300 <= status < 400:
            raise ApiError(status, "la API devolvió una redirección; el cliente no sigue redirecciones.")

        parsed = None
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise ApiError(status, "la API devolvió una respuesta no-JSON.")

        if status >= 400:
            mensaje = f"error HTTP {status}"
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), str):
                mensaje = parsed["error"]
            raise ApiError(status, mensaje, parsed)
        return parsed if parsed is not None else {}

    def get_categories(self, tipo):
        return self._request("GET", "/api/categories", query={"tipo": tipo})["categories"]

    def create_expense_telegram(self, payload):
        return self._request("POST", "/api/expenses/telegram", json_body=payload)

    def create_income_telegram(self, payload):
        return self._request("POST", "/api/income/telegram", json_body=payload)

    def dedupe(self, hash_archivo, *, monto=None, fecha=None, comercio=None, nro_operacion=None):
        query = {"hash": hash_archivo}
        if monto is not None:
            query["monto"] = monto
        if fecha is not None:
            query["fecha"] = fecha
        if comercio is not None:
            query["comercio"] = comercio
        if nro_operacion is not None:
            query["nro_operacion"] = nro_operacion
        return self._request("GET", "/api/comprobantes/dedupe", query=query)

    def avisos_pendientes(self):
        return self._request("GET", "/api/avisos-credito/pendientes")

    def marcar_avisos(self, items):
        return self._request("POST", "/api/avisos-credito/marcar-enviados", json_body={"items": items})

    def borrador_get(self, chat, usuario=None):
        return self._request("GET", "/api/telegram/borrador", query={"chat": chat, "usuario": usuario})

    def borrador_set(self, chat, usuario, datos):
        return self._request(
            "PUT", "/api/telegram/borrador", query={"chat": chat, "usuario": usuario}, json_body=datos,
        )

    def borrador_clear(self, chat, usuario=None):
        return self._request("DELETE", "/api/telegram/borrador", query={"chat": chat, "usuario": usuario})


# --- Parseo determinista de montos AR ---------------------------------------


_GRUPOS_MILES_RE = re.compile(r"\d{1,3}(\.\d{3})+")


def _validar_agrupacion_miles(entero):
    """Si `entero` tiene puntos de separador de miles, exige que agrupen de
    a 3 dígitos ('1.500.000' OK; '1.2.3' inválido). Sin puntos, no hay nada
    que validar (un entero sin separador, ej. '1500', es válido tal cual)."""
    if "." not in entero:
        return
    if not _GRUPOS_MILES_RE.fullmatch(entero):
        raise ValueError(f"agrupación de miles inválida: {entero!r}.")


def _parse_numero_ar(token):
    """Parsea un número en formato AR sin sufijos: '.' separa miles (de a 3
    dígitos), ',' separa decimales, máximo 2 (ej. '45.000,50' -> 45000.50;
    '45.000' -> 45000.0; '1.2.3' o '45.000,123' son inválidos)."""
    token = token.strip()
    if not token:
        raise ValueError("número vacío.")
    if "," in token:
        entero, _, decimal = token.rpartition(",")
        _validar_agrupacion_miles(entero)
        entero_limpio = entero.replace(".", "")
        if not re.fullmatch(r"\d+", entero_limpio) or not re.fullmatch(r"\d{1,2}", decimal):
            raise ValueError(f"monto con formato inválido: {token!r}.")
        return float(f"{entero_limpio}.{decimal}")
    _validar_agrupacion_miles(token)
    sin_puntos = token.replace(".", "")
    if not re.fullmatch(r"\d+", sin_puntos):
        raise ValueError(f"monto con formato inválido: {token!r}.")
    return float(sin_puntos)


def _validar_monto_final(monto):
    """Último chequeo, igual para montos parseados de texto o pasados ya
    numéricos: finito, > 0, y dentro del mismo límite que acepta la API
    (`api.MAX_MONEY`/`api._valid_money`, ver `MONTO_MAXIMO` más arriba)."""
    if not math.isfinite(monto):
        raise ValueError(f"monto inválido: {monto!r} (no es un número finito).")
    if monto <= 0:
        raise ValueError(f"monto inválido: {monto!r} (debe ser mayor a 0).")
    cantidad = Decimal(str(monto))
    if cantidad > MONTO_MAXIMO:
        raise ValueError(f"monto inválido: {monto!r} (supera el máximo permitido).")
    if cantidad * 100 != (cantidad * 100).to_integral_value():
        raise ValueError(f"monto inválido: {monto!r} (máximo 2 decimales).")
    return monto


def parse_monto_ar(valor):
    """Parseo determinista de montos en formatos AR habituales de Telegram:
    '45.000', '45 mil', '$45.000,50', '45k'. Acepta también `int`/`float`
    ya numéricos (passthrough, con la misma validación final). Nunca
    adivina: si el formato no matchea ninguno de los patrones soportados,
    levanta `ValueError`.
    """
    if isinstance(valor, bool):
        raise ValueError(f"monto inválido: {valor!r}.")
    if isinstance(valor, (int, float)):
        # Un `int` arbitrariamente grande (ej. 10**400) se compara como
        # `Decimal` contra el máximo ANTES de convertir a `float` -- esa
        # conversión levanta `OverflowError` (no `ValueError`) si el entero
        # no entra en un double, y acá eso debe seguir siendo un rechazo
        # limpio del monto, no una excepción sin capturar.
        if isinstance(valor, int) and Decimal(valor) > MONTO_MAXIMO:
            raise ValueError(f"monto inválido: {valor!r} (supera el máximo permitido).")
        try:
            return _validar_monto_final(float(valor))
        except OverflowError:
            raise ValueError(f"monto inválido: {valor!r} (supera el máximo permitido).") from None
    if not isinstance(valor, str):
        raise ValueError(f"monto inválido: {valor!r}.")

    texto = valor.strip().lower().replace("$", "").strip()
    texto = re.sub(r"\s+", " ", texto)
    if not texto:
        raise ValueError("monto vacío.")

    mil_match = re.fullmatch(r"([\d.,]+)\s*mil", texto)
    if mil_match:
        return _validar_monto_final(_parse_numero_ar(mil_match.group(1)) * 1000)

    k_match = re.fullmatch(r"([\d.,]+)\s*k", texto)
    if k_match:
        return _validar_monto_final(_parse_numero_ar(k_match.group(1)) * 1000)

    return _validar_monto_final(_parse_numero_ar(texto.replace(" ", "")))


def formatear_monto_ar(monto):
    """Formatea un monto como '$12.350' o '$212.350,50' (separador de miles
    '.', decimales con ',', solo si no son exactamente cero)."""
    negativo = monto < 0
    monto_abs = abs(float(monto))
    entero = int(monto_abs)
    frac = round(monto_abs - entero, 2)
    entero_str = f"{entero:,}".replace(",", ".")
    signo = "-" if negativo else ""
    if frac == 0:
        return f"{signo}${entero_str}"
    frac_str = f"{frac:.2f}".split(".", 1)[1]
    return f"{signo}${entero_str},{frac_str}"


def _formatear_fecha_corta(fecha_iso):
    if not fecha_iso:
        return "?"
    anio, mes, dia = fecha_iso[:10].split("-")
    return f"{dia}/{mes}"


def _nombre_mes_es(mes_iso):
    _, mes = mes_iso.split("-")
    return MESES_ES[int(mes) - 1]


# --- Matching tolerante de categoría/subcategoría ----------------------------


def _slug(texto):
    """Normaliza para matching tolerante: sin acentos, sin mayúsculas, sin
    espacios de borde. Base de la validación de categoría/subcategoría/
    subcategoría contra los catálogos reales de la API."""
    if texto is None:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.strip().lower()


def _resolver_categoria(categorias, categoria_in, subcategoria_in):
    """Busca `categoria_in`/`subcategoria_in` en la lista de `GET
    /api/categories` (`[{"categoria": str, "subcategorias": [str, ...]}]`),
    con matching tolerante. Devuelve `{"categoria": str, "subcategoria":
    str|None}` con los nombres REALES del catálogo, o `None` si no matchea.
    """
    slug_cat = ALIASES_CATEGORIA.get(_slug(categoria_in), _slug(categoria_in))
    encontrada = next((c for c in categorias if _slug(c["categoria"]) == slug_cat), None)
    if encontrada is None:
        return None

    resultado = {"categoria": encontrada["categoria"], "subcategoria": None}
    if subcategoria_in:
        slug_sub = ALIASES_SUBCATEGORIA.get(_slug(subcategoria_in), _slug(subcategoria_in))
        sub = next((s for s in encontrada["subcategorias"] if _slug(s) == slug_sub), None)
        if sub is None:
            return None
        resultado["subcategoria"] = sub
    return resultado


# --- extraer-campos: parseo determinista de comprobantes (solo regex) ------
#
# "La onda del comprobante es que se lea todo desde ahí directamente" (Juan,
# 2026-10-25): esta sección NUNCA usa un LLM -- el texto de un comprobante es
# un DATO (ver encabezado del módulo), parseado con regex exactas contra
# formatos conocidos. Un formato no reconocido devuelve campos vacíos y
# `formato_desconocido=True`, nunca un valor inventado.


CAMPOS_EXTRAER_CAMPOS = (
    "monto", "fecha", "medio_pago", "comercio", "descripcion",
    "nro_operacion", "titular_origen", "emisor",
)

_CAMPOS_VACIOS_COMPROBANTE = {campo: None for campo in CAMPOS_EXTRAER_CAMPOS}

_DIAS_SEMANA_ES_RE = "lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo"

_FECHA_COMPROBANTE_RE = re.compile(
    rf"^(?:{_DIAS_SEMANA_ES_RE}),\s*(\d{{1,2}})\s+de\s+([A-Za-zñÑáéíóúÁÉÍÓÚ]+)\s+de\s+(\d{{4}})"
    rf"\s+a las\s+\d{{1,2}}:\d{{2}}\s*hs\.?$",
    re.IGNORECASE,
)
_MONTO_COMPROBANTE_RE = re.compile(r"^\$\s*([\d.,]+)$")
_MOTIVO_COMPROBANTE_RE = re.compile(r"^Motivo:\s*(.+)$", re.IGNORECASE)
_CUIT_COMPROBANTE_RE = re.compile(r"^CUIT/CUIL:\s*[\d-]+$")
_CVU_COMPROBANTE_RE = re.compile(r"^CVU:\s*\d+$")
_NRO_OPERACION_HEADER_RE = re.compile(
    r"^N[uú]mero de operaci[oó]n de Mercado Pago$", re.IGNORECASE,
)
_NRO_OPERACION_VALOR_RE = re.compile(r"^\d+$")

# "Varios" es el motivo default que pone Mercado Pago cuando el que transfiere
# no escribe nada -- no aporta información, así que no se arma `descripcion`
# con él (brief: "descripción ... si no es genérico").
_MOTIVOS_GENERICOS_COMPROBANTE = {"varios"}


def _mes_es_a_numero(nombre_mes):
    slug_mes = _slug(nombre_mes)
    if slug_mes not in MESES_ES:
        return None
    return MESES_ES.index(slug_mes) + 1


def _extraer_mercadopago_transferencia(lineas):
    """Parser del único formato soportado hoy: comprobante de transferencia
    de Mercado Pago (brief, formato exacto extraído de un PDF real con
    nombres/CUIT/CVU reemplazados). Devuelve el dict de campos, o `None` si
    `lineas` no matchea esta forma exacta -- nunca completa a medias."""
    if not lineas or lineas[0] != "Comprobante de transferencia":
        return None
    if len(lineas) < 2:
        return None

    indice = 1
    m_fecha = _FECHA_COMPROBANTE_RE.match(lineas[indice])
    if not m_fecha:
        return None
    dia, nombre_mes, anio = m_fecha.groups()
    mes_numero = _mes_es_a_numero(nombre_mes)
    if mes_numero is None:
        return None
    fecha_iso = f"{int(anio):04d}-{mes_numero:02d}-{int(dia):02d}"
    try:
        date.fromisoformat(fecha_iso)
    except ValueError:
        return None
    indice += 1

    if indice >= len(lineas):
        return None
    m_monto = _MONTO_COMPROBANTE_RE.match(lineas[indice])
    if not m_monto:
        return None
    try:
        monto = parse_monto_ar(m_monto.group(1))
    except ValueError:
        return None
    indice += 1

    descripcion = None
    if indice < len(lineas):
        m_motivo = _MOTIVO_COMPROBANTE_RE.match(lineas[indice])
        if m_motivo:
            motivo = m_motivo.group(1).strip()
            if _slug(motivo) not in _MOTIVOS_GENERICOS_COMPROBANTE:
                descripcion = f"Motivo: {motivo}"
            indice += 1

    def _siguiente():
        nonlocal indice
        if indice >= len(lineas):
            raise ValueError("comprobante incompleto")
        valor = lineas[indice]
        indice += 1
        return valor

    try:
        if _siguiente() != "De":
            return None
        titular_origen = _siguiente()
        if not _CUIT_COMPROBANTE_RE.match(_siguiente()):
            return None
        emisor = _siguiente()
        if emisor != "Mercado Pago":
            return None
        if not _CVU_COMPROBANTE_RE.match(_siguiente()):
            return None

        if _siguiente() != "Para":
            return None
        comercio = _siguiente()
        if not _CUIT_COMPROBANTE_RE.match(_siguiente()):
            return None
        if _siguiente() != "Mercado Pago":
            return None
        if not _CVU_COMPROBANTE_RE.match(_siguiente()):
            return None

        if not _NRO_OPERACION_HEADER_RE.match(_siguiente()):
            return None
        nro_operacion = _siguiente()
    except ValueError:
        return None
    if indice != len(lineas) or not _NRO_OPERACION_VALOR_RE.match(nro_operacion):
        return None

    return {
        "monto": monto, "fecha": fecha_iso, "medio_pago": "Transferencia",
        "comercio": comercio, "descripcion": descripcion, "nro_operacion": nro_operacion,
        "titular_origen": titular_origen, "emisor": emisor,
    }


_PARSERS_COMPROBANTE = (_extraer_mercadopago_transferencia,)


def extraer_campos_comprobante(texto):
    """Parsea el texto de un comprobante (ya extraído por `extraer-pdf` o
    tipeado) con los parsers regex conocidos (hoy solo transferencias de
    Mercado Pago). Devuelve siempre las mismas claves (`CAMPOS_EXTRAER_
    CAMPOS` + `formato_desconocido`); si ningún parser reconoce el formato,
    todos los campos quedan en `None` y `formato_desconocido=True` -- nunca
    se inventa un valor a partir de un texto que no matchea.
    """
    if not isinstance(texto, str):
        raise CliError("el texto del comprobante debe ser una cadena.")
    lineas = [linea.strip() for linea in texto.strip().splitlines() if linea.strip()]
    for parser in _PARSERS_COMPROBANTE:
        resultado = parser(lineas)
        if resultado is not None:
            salida = dict(_CAMPOS_VACIOS_COMPROBANTE)
            salida.update(resultado)
            salida["formato_desconocido"] = False
            return salida
    salida = dict(_CAMPOS_VACIOS_COMPROBANTE)
    salida["formato_desconocido"] = True
    return salida


# --- normalizar ---------------------------------------------------------


def _normalizar_telegram_ids(telegram, borrador):
    for campo_salida, campo_entrada in (
        ("chat_id", "chat_id"), ("telegram_user_id", "user_id"), ("telegram_message_id", "message_id"),
    ):
        valor = telegram.get(campo_entrada)
        if valor is None:
            continue
        valor_str = str(valor)
        if not _TELEGRAM_ID_RE.match(valor_str):
            raise CliError(f"telegram.{campo_entrada} inválido: {valor!r} (debe ser dígitos, '-' inicial opcional).")
        borrador[campo_salida] = valor_str


def cargar_usuarios(ruta):
    try:
        contenido = Path(ruta).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"no se pudo leer el archivo de usuarios ({ruta}): {exc}")
    try:
        datos = json.loads(contenido)
    except ValueError as exc:
        raise CliError(f"telegram_usuarios.json inválido: {exc}")
    if not isinstance(datos, dict):
        raise CliError("telegram_usuarios.json debe ser un objeto {user_id: {persona, nombre}}.")
    return datos


def resolver_usuario(usuarios, user_id):
    """Resuelve `user_id` contra el mapeo cargado. Un usuario desconocido es
    siempre un error explícito -- nunca se infiere una persona por default."""
    info = usuarios.get(str(user_id))
    if info is None:
        raise CliError(f"usuario de Telegram desconocido: {user_id!r} (agregalo a telegram_usuarios.json).")
    return info


def _sugerir_pagado_por_por_titular(titular_origen, usuarios):
    """Busca `titular_origen` (nombre tal como lo extrajo `extraer-campos` de
    un comprobante) contra `telegram_usuarios.json["titulares"]`, con el mismo
    matching tolerante (`_slug`) que categorías. Devuelve
    `"JD"`/`"Pinki"` si matchea, o `None` si no hay mapeo o no coincide --
    nunca inventa una persona que no esté en el mapeo explícito.
    """
    titulares = usuarios.get("titulares")
    if not isinstance(titulares, dict):
        return None
    slug_titular = _slug(titular_origen)
    for nombre, persona in titulares.items():
        if _slug(nombre) == slug_titular and persona in PAGADO_POR_VALIDOS:
            return persona
    return None


def normalizar_borrador(tipo, datos, usuarios, client):
    if tipo not in ("gasto", "ingreso"):
        raise CliError(f"tipo inválido: {tipo!r} (usar 'gasto' o 'ingreso').")
    if not isinstance(datos, dict):
        raise CliError("el JSON de entrada de 'normalizar' debe ser un objeto.")

    telegram = datos.get("telegram") or {}
    if not isinstance(telegram, dict):
        raise CliError("'telegram' debe ser un objeto con chat_id/user_id/message_id.")

    borrador = {}
    defaults_aplicados = []
    advertencias = []
    campos_faltantes = []

    _normalizar_telegram_ids(telegram, borrador)

    # `resolver_usuario` se llama solo para validar que un `user_id`
    # presente sea conocido (error explícito si no) -- el resultado ya no
    # se usa para defaultear `pagado_por` (ver `_normalizar_gasto`: Juan,
    # 2026-10-25, "preguntar siempre quién hizo el gasto" -- un user_id
    # conocido solo identifica quién CARGÓ el mensaje, no quién pagó).
    if telegram.get("user_id") is not None:
        resolver_usuario(usuarios, telegram["user_id"])

    monto_raw = datos.get("monto")
    if monto_raw in (None, ""):
        campos_faltantes.append("monto")
    else:
        try:
            borrador["monto"] = parse_monto_ar(monto_raw)
        except ValueError as exc:
            raise CliError(f"monto inválido: {exc}")

    fecha = datos.get("fecha")
    if not fecha:
        fecha = date.today().isoformat()
        defaults_aplicados.append({"campo": "fecha", "valor": fecha})
        advertencias.append(f"no se especificó fecha, se usó la de hoy ({fecha}).")
    borrador["fecha"] = fecha

    descripcion = datos.get("comercio") or datos.get("descripcion")
    if descripcion:
        borrador["descripcion_original"] = descripcion

    api_tipo = API_TIPOS[tipo]
    categoria_in = datos.get("categoria")
    if not categoria_in:
        campos_faltantes.append("categoria")
    else:
        categorias = client.get_categories(api_tipo)
        resuelta = _resolver_categoria(categorias, categoria_in, datos.get("subcategoria"))
        if resuelta is None:
            opciones = ", ".join(c["categoria"] for c in categorias)
            raise CliError(f"categoría/subcategoría desconocida: {categoria_in!r} (opciones: {opciones}).")
        borrador["categoria"] = resuelta["categoria"]
        if resuelta["subcategoria"]:
            borrador["subcategoria"] = resuelta["subcategoria"]

    pagado_por_sugerido = None
    if tipo == "gasto":
        pagado_por_sugerido = _normalizar_gasto(
            datos, borrador, usuarios, client, campos_faltantes, defaults_aplicados, advertencias,
        )
    else:
        _normalizar_ingreso(datos, borrador, campos_faltantes, advertencias)

    resultado = {
        "borrador": borrador,
        "campos_faltantes": campos_faltantes,
        "defaults_aplicados": defaults_aplicados,
        "advertencias": advertencias,
    }
    if pagado_por_sugerido:
        # Al nivel del resultado, NUNCA dentro de `borrador` -- `borrador`
        # viaja tal cual como payload de `guardar` hacia `POST /api/
        # expenses/telegram`, que rechaza campos desconocidos (ver
        # `api.ALLOWED_EXPENSE_TELEGRAM_FIELDS`).
        resultado["pagado_por_sugerido"] = pagado_por_sugerido
    return resultado


def _validar_proporcion_jd(valor):
    """`proporcion_jd` (custom) debe ser un número finito entre 0 y 100 --
    `proporcion_pinki` se deriva como `100 - proporcion_jd`, así que un valor
    fuera de rango produciría una proporción negativa o mayor a 100 del lado
    de Pinki (ver hallazgo 1, run 9e3e4298)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise CliError(f"proporcion_jd inválida: {valor!r} (debe ser un número finito entre 0 y 100).")
    if not math.isfinite(valor) or valor < 0 or valor > 100:
        raise CliError(f"proporcion_jd inválida: {valor!r} (debe ser un número finito entre 0 y 100).")


def _normalizar_gasto(datos, borrador, usuarios, client, campos_faltantes, defaults_aplicados, advertencias):
    pagado_por_sugerido = None
    medio_pago = datos.get("medio_pago")
    if medio_pago:
        if medio_pago not in MEDIOS_PAGO_VALIDOS:
            raise CliError(f"medio_pago inválido: {medio_pago!r} (usar {MEDIOS_PAGO_VALIDOS}).")
        borrador["medio_pago"] = medio_pago
    else:
        campos_faltantes.append("medio_pago")

    pagado_por = datos.get("pagado_por")
    if pagado_por:
        if pagado_por not in PAGADO_POR_VALIDOS:
            raise CliError(f"pagado_por inválido: {pagado_por!r} (usar {PAGADO_POR_VALIDOS}).")
        borrador["pagado_por"] = pagado_por
    else:
        # `pagado_por` NUNCA tiene default por quién cargó el mensaje de
        # Telegram (Juan, 2026-10-25: "a lo mejor Pinki carga un gasto
        # hecho por JD") -- siempre va a `campos_faltantes`, salvo que el
        # texto lo diga explícito (ese caso ya está arriba, `pagado_por`
        # viene seteado en `datos`) o un comprobante tenga un titular
        # mapeado en `telegram_usuarios.json` ("titulares"): en ese caso se
        # propone en `pagado_por_sugerido`, pero IGUAL queda en
        # `campos_faltantes` -- la sugerencia se muestra para confirmar,
        # nunca se asume (ver `armar_pregunta_con_comprobante`).
        campos_faltantes.append("pagado_por")
        titular_origen = datos.get("titular_origen")
        if titular_origen:
            sugerido = _sugerir_pagado_por_por_titular(titular_origen, usuarios)
            if sugerido:
                pagado_por_sugerido = sugerido
                advertencias.append(
                    f"pagado_por inferido del comprobante ({sugerido}) -- falta confirmar."
                )

    tipo_proporcion = datos.get("tipo_proporcion")
    proporcion_jd = datos.get("proporcion_jd")
    if tipo_proporcion:
        if tipo_proporcion not in TIPO_PROPORCION_VALIDOS:
            raise CliError(f"tipo_proporcion inválido: {tipo_proporcion!r} (usar {TIPO_PROPORCION_VALIDOS}).")
        borrador["tipo_proporcion"] = tipo_proporcion
        if tipo_proporcion == "custom":
            if proporcion_jd is None:
                # `custom` sin porcentaje es un borrador incompleto, no un
                # default inventado -- se pide explícitamente (nunca se
                # arma la pregunta de confirmación con proporcion_jd=None).
                campos_faltantes.append("proporcion_jd")
            else:
                _validar_proporcion_jd(proporcion_jd)
                proporcion_jd = float(proporcion_jd)
                borrador["proporcion_jd"] = proporcion_jd
                borrador["proporcion_pinki"] = 100 - proporcion_jd
        elif proporcion_jd is not None:
            # `dinamico` explícito no acepta proporcion_jd (el backend la
            # rechazaría, ver validaciones.validar_expense): se ignora acá
            # mismo, con una advertencia explícita en vez de un borrador
            # contradictorio.
            advertencias.append(
                "se ignoró proporcion_jd: con tipo_proporcion='dinamico' el reparto se calcula "
                "según los sueldos del mes."
            )
    else:
        # Default documentado en CTO-DISENO.md §1(c): sin `tipo_proporcion`
        # explícito, cualquier pagador (Común, JD o Pinki) usa reparto
        # dinámico -- el valor que acepta la API/dominio
        # (validaciones.TIPO_PROPORCION_VALIDOS) es 'dinamico', no
        # 'dinamica' -- se guarda ese valor, mostrando el default siempre
        # en `defaults_aplicados`, nunca en silencio.
        borrador["tipo_proporcion"] = "dinamico"
        defaults_aplicados.append({"campo": "tipo_proporcion", "valor": "dinamico"})
        if proporcion_jd is not None:
            advertencias.append(
                "se ignoró proporcion_jd: sin tipo_proporcion='custom' el reparto se calcula "
                "según los sueldos del mes."
            )

    cuotas_total = datos.get("cuotas_total")
    if cuotas_total is None:
        borrador["cuotas_total"] = 1
        defaults_aplicados.append({"campo": "cuotas_total", "valor": 1})
    else:
        if isinstance(cuotas_total, bool) or not isinstance(cuotas_total, int):
            raise CliError(f"cuotas_total inválido: {datos.get('cuotas_total')!r}.")
        if not 1 <= cuotas_total <= 120:
            raise CliError("cuotas_total debe ser un entero entre 1 y 120.")
        borrador["cuotas_total"] = cuotas_total

    if borrador.get("monto") is not None and Decimal(str(borrador["monto"])) * 100 < borrador["cuotas_total"]:
        raise CliError("cuotas_total excede los centavos disponibles del monto.")

    return pagado_por_sugerido


def _normalizar_ingreso(datos, borrador, campos_faltantes, advertencias):
    persona = datos.get("persona")
    if persona:
        if persona not in PERSONA_INGRESO_VALIDOS:
            raise CliError(f"persona inválida: {persona!r} (usar {PERSONA_INGRESO_VALIDOS}).")
        borrador["persona"] = persona
    else:
        campos_faltantes.append("persona")

    if borrador.get("categoria") == "Salario":
        advertencias.append("cambia la proporción del mes.")


# --- faltantes / pregunta ------------------------------------------------


def calcular_campos_faltantes(tipo, borrador):
    if tipo == "gasto":
        faltan = [c for c in CAMPOS_OBLIGATORIOS_GASTO if not borrador.get(c)]
        if borrador.get("tipo_proporcion") == "custom" and borrador.get("proporcion_jd") is None:
            faltan.append("proporcion_jd")
        return faltan
    if tipo == "ingreso":
        return [c for c in CAMPOS_OBLIGATORIOS_INGRESO if not borrador.get(c)]
    raise CliError(f"tipo inválido: {tipo!r} (usar 'gasto' o 'ingreso').")


def _pregunta_para_campo(campo, categorias):
    if campo == "categoria":
        opciones = ", ".join(c["categoria"] for c in categorias)
        return f"¿Categoría? (opciones: {opciones})"
    if campo == "tipo_proporcion":
        return "¿Cómo repartimos este gasto? (opciones: dinámico / custom (indicá %))"
    return PREGUNTAS_CAMPO_FIJAS.get(campo, f"¿{campo}?")


def _formatear_pct(valor):
    """'57' para 57.0, '57.5' para 57.5 -- sin ceros decimales de sobra."""
    return f"{valor:g}"


def _resumen_reparto(borrador):
    """Texto del reparto para la pregunta de confirmación (brief: siempre
    mostrado, nunca omitido -- ver `defaults_aplicados` de `tipo_proporcion`
    en `_normalizar_gasto`)."""
    if borrador.get("tipo_proporcion") == "custom" and borrador.get("proporcion_jd") is not None:
        jd = _formatear_pct(borrador["proporcion_jd"])
        pinki = _formatear_pct(borrador.get("proporcion_pinki"))
        return f"Reparto: {jd}% JD / {pinki}% Pinki"
    return "Reparto: dinámico (según sueldos del mes)"


def _resumen_borrador(tipo, borrador):
    monto_fmt = formatear_monto_ar(borrador["monto"])
    categoria = borrador.get("categoria")
    if borrador.get("subcategoria"):
        categoria = f"{categoria} > {borrador['subcategoria']}"
    fecha_fmt = _formatear_fecha_corta(borrador.get("fecha"))

    if tipo == "gasto":
        medio = borrador.get("medio_pago")
        medio_fmt = f"💳 {medio}"
        partes = [f"💰 {monto_fmt}", categoria]
        if borrador.get("descripcion_original"):
            partes.append(f"📝 {borrador['descripcion_original']}")
        partes.append(medio_fmt)
        partes.append(f"Pagó: {borrador.get('pagado_por')}")
        partes.append(_resumen_reparto(borrador))
        partes.append(f"Cuotas: {borrador.get('cuotas_total', 1)}")
        partes.append(f"📅 {fecha_fmt}")
        return " · ".join(partes)

    partes = [f"💰 {monto_fmt}", categoria]
    if borrador.get("descripcion_original"):
        partes.append(f"📝 {borrador['descripcion_original']}")
    partes.append(f"Para: {borrador.get('persona')}")
    partes.append(f"📅 {fecha_fmt}")
    return " · ".join(partes)


def armar_pregunta(tipo, borrador, campos_faltantes, advertencias, categorias):
    if not campos_faltantes:
        lineas = [
            "Che, esto es lo que entendí — avisame si hay que corregir algo:",
            _resumen_borrador(tipo, borrador),
        ]
        for advertencia in advertencias:
            lineas.append(f"⚠️ {advertencia}")
        lineas.append("¿Subo así o cambio algo?")
        return "\n".join(lineas)

    lineas = ["Me falta esto para subirlo, contestame junto:"]
    for indice, campo in enumerate(campos_faltantes, start=1):
        lineas.append(f"{indice}) {_pregunta_para_campo(campo, categorias)}")
    return "\n".join(lineas)


# Orden fijo de la pregunta con comprobante: "lo que el comprobante no trae"
# es, en la práctica, quién pagó y (si no se pudo inferir) la categoría --
# todo lo demás (monto, fecha, medio, destinatario/comercio, nro. de
# operación) ya sale del comprobante (Juan, 2026-10-25).
_ORDEN_PREGUNTA_COMPROBANTE = ("pagado_por", "categoria")


def _resumen_comprobante(borrador):
    """Línea "Leí del comprobante: ..." (brief, punto D): monto, medio de
    pago + a quién (si hay), fecha corta -- todo ya resuelto por `extraer-
    campos`/`normalizar`, sin volver a preguntarlo."""
    partes = []
    if borrador.get("monto") is not None:
        partes.append(formatear_monto_ar(borrador["monto"]))
    medio = borrador.get("medio_pago")
    destino = borrador.get("descripcion_original")
    if medio:
        sufijo_destino = f" a {destino}" if destino else ""
        partes.append(f"{medio.lower()}{sufijo_destino}")
    elif destino:
        partes.append(destino)
    if borrador.get("fecha"):
        partes.append(_formatear_fecha_corta(borrador["fecha"]))
    return "Leí del comprobante: " + " · ".join(partes) if partes else "No pude leer datos del comprobante."


def _pregunta_pagado_por_con_sugerencia(pagado_por_sugerido):
    if pagado_por_sugerido == "JD":
        return "Veo que salió de la cuenta de Juan/JD, ¿lo pagó JD? (JD / Pinki / Común)"
    if pagado_por_sugerido == "Pinki":
        return "Veo que salió de la cuenta de Regina/Pinki, ¿lo pagó Pinki? (JD / Pinki / Común)"
    return "¿Quién lo pagó? (JD / Pinki / Común)"


def armar_pregunta_con_comprobante(
    borrador, campos_faltantes, categorias, pagado_por_sugerido=None,
):
    """Variante de `armar_pregunta` para gastos cargados desde un
    comprobante leído completo (`--con-comprobante`/campo `con_comprobante`
    del borrador, brief punto D): arranca con lo ya leído del comprobante,
    y solo pregunta lo mínimo que el comprobante no trae -- en la práctica,
    quién pagó y la categoría si no se pudo inferir -- mostrando el reparto
    como default informativo.
    """
    lineas = [_resumen_comprobante(borrador)]
    conocidos = []
    if borrador.get("categoria"):
        categoria = borrador["categoria"]
        if borrador.get("subcategoria"):
            categoria += f" > {borrador['subcategoria']}"
        conocidos.append(f"Categoría: {categoria}")
    if borrador.get("pagado_por"):
        conocidos.append(f"Pagó: {borrador['pagado_por']}")
    if conocidos:
        lineas.append(" · ".join(conocidos))

    ordenados = [c for c in _ORDEN_PREGUNTA_COMPROBANTE if c in campos_faltantes]
    ordenados += [c for c in campos_faltantes if c not in _ORDEN_PREGUNTA_COMPROBANTE]

    if not ordenados:
        lineas.append(_resumen_reparto(borrador))
        lineas.append(f"Cuotas: {borrador.get('cuotas_total', 1)}")
        lineas.append("¿Subo así o cambio algo?")
        return "\n".join(lineas)

    for indice, campo in enumerate(ordenados, start=1):
        if campo == "pagado_por":
            lineas.append(f"{indice}) {_pregunta_pagado_por_con_sugerencia(pagado_por_sugerido)}")
        else:
            lineas.append(f"{indice}) {_pregunta_para_campo(campo, categorias)}")
    lineas.append(_resumen_reparto(borrador))
    return "\n".join(lineas)


# --- mensaje-aviso ---------------------------------------------------------


def armar_mensaje_aviso(items):
    """Arma el texto de un solo mensaje para el grupo (DECISIONES.md punto 8:
    "un solo mensaje con el máximo alcanzado"). `items` es una lista de dicts
    con al menos `mes` y `umbral`, y `total` o `total_al_detectar` (acepta
    ambas formas de respuesta de la API: `avisos_credito_nuevos` usa
    `total`, `avisos_credito` de `/pendientes` usa `total_al_detectar`).
    """
    if not items:
        raise CliError("no hay avisos para armar un mensaje.")
    meses = {item["mes"] for item in items}
    if len(meses) != 1:
        raise CliError("mensaje-aviso espera avisos de un solo mes a la vez.")
    mes = next(iter(meses))

    maximo = max(items, key=lambda item: item["umbral"])
    total = maximo.get("total")
    if total is None:
        total = maximo.get("total_al_detectar")
    if total is None:
        raise CliError("el aviso con el umbral máximo no tiene 'total' ni 'total_al_detectar'.")

    nombre_mes = _nombre_mes_es(mes)
    return (
        f"🚨 Los gastos en crédito de {nombre_mes} superaron "
        f"{formatear_monto_ar(maximo['umbral'])} (van {formatear_monto_ar(total)})"
    )


# --- infraestructura de comandos ------------------------------------------


def _leer_texto_arg(valor):
    """Igual que `_leer_json_arg`, pero devuelve el contenido crudo (no lo
    parsea como JSON) -- usado por `extraer-campos`, que recibe texto plano
    de comprobante, no un JSON."""
    if valor is None or valor == "-":
        return sys.stdin.read()
    try:
        return Path(valor).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"no se pudo leer {valor!r}: {exc}")


def _leer_json_arg(valor):
    if valor is None or valor == "-":
        contenido = sys.stdin.read()
        origen = "stdin"
    else:
        try:
            contenido = Path(valor).read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(f"no se pudo leer {valor!r}: {exc}")
        origen = valor
    try:
        return json.loads(contenido)
    except ValueError as exc:
        raise CliError(f"JSON inválido en {origen}: {exc}")


def _resolver_secret(args):
    secret_file = args.secret_file or os.environ.get("LIFE_API_SECRET_FILE")
    if not secret_file:
        raise CliError("falta el secreto: pasá --secret-file o definí LIFE_API_SECRET_FILE.")
    ruta = Path(secret_file)
    if ruta.is_symlink():
        raise CliError(f"--secret-file no puede ser un symlink: {secret_file}")
    try:
        info = ruta.stat()
    except OSError as exc:
        raise CliError(f"no se pudo leer --secret-file ({secret_file}): {exc}")
    if not stat.S_ISREG(info.st_mode):
        raise CliError(f"--secret-file debe ser un archivo regular: {secret_file}")
    if info.st_uid != os.getuid():
        raise CliError(f"--secret-file debe pertenecer al usuario que corre el CLI: {secret_file}")
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise CliError(
            f"--secret-file tiene permisos demasiado abiertos (debe ser 0600 o 0400, "
            f"sin acceso de grupo ni de otros): {secret_file}"
        )
    try:
        secret = ruta.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CliError(f"no se pudo leer --secret-file ({secret_file}): {exc}")
    if not secret:
        raise CliError(f"--secret-file ({secret_file}) está vacío.")
    return secret


def _build_client(args):
    return ApiClient(args.api_base, _resolver_secret(args))


# --- comandos ---------------------------------------------------------------


PDF_MAX_BYTES = 10 * 1024 * 1024
PDF_MAX_PAGINAS_TEXTO = 20
PDF_MAX_CARACTERES = 50_000
PDF_MAX_PAGINAS_RENDER = 3
PDF_RENDER_DPI = 150
PDF_MAX_PIXELS_RENDER = 4_000_000
PDF_MAX_DIMENSION_RENDER = 4096
PDF_TIMEOUT_SECONDS = 20
PDF_STARTUP_AS_BYTES = 2 * 1024 * 1024 * 1024
PDF_PROCESSING_AS_HEADROOM_BYTES = 768 * 1024 * 1024


def _pdf_resource_limits():
    import resource
    # RLIMIT_AS includes Python and PyMuPDF virtual address reservations.
    # Bound startup, then tighten the limit before opening an untrusted PDF.
    resource.setrlimit(resource.RLIMIT_AS, (PDF_STARTUP_AS_BYTES, PDF_STARTUP_AS_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))


def _pdf_limit_after_import():
    """Leave 768 MiB of additional virtual address space for PDF processing.

    RLIMIT_AS measures virtual size, not RSS. On Linux, statm lets us account
    for the loaded runtime while retaining a real cap. Other POSIX systems
    retain the 2 GiB startup cap.
    """
    import resource
    try:
        pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[0])
        baseline = pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    processing_limit = min(soft, baseline + PDF_PROCESSING_AS_HEADROOM_BYTES)
    resource.setrlimit(resource.RLIMIT_AS, (processing_limit, hard))


def cmd_extraer_pdf(args):
    """Aísla PyMuPDF: CPU/memoria reales, timeout y entorno sin credenciales."""
    ruta = Path(args.ruta).absolute()
    if ruta.is_symlink() or not ruta.is_file() or ruta.stat().st_size > PDF_MAX_BYTES:
        raise CliError("el PDF debe ser regular, sin symlink y medir como máximo 10 MB.")
    out_dir = Path(args.out_dir).absolute() if args.out_dir else None
    if out_dir is not None:
        if out_dir.is_symlink() or not out_dir.is_dir():
            raise CliError("--out-dir debe existir y ser un directorio sin symlink.")
        from telegram_retencion import exigir_original_y_salida
        try:
            exigir_original_y_salida(out_dir.parent, ruta, out_dir)
        except ValueError as exc:
            raise CliError(str(exc)) from exc
    job_id = uuid4().hex
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_pdf-worker", str(ruta), "--job-id", job_id]
    if out_dir is not None:
        command += ["--out-dir", str(out_dir)]
    try:
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=PDF_TIMEOUT_SECONDS,
                env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
                close_fds=True, preexec_fn=_pdf_resource_limits,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliError("la extracción del PDF excedió el tiempo máximo.") from exc
        if done.returncode < 0:
            raise CliError("la extracción del PDF excedió límites de recursos o fue interrumpida.")
        try:
            result = json.loads(done.stdout)
        except ValueError as exc:
            raise CliError("la extracción del PDF no produjo JSON válido.") from exc
        if done.returncode or not isinstance(result, dict) or "error" in result:
            raise CliError(result.get("error", "no se pudo extraer el PDF") if isinstance(result, dict) else "no se pudo extraer el PDF")
        return result
    finally:
        if out_dir is not None:
            for temporary in out_dir.glob(f".{job_id}-*.png"):
                if temporary.is_symlink() or temporary.is_file():
                    temporary.unlink()


def _extraer_pdf_worker(args):
    # -I elimina el directorio del script de sys.path; agregar solo el módulo
    # local de retención, sin volver a heredar PYTHONPATH ni variables sensibles.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import pymupdf
    except ImportError as exc:
        raise CliError(
            "pymupdf no está instalado en este entorno. Instalalo en el venv de "
            "ingesta (/home/ai-os/hermes/workspaces/lasso/tools/venv-ingesta) con "
            "'pip install pymupdf' y reintentá."
        ) from exc
    except Exception as exc:
        raise CliError("no se pudo inicializar PyMuPDF dentro del límite de recursos.") from exc
    _pdf_limit_after_import()

    ruta = Path(args.ruta)
    if ruta.is_symlink():
        raise CliError(f"no se acepta un symlink como archivo a procesar: {ruta}")
    if not ruta.is_file():
        raise CliError(f"no existe el archivo: {ruta}")

    tamano = ruta.stat().st_size
    if tamano > PDF_MAX_BYTES:
        raise CliError(
            f"el archivo supera el límite de {PDF_MAX_BYTES // (1024 * 1024)} MB "
            f"({tamano} bytes): {ruta}"
        )

    out_dir = None
    if args.out_dir:
        out_dir = Path(args.out_dir)
        if out_dir.is_symlink() or not out_dir.is_dir():
            raise CliError(f"--out-dir debe existir y ser un directorio (no symlink): {out_dir}")

    try:
        doc = pymupdf.open(str(ruta))
    except Exception as exc:
        raise CliError("no se pudo abrir el PDF (corrupto o formato inválido).") from exc

    try:
        try:
            necesita_clave = doc.needs_pass
            paginas = doc.page_count
        except Exception as exc:
            raise CliError("no se pudo abrir el PDF (corrupto o formato inválido).") from exc
        if necesita_clave:
            raise CliError(f"el PDF está cifrado con contraseña, no se puede procesar: {ruta}")

        truncado_paginas = paginas > PDF_MAX_PAGINAS_TEXTO
        limite_texto = min(paginas, PDF_MAX_PAGINAS_TEXTO)
        # PyMuPDF materializa cada página entera; el límite de memoria del
        # subproceso protege incluso una página comprimida hostil.
        partes_texto = []
        longitud = 0
        truncado_caracteres = False
        try:
            for indice in range(limite_texto):
                parte = doc[indice].get_text()
                espacio = max(0, PDF_MAX_CARACTERES - longitud)
                if len(parte) > espacio:
                    partes_texto.append(parte[:espacio])
                    truncado_caracteres = True
                    break
                partes_texto.append(parte)
                longitud += len(parte) + 1
        except Exception as exc:
            raise CliError("no se pudo leer el contenido del PDF.") from exc

        texto = "\n".join(partes_texto).strip()
        if len(texto) > PDF_MAX_CARACTERES:
            truncado_caracteres = True
            texto = texto[:PDF_MAX_CARACTERES]

        if texto:
            return {
                "texto": texto, "paginas": paginas, "fuente": "pdf_texto", "imagenes": [],
                "truncado": truncado_paginas or truncado_caracteres, "advertencias": [],
            }

        if out_dir is None:
            raise CliError(
                "el PDF no tiene texto extraíble: hace falta --out-dir (debe existir) para "
                "renderizar las páginas como imágenes (para que Lasso las lea con visión)."
            )

        imagenes = []
        advertencias = []
        limite_render = min(paginas, PDF_MAX_PAGINAS_RENDER)
        zoom_base = PDF_RENDER_DPI / 72
        zoom_minimo = 0.01
        try:
            for indice in range(limite_render):
                rect = doc[indice].rect
                zoom = zoom_base
                # Dimensiones del pixmap resultante ANTES de renderizar
                # (`page.rect` está en puntos, 1/72"; el pixmap final mide
                # `rect.width * zoom` x `rect.height * zoom` píxeles): un
                # `MediaBox` extremo no debe disparar un render de decenas
                # de millones de píxeles solo por fijar un DPI constante.
                area_estimada = (rect.width * zoom) * (rect.height * zoom)
                max_width = rect.width * zoom
                max_height = rect.height * zoom
                if area_estimada > PDF_MAX_PIXELS_RENDER or max_width > PDF_MAX_DIMENSION_RENDER or max_height > PDF_MAX_DIMENSION_RENDER:
                    zoom = min(
                        zoom_base,
                        zoom_base * math.sqrt(PDF_MAX_PIXELS_RENDER / area_estimada) if area_estimada > 0 else zoom_base,
                        PDF_MAX_DIMENSION_RENDER / rect.width if rect.width > 0 else zoom_base,
                        PDF_MAX_DIMENSION_RENDER / rect.height if rect.height > 0 else zoom_base,
                    ) * 0.99
                    if zoom < zoom_minimo:
                        advertencias.append(
                            f"página {indice + 1} omitida: la página es demasiado grande para "
                            f"renderizar dentro del límite de {PDF_MAX_PIXELS_RENDER} píxeles."
                        )
                        continue
                    advertencias.append(
                        f"página {indice + 1}: zoom reducido para no superar "
                        f"{PDF_MAX_PIXELS_RENDER} píxeles (la página tiene dimensiones inusuales)."
                    )
                if not (0 < rect.width * zoom <= PDF_MAX_DIMENSION_RENDER and
                        0 < rect.height * zoom <= PDF_MAX_DIMENSION_RENDER and
                        (rect.width * zoom) * (rect.height * zoom) <= PDF_MAX_PIXELS_RENDER):
                    advertencias.append(f"página {indice + 1} omitida: dimensiones fuera de límite.")
                    continue
                pixmap = doc[indice].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                if pixmap.width > PDF_MAX_DIMENSION_RENDER or pixmap.height > PDF_MAX_DIMENSION_RENDER or pixmap.width * pixmap.height > PDF_MAX_PIXELS_RENDER:
                    raise CliError("el pixmap excedió los límites de dimensión.")
                from telegram_retencion import registrar_derivado
                ruta_temporal = out_dir / f".{args.job_id}-{indice + 1}.png"
                try:
                    pixmap.save(str(ruta_temporal))
                    ruta_png = registrar_derivado(out_dir.parent, ruta, ruta_temporal)
                finally:
                    ruta_temporal.unlink(missing_ok=True)
                imagenes.append(str(ruta_png))
        except Exception as exc:
            raise CliError("no se pudo renderizar el PDF a imágenes.") from exc
        return {
            "texto": None, "paginas": paginas, "fuente": "sin_texto", "imagenes": imagenes,
            "truncado": truncado_paginas, "advertencias": advertencias,
        }
    finally:
        doc.close()


def cmd_hash(args):
    ruta = Path(args.ruta)
    if not ruta.is_file():
        raise CliError(f"no existe el archivo: {ruta}")
    hasher = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            hasher.update(bloque)
    return {"sha256": hasher.hexdigest()}


def cmd_extraer_campos(args):
    texto = _leer_texto_arg(args.texto)
    campos = extraer_campos_comprobante(texto)
    usuarios = cargar_usuarios(args.usuarios_file)
    pagado_por_sugerido = None
    if campos.get("titular_origen"):
        pagado_por_sugerido = _sugerir_pagado_por_por_titular(campos["titular_origen"], usuarios)
    campos["pagado_por_sugerido"] = pagado_por_sugerido
    return campos


def cmd_normalizar(args):
    datos = _leer_json_arg(args.json)
    usuarios = cargar_usuarios(args.usuarios_file)
    client = _build_client(args)
    return normalizar_borrador(args.tipo, datos, usuarios, client)


def cmd_faltantes(args):
    datos = _leer_json_arg(args.json)
    borrador = datos.get("borrador", datos) if isinstance(datos, dict) else None
    if not isinstance(borrador, dict):
        raise CliError("el JSON de entrada de 'faltantes' debe ser un borrador u objeto {\"borrador\": {...}}.")
    return {"campos_faltantes": calcular_campos_faltantes(args.tipo, borrador)}


def cmd_pregunta(args):
    datos = _leer_json_arg(args.json)
    if not isinstance(datos, dict):
        raise CliError("el JSON de entrada de 'pregunta' debe ser un objeto (salida de 'normalizar').")
    borrador = datos.get("borrador", datos)
    if not isinstance(borrador, dict):
        raise CliError("'borrador' debe ser un objeto.")
    borrador = {key: value for key, value in borrador.items() if key not in ("tarjeta", "tarjeta_id", "banco")}
    campos_faltantes = datos.get("campos_faltantes")
    if campos_faltantes is None:
        campos_faltantes = calcular_campos_faltantes(args.tipo, borrador)
    else:
        campos_faltantes = [campo for campo in campos_faltantes if campo not in ("tarjeta", "tarjeta_id", "banco")]
    advertencias = [aviso for aviso in (datos.get("advertencias") or [])
                    if "tarjeta" not in aviso.lower() and "banco" not in aviso.lower()]
    con_comprobante = (
        args.con_comprobante or bool(datos.get("con_comprobante")) or bool(borrador.get("con_comprobante"))
    )

    client = _build_client(args)
    categorias = client.get_categories(API_TIPOS[args.tipo])

    if con_comprobante and args.tipo == "gasto":
        pagado_por_sugerido = datos.get("pagado_por_sugerido")
        mensaje = armar_pregunta_con_comprobante(
            borrador, campos_faltantes, categorias, pagado_por_sugerido,
        )
    else:
        mensaje = armar_pregunta(
            args.tipo, borrador, campos_faltantes, advertencias, categorias,
        )
    return {"mensaje": mensaje}


def cmd_dedupe(args):
    client = _build_client(args)
    return client.dedupe(
        args.hash, monto=args.monto, fecha=args.fecha, comercio=args.comercio,
        nro_operacion=args.nro_operacion,
    )


def cmd_guardar(args):
    datos = _leer_json_arg(args.json)
    borrador = datos.get("borrador", datos) if isinstance(datos, dict) else None
    if not isinstance(borrador, dict):
        raise CliError("el JSON de entrada de 'guardar' debe ser un borrador u objeto {\"borrador\": {...}}.")

    if not args.confirmado:
        raise CliError("falta --confirmado: no se guarda nada sin confirmación explícita del usuario.")

    faltan = calcular_campos_faltantes(args.tipo, borrador)
    if faltan:
        raise CliError(
            "faltan campos obligatorios, no se guarda nada.", payload={"campos_faltantes": faltan},
        )

    comprobante = None
    if args.comprobante:
        comprobante = _leer_json_arg(args.comprobante)
        if not isinstance(comprobante, dict):
            raise CliError("el JSON de --comprobante debe ser un objeto.")

    client = _build_client(args)

    if comprobante and not args.forzar_duplicado:
        resultado_dedupe = client.dedupe(
            comprobante.get("hash_archivo"),
            monto=comprobante.get("monto_detectado"),
            fecha=comprobante.get("fecha_detectada"),
            comercio=comprobante.get("comercio_detectado"),
            nro_operacion=comprobante.get("nro_operacion"),
        )
        if resultado_dedupe.get("duplicado"):
            raise CliError(
                "comprobante duplicado, no se guarda nada (usar --forzar-duplicado para subir igual).",
                payload={"duplicado": True, "dedupe": resultado_dedupe},
            )

    payload = {key: value for key, value in borrador.items() if key not in ("tarjeta", "tarjeta_id", "banco")}
    payload["confirmado"] = True
    if comprobante:
        if comprobante.get("ruta_archivo"):
            from telegram_retencion import received_at_para_original
            try:
                comprobante["received_at"] = received_at_para_original(comprobante["ruta_archivo"])
            except ValueError as exc:
                raise CliError(str(exc)) from exc
        payload["comprobante"] = comprobante

    if args.tipo == "gasto":
        respuesta = client.create_expense_telegram(payload)
        ids = [fila["id"] for fila in respuesta["expenses"]]
        return {
            "id": ids[0],
            "ids": ids,
            "avisos_credito_nuevos": respuesta.get("avisos_credito_nuevos", []),
        }

    respuesta = client.create_income_telegram(payload)
    return {"id": respuesta["income"]["id"], "avisos_credito_nuevos": []}


def cmd_avisos_pendientes(args):
    client = _build_client(args)
    return client.avisos_pendientes()


def cmd_marcar_avisos(args):
    items = _leer_json_arg(args.items)
    if not isinstance(items, list):
        raise CliError("--items debe ser una lista JSON de {\"mes\", \"umbral\"}.")
    client = _build_client(args)
    return client.marcar_avisos(items)


def cmd_mensaje_aviso(args):
    datos = _leer_json_arg(args.json)
    if isinstance(datos, list):
        items = datos
    elif isinstance(datos, dict):
        items = datos.get("avisos_credito") or datos.get("avisos_credito_nuevos") or datos.get("nuevos")
    else:
        items = None
    if not isinstance(items, list):
        raise CliError(
            "el JSON de 'mensaje-aviso' debe ser una lista de avisos, o un objeto con "
            "'avisos_credito'/'avisos_credito_nuevos'/'nuevos'."
        )
    return {"mensaje": armar_mensaje_aviso(items)}


def cmd_borrador(args):
    client = _build_client(args)
    if args.accion == "get":
        return client.borrador_get(args.chat, args.usuario)
    if args.accion == "clear":
        return client.borrador_clear(args.chat, args.usuario)

    if not args.json:
        raise CliError("'borrador set' requiere --json con al menos el campo 'estado'.")
    datos = _leer_json_arg(args.json)
    if not isinstance(datos, dict):
        raise CliError("el JSON de 'borrador set' debe ser un objeto.")
    return client.borrador_set(args.chat, args.usuario, datos)


# --- CLI ---------------------------------------------------------------


class ArgumentosInvalidosError(Exception):
    """Errores de `argparse` (opción desconocida, falta un valor requerido,
    etc.) -- se capturan en `main()` para que la salida siga siendo siempre
    JSON por stdout, en vez del texto de uso de `argparse` por stderr."""


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentosInvalidosError(message)


def build_parser():
    parser = _JsonArgumentParser(
        prog="telegram_ingesta.py",
        description="CLI determinista de ingesta por Telegram (cliente HTTP de la API candidata LIFE).",
        allow_abbrev=False,
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help=f"Default: {DEFAULT_API_BASE}.")
    parser.add_argument(
        "--secret-file", default=None,
        help="Ruta al archivo con el secreto interno. Default: $LIFE_API_SECRET_FILE. "
             "El secreto nunca se acepta como valor de argumento.",
    )
    parser.add_argument("--usuarios-file", default=DEFAULT_USUARIOS_FILE)

    subparsers = parser.add_subparsers(dest="comando", required=True)

    sp = subparsers.add_parser("extraer-pdf", allow_abbrev=False)
    sp.add_argument("ruta")
    sp.add_argument("--out-dir", default=None)
    sp.set_defaults(func=cmd_extraer_pdf)

    sp = subparsers.add_parser("_pdf-worker", allow_abbrev=False, help=argparse.SUPPRESS)
    sp.add_argument("ruta")
    sp.add_argument("--out-dir", default=None)
    sp.add_argument("--job-id", required=True)
    sp.set_defaults(func=_extraer_pdf_worker)

    sp = subparsers.add_parser("hash", allow_abbrev=False)
    sp.add_argument("ruta")
    sp.set_defaults(func=cmd_hash)

    sp = subparsers.add_parser("extraer-campos", allow_abbrev=False)
    sp.add_argument("--texto", required=True, help="Ruta a un archivo de texto, o '-' para leer de stdin.")
    sp.set_defaults(func=cmd_extraer_campos)

    sp = subparsers.add_parser("normalizar", allow_abbrev=False)
    sp.add_argument("--tipo", required=True, choices=("gasto", "ingreso"))
    sp.add_argument("--json", required=True, help="Ruta a un JSON, o '-' para leer de stdin.")
    sp.set_defaults(func=cmd_normalizar)

    sp = subparsers.add_parser("faltantes", allow_abbrev=False)
    sp.add_argument("--tipo", required=True, choices=("gasto", "ingreso"))
    sp.add_argument("--json", required=True)
    sp.set_defaults(func=cmd_faltantes)

    sp = subparsers.add_parser("pregunta", allow_abbrev=False)
    sp.add_argument("--tipo", required=True, choices=("gasto", "ingreso"))
    sp.add_argument("--json", required=True)
    sp.add_argument(
        "--con-comprobante", action="store_true",
        help="El borrador viene de un comprobante leído completo: la pregunta arranca con "
             "un resumen de lo leído y solo pide lo mínimo (quién pagó / categoría si falta).",
    )
    sp.set_defaults(func=cmd_pregunta)

    sp = subparsers.add_parser("dedupe", allow_abbrev=False)
    sp.add_argument("--hash", required=True, dest="hash")
    sp.add_argument("--monto", type=float, default=None)
    sp.add_argument("--fecha", default=None)
    sp.add_argument("--comercio", default=None)
    sp.add_argument("--nro-operacion", default=None, dest="nro_operacion")
    sp.set_defaults(func=cmd_dedupe)

    sp = subparsers.add_parser("guardar", allow_abbrev=False)
    sp.add_argument("--tipo", required=True, choices=("gasto", "ingreso"))
    sp.add_argument("--json", required=True)
    sp.add_argument("--comprobante", default=None)
    sp.add_argument("--confirmado", action="store_true")
    sp.add_argument("--forzar-duplicado", action="store_true")
    sp.set_defaults(func=cmd_guardar)

    sp = subparsers.add_parser("avisos-pendientes", allow_abbrev=False)
    sp.set_defaults(func=cmd_avisos_pendientes)

    sp = subparsers.add_parser("marcar-avisos", allow_abbrev=False)
    sp.add_argument("--items", required=True, help="Ruta a un JSON (lista de {mes, umbral}), o '-' para stdin.")
    sp.set_defaults(func=cmd_marcar_avisos)

    sp = subparsers.add_parser("mensaje-aviso", allow_abbrev=False)
    sp.add_argument("--json", required=True)
    sp.set_defaults(func=cmd_mensaje_aviso)

    sp = subparsers.add_parser("borrador", allow_abbrev=False)
    sp.add_argument("accion", choices=("get", "set", "clear"))
    sp.add_argument("--chat", required=True)
    sp.add_argument("--usuario", default=None)
    sp.add_argument("--json", default=None, help="Obligatorio para 'set'.")
    sp.set_defaults(func=cmd_borrador)

    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except ArgumentosInvalidosError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    try:
        resultado = args.func(args)
    except CliError as exc:
        salida = {"error": str(exc)}
        if exc.payload:
            salida.update(exc.payload)
        print(json.dumps(salida, ensure_ascii=False))
        return 1
    except ApiError as exc:
        print(json.dumps({"error": str(exc), "status": exc.status}, ensure_ascii=False))
        return 1
    except Exception as exc:
        # Última red de contención: cualquier excepción no anticipada (bug
        # del CLI) nunca debe escapar como traceback de Python por stderr
        # -- se informa un error genérico por stdout, sin traza ni datos.
        print(json.dumps({"error": f"error interno: {type(exc).__name__}"}, ensure_ascii=False))
        return 1

    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
