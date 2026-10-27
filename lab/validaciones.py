"""Validaciones puras para el contrato de `api-contract.md`.

Sin SQLite, sin I/O: solo reciben un dict (payload JSON ya parseado) y
devuelven una lista de mensajes de error (vacía si el payload es válido).
Pensadas para usarse como capa de validación antes de tocar la base real,
cuando exista la infraestructura que hoy no está desplegada (ver README.md).
"""

import math
import re
from datetime import datetime
from decimal import Decimal

_FORMATO_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PAGADO_POR_VALIDOS = ("Común", "JD", "Pinki")
TIPO_PROPORCION_VALIDOS = ("dinamico", "custom")
TOLERANCIA_PROPORCION = 0.01
MAX_CUOTAS = 120

# A diferencia de `pagado_por` (gastos), un ingreso siempre pertenece a una
# persona concreta — "Común" no es válido acá (ver brief t_65096083).
PERSONA_INGRESO_VALIDOS = ("JD", "Pinki")
MEDIOS_PAGO_VALIDOS = ("Crédito", "Débito", "Efectivo", "Transferencia")


def _es_numero(valor) -> bool:
    """True solo para `int`/`float` finitos (rechaza `bool`, `NaN` e infinito).

    Centralizado acá porque antes cada validación individual (monto,
    proporciones, monto_estimado) podía dejar pasar `NaN`/`inf` ya que
    `NaN <= 0` y las comparaciones de tolerancia con `NaN` dan `False`
    (hallazgo de revisor independiente, run 3b184396). Corregir una sola vez
    acá cierra el hueco en todas las validaciones que ya usan `_es_numero`.
    """
    if isinstance(valor, bool):
        return False
    if not isinstance(valor, (int, float)):
        return False
    return math.isfinite(valor)


def _es_fecha_iso(valor) -> bool:
    """True solo para 'YYYY-MM-DD' con padding estricto de 4-2-2 dígitos y
    calendario válido.

    `datetime.strptime(..., "%Y-%m-%d")` por sí solo no alcanza: es laxo con
    el padding (acepta "2026-2-01" como si fuera "2026-02-01"), lo que
    colaba fechas no-ISO en `crear_version_fijo`/`insert_gasto_fijo` y rompía
    el orden lexicográfico que usa `monto_fijo_vigente_en` para comparar
    `vigente_desde` entre versiones.
    """
    if not isinstance(valor, str) or not _FORMATO_FECHA_ISO.match(valor):
        return False
    try:
        datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def validar_expense(payload: dict) -> list:
    """Valida un payload de `POST /api/expenses` según `api-contract.md`.

    Devuelve una lista de errores (vacía si el payload es válido). No
    muta `payload` ni toca la base de datos.
    """
    errores = []

    monto = payload.get("monto")
    if not _es_numero(monto):
        errores.append("monto es obligatorio y debe ser numérico.")
    elif monto <= 0:
        errores.append("monto debe ser mayor a 0.")

    categoria = payload.get("categoria")
    if not isinstance(categoria, str) or not categoria.strip():
        errores.append("categoria es obligatoria y no puede estar vacía.")

    pagado_por = payload.get("pagado_por")
    if pagado_por is not None and pagado_por not in PAGADO_POR_VALIDOS:
        errores.append(
            f"pagado_por inválido: {pagado_por!r} (usar {PAGADO_POR_VALIDOS})."
        )

    tipo_proporcion = payload.get("tipo_proporcion", "dinamico") or "dinamico"
    proporcion_jd = payload.get("proporcion_jd")
    proporcion_pinki = payload.get("proporcion_pinki")

    if tipo_proporcion not in TIPO_PROPORCION_VALIDOS:
        errores.append(
            f"tipo_proporcion inválido: {tipo_proporcion!r} "
            f"(usar {TIPO_PROPORCION_VALIDOS})."
        )
    elif tipo_proporcion == "custom":
        if proporcion_jd is None or proporcion_pinki is None:
            errores.append(
                "tipo_proporcion='custom' requiere proporcion_jd y "
                "proporcion_pinki explícitas."
            )
        elif not _es_numero(proporcion_jd) or not _es_numero(proporcion_pinki):
            errores.append("proporcion_jd y proporcion_pinki deben ser numéricas.")
        elif not (0 <= proporcion_jd <= 100) or not (0 <= proporcion_pinki <= 100):
            errores.append(
                "proporcion_jd y proporcion_pinki deben estar entre 0 y 100 "
                f"(recibido {proporcion_jd} y {proporcion_pinki})."
            )
        elif abs((proporcion_jd + proporcion_pinki) - 100) > TOLERANCIA_PROPORCION:
            errores.append(
                "proporcion_jd + proporcion_pinki debe sumar 100 "
                f"(±{TOLERANCIA_PROPORCION}); recibido "
                f"{proporcion_jd} + {proporcion_pinki}."
            )
    else:  # dinamico
        if proporcion_jd is not None or proporcion_pinki is not None:
            errores.append(
                "tipo_proporcion='dinamico' no debe traer proporcion_jd/"
                "proporcion_pinki."
            )

    cuotas_total = payload.get("cuotas_total", 1)
    if cuotas_total is None:
        cuotas_total = 1
    if (not isinstance(cuotas_total, int) or isinstance(cuotas_total, bool)
            or not 1 <= cuotas_total <= MAX_CUOTAS):
        errores.append("cuotas_total debe ser un entero entre 1 y 120.")
        cuotas_total = None  # evita validar cuota_nro contra un valor inválido
    elif _es_numero(monto) and monto > 0 and Decimal(str(monto)) * 100 < cuotas_total:
        errores.append("cuotas_total excede los centavos disponibles del monto.")

    cuota_nro = payload.get("cuota_nro", 1)
    if cuota_nro is None:
        cuota_nro = 1
    if not isinstance(cuota_nro, int) or isinstance(cuota_nro, bool) or cuota_nro < 1:
        errores.append("cuota_nro debe ser un entero >= 1.")
    elif cuotas_total is not None and cuota_nro > cuotas_total:
        errores.append(
            f"cuota_nro ({cuota_nro}) no puede ser mayor a cuotas_total "
            f"({cuotas_total})."
        )

    return errores


