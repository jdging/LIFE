"""Validaciones puras para el contrato de `api-contract.md`.

Sin SQLite, sin I/O: solo reciben un dict (payload JSON ya parseado) y
devuelven una lista de mensajes de error (vacía si el payload es válido).
Pensadas para usarse como capa de validación antes de tocar la base real,
cuando exista la infraestructura que hoy no está desplegada (ver README.md).
"""

from typing import Optional

PAGADO_POR_VALIDOS = ("Común", "JD", "Pinki")
TIPO_PROPORCION_VALIDOS = ("dinamico", "custom")
TOLERANCIA_PROPORCION = 0.01


def _es_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


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
    if not isinstance(cuotas_total, int) or isinstance(cuotas_total, bool) or cuotas_total < 1:
        errores.append("cuotas_total debe ser un entero >= 1.")
        cuotas_total = None  # evita validar cuota_nro contra un valor inválido

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