def validar_telegram_expense(payload: dict) -> list:
    """Campos explícitos del flujo Telegram, antes de permitir defaults de DB."""
    errores = validar_expense(payload)
    if payload.get("confirmado") is not True:
        errores.append("confirmado=True es obligatorio para Telegram.")
    if not _es_fecha_iso(payload.get("fecha")):
        errores.append("fecha ISO explícita es obligatoria para Telegram.")
    if payload.get("pagado_por") not in PAGADO_POR_VALIDOS:
        errores.append("pagado_por explícito es obligatorio para Telegram.")
    medio = payload.get("medio_pago")
    if medio not in MEDIOS_PAGO_VALIDOS:
        errores.append("medio_pago explícito es obligatorio para Telegram.")
    if medio in ("Crédito", "Débito") and not isinstance(payload.get("tarjeta_id"), str):
        errores.append("tarjeta_id es obligatoria para Crédito o Débito.")
    elif medio in ("Crédito", "Débito") and not payload["tarjeta_id"].strip():
        errores.append("tarjeta_id es obligatoria para Crédito o Débito.")
    return errores


def validar_telegram_ingreso(payload: dict) -> list:
    errores = validar_ingreso(payload)
    if payload.get("confirmado") is not True:
        errores.append("confirmado=True es obligatorio para Telegram.")
    if not _es_fecha_iso(payload.get("fecha")):
        errores.append("fecha ISO explícita es obligatoria para Telegram.")
    return errores


def validar_fixed_update(payload: dict) -> list:
    """Valida un payload de `PATCH /api/fixed/:id` según `api-contract.md`.

    Devuelve una lista de errores (vacía si el payload es válido).
    """
    errores = []

    monto_estimado = payload.get("monto_estimado")
    if not _es_numero(monto_estimado):
        errores.append("monto_estimado es obligatorio y debe ser numérico.")
    elif monto_estimado <= 0:
        errores.append("monto_estimado debe ser mayor a 0.")

    return errores


def validar_ingreso(payload: dict) -> list:
    """Valida un payload de alta/edición de ingreso (`db.insert_ingreso` /
    `db.actualizar_ingreso`), mismas convenciones que `validar_expense`.

    Reglas (ver brief t_65096083):
      - `monto` obligatorio, numérico, > 0.
      - `persona` obligatoria, debe estar en {"JD", "Pinki"} — a diferencia
        de `pagado_por` en gastos, un ingreso NO admite "Común": siempre es
        de una persona concreta.
      - `categoria` obligatoria, no vacía.

    Devuelve una lista de errores (vacía si el payload es válido). No muta
    `payload` ni toca la base de datos.
    """
    errores = []

    monto = payload.get("monto")
    if not _es_numero(monto):
        errores.append("monto es obligatorio y debe ser numérico.")
    elif monto <= 0:
        errores.append("monto debe ser mayor a 0.")

    persona = payload.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        errores.append("persona es obligatoria y no puede estar vacía.")
    elif persona not in PERSONA_INGRESO_VALIDOS:
        errores.append(
            f"persona inválida: {persona!r} (usar {PERSONA_INGRESO_VALIDOS})."
        )

    categoria = payload.get("categoria")
    if not isinstance(categoria, str) or not categoria.strip():
        errores.append("categoria es obligatoria y no puede estar vacía.")

    return errores


def validar_gasto_fijo(payload: dict) -> list:
    """Valida una versión (alta o `crear_version_fijo`) de `gastos_fijos`.

    Reglas (corrección pedida por revisor independiente tras dictamen NO
    APTO, run 3b184396, hallazgo 5; `responsable` relajado a opcional en la
    corrección posterior, run 3e22f249, para compatibilidad legacy con
    `reference/db.py`):
      - `monto_estimado` obligatorio, numérico, finito, > 0.
      - `nombre` no vacío y `periodicidad` mensual o bimestral.
      - `vigente_desde` obligatoria, fecha ISO 'YYYY-MM-DD' válida (una
        comparación lexicográfica como la de `monto_fijo_vigente_en` da
        orden incorrecto con fechas no normalizadas, ej. '2026-2-01').
      - `responsable`: OPCIONAL (`None` se acepta y se conserva tal cual,
        igual que `reference/db.py` — un gasto fijo legacy sin responsable
        asignado no debe rechazarse ni inventársele un dueño). Si SE
        especifica (no es `None`), debe ser un string no vacío en
        {"Común", "JD", "Pinki"}. La futura capa web sí exigirá
        `responsable` obligatorio (ver README); esta capa de dominio no.
      - `categoria`: OPCIONAL (`None` se acepta y se conserva tal cual — un
        fijo legacy sin categoría asignada no debe rechazarse ni
        inventársele una). Si SE especifica, debe ser un string no vacío;
        no hay catálogo cerrado de categorías para fijos (brief t_38a7253f,
        punto 5).
      - `subcategoria`: igual regla que `categoria` (brief t_38a7253f F1b,
        hallazgo A) — opcional, se conserva tal cual, string no vacío si se
        especifica.
      - Regla cruzada (brief t_38a7253f F1b-fix2, hallazgo 2 del revisor): no
        puede quedar `subcategoria` asignada sin `categoria`. Se valida sobre
        los valores YA RESUELTOS (tras heredar/vaciar en `crear_version_fijo`
        o `insert_gasto_fijo`), así que aplica tanto al alta como a cada
        versión nueva.

    Devuelve una lista de errores (vacía si el payload es válido). No muta
    `payload` ni toca la base de datos.
    """
    errores = []

    nombre = payload.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        errores.append("nombre es obligatorio y no puede estar vacío.")

    if payload.get("periodicidad") not in ("mensual", "bimestral"):
        errores.append("periodicidad debe ser mensual o bimestral.")

    monto_estimado = payload.get("monto_estimado")
    if not _es_numero(monto_estimado):
        errores.append("monto_estimado es obligatorio y debe ser numérico y finito.")
    elif monto_estimado <= 0:
        errores.append("monto_estimado debe ser mayor a 0.")

    vigente_desde = payload.get("vigente_desde")
    if not _es_fecha_iso(vigente_desde):
        errores.append(
            f"vigente_desde debe ser una fecha ISO 'YYYY-MM-DD' válida "
            f"(recibido {vigente_desde!r})."
        )

    responsable = payload.get("responsable")
    if responsable is not None:
        if not isinstance(responsable, str) or not responsable.strip():
            errores.append("responsable, si se especifica, no puede estar vacío.")
        elif responsable not in PAGADO_POR_VALIDOS:
            errores.append(
                f"responsable inválido: {responsable!r} (usar {PAGADO_POR_VALIDOS})."
            )

    categoria = payload.get("categoria")
    if categoria is not None and (not isinstance(categoria, str) or not categoria.strip()):
        errores.append("categoria, si se especifica, no puede estar vacía.")

    subcategoria = payload.get("subcategoria")
    if subcategoria is not None and (not isinstance(subcategoria, str) or not subcategoria.strip()):
        errores.append("subcategoria, si se especifica, no puede estar vacía.")

    if subcategoria is not None and categoria is None:
        errores.append("subcategoria no puede quedar asignada sin categoria.")

    return errores
