"""CLI determinista para leer facturas de gastos fijos (gas, EPE, internet)
y proponer/aplicar la actualización de `monto_estimado` (mejora #4 de Juan,
2026-11-05).

Mismo patrón de `lab/telegram_ingesta.py` (brief S2/S3): nunca importa
`db.py`/`api.py` ni abre la base SQLite directo, todo pasa por `/api/*` con
`X-Internal-Proxy-Secret`. Reutiliza `ApiClient`, `CliError`, `ApiError` y la
resolución de secreto de `telegram_ingesta` en vez de duplicarlos.

El texto de la factura es un DATO: se trata con regex y comparaciones de
string exactas, nunca como instrucción.

En el flujo real, el agente (Lasso) recibe el PDF por Telegram, lo lee con
su extracción de texto nativa (no hace falta `extraer-pdf` de
`telegram_ingesta` para esto), corre `extraer` sobre ese texto para
proponer el monto, se lo confirma a Juan por el mismo chat y recién después
corre `actualizar --confirmado`.

Subcomandos:
    extraer --texto <archivo.txt o -> [--proveedor auto|gas|epe|internet]
    actualizar --fixed-id N --monto M [--vigente-desde YYYY-MM-DD] --confirmado
    listar-fijos   (proxy de GET /api/fixed, para ubicar el id correcto)
"""

import argparse
import json
import re
import sys
from datetime import date, datetime

from telegram_ingesta import (
    ApiError,
    CliError,
    _build_client,
    _leer_texto_arg,
    _validar_monto_final,
)

PROVEEDORES = ("gas", "epe", "internet")


class _ArgumentParserSinSalida(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(f"argumentos inválidos: {message}")


def _parse_monto_es(token):
    """Convierte "158.277,32" / "22.965,01" (punto miles, coma decimal
    opcional) a float. Las facturas argentinas de estos proveedores nunca
    usan el formato "45k"/"45 mil" de un chat -- alcanza con este caso."""
    token = token.strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d{1,2})?", token):
        raise CliError(f"monto con formato inesperado en la factura: {token!r}")
    entero, _, decimales = token.partition(",")
    normalizado = entero.replace(".", "") + ("." + decimales if decimales else "")
    return _validar_monto_final(float(normalizado))


def _fecha_ddmmyyyy_a_iso(token):
    try:
        return datetime.strptime(token, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def detectar_proveedor(texto):
    if "Litoral Gas" in texto:
        return "gas"
    if "Empresa Provincial de la Energía" in texto or re.search(r"\bEPE\b", texto):
        return "epe"
    if "TELECOM ARGENTINA" in texto.upper() or re.search(r"Internet\s+\d+\s*MB", texto):
        return "internet"
    return None


def _parsear_gas(texto):
    # Litoral Gas S.A.: "TOTAL A PAGAR hasta el 10/11/2026: 158.277,32"
    m = re.search(r"TOTAL A PAGAR hasta el (\d{2}/\d{2}/\d{4})[:\s]+\$?\s*([\d.,]+)", texto)
    if not m:
        return None, None
    return _parse_monto_es(m.group(2)), _fecha_ddmmyyyy_a_iso(m.group(1))


def _parsear_epe(texto):
    # EPE factura un bimestre en 2 cuotas mensuales ("Cuota 1"/"Cuota 2"),
    # cada una con su propio vencimiento e importe. Se usa siempre la
    # Cuota 1 (la de vencimiento más próximo) como monto representativo del
    # gasto fijo mensual -- la Cuota 2 queda en "detalle" por si Juan
    # prefiere promediarlas a mano.
    cuota1 = re.search(r"Cuota 1\s+(\d{2}/\d{2}/\d{4})\s+\$\s*([\d.,]+)", texto)
    cuota2 = re.search(r"Cuota 2\s+(\d{2}/\d{2}/\d{4})\s+\$\s*([\d.,]+)", texto)
    if not cuota1:
        return None, None, None
    monto = _parse_monto_es(cuota1.group(2))
    vencimiento = _fecha_ddmmyyyy_a_iso(cuota1.group(1))
    detalle_cuota2 = None
    if cuota2:
        detalle_cuota2 = {
            "monto": _parse_monto_es(cuota2.group(2)),
            "vencimiento": _fecha_ddmmyyyy_a_iso(cuota2.group(1)),
        }
    return monto, vencimiento, detalle_cuota2


def _parsear_internet(texto):
    # Telecom: "Tu saldo total es de $ 22.965,01 y vence el día 11/11/2026"
    m = re.search(r"saldo total es de \$\s*([\d.,]+) y vence el d[ií]a (\d{2}/\d{2}/\d{4})", texto)
    if not m:
        return None, None
    return _parse_monto_es(m.group(1)), _fecha_ddmmyyyy_a_iso(m.group(2))


def extraer_factura(texto, proveedor=None):
    """Devuelve {"proveedor", "monto", "vencimiento", "detalle", "formato_desconocido"}.

    `proveedor=None`/"auto" detecta por el texto; si se pasa explícito, se usa
    ese parser igual (útil si la detección automática falla pero Juan sabe
    de qué factura se trata)."""
    detectado = detectar_proveedor(texto)
    usar = proveedor if proveedor and proveedor != "auto" else detectado
    if usar not in PROVEEDORES:
        return {"proveedor": detectado, "monto": None, "vencimiento": None,
                "detalle": None, "formato_desconocido": True}

    detalle = None
    if usar == "gas":
        monto, vencimiento = _parsear_gas(texto)
    elif usar == "epe":
        monto, vencimiento, detalle = _parsear_epe(texto)
    else:
        monto, vencimiento = _parsear_internet(texto)

    if monto is None:
        return {"proveedor": usar, "monto": None, "vencimiento": None,
                "detalle": None, "formato_desconocido": True}
    return {"proveedor": usar, "monto": monto, "vencimiento": vencimiento,
            "detalle": detalle, "formato_desconocido": False}


# --- comandos -----------------------------------------------------------


def cmd_extraer(args):
    texto = _leer_texto_arg(args.texto)
    resultado = extraer_factura(texto, args.proveedor)
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if not resultado["formato_desconocido"] else 1


def cmd_listar_fijos(args):
    client = _build_client(args)
    fijos = client.list_fixed()
    print(json.dumps(fijos, ensure_ascii=False))
    return 0


def cmd_actualizar(args):
    if not args.confirmado:
        raise CliError("falta --confirmado: mostrale el monto propuesto a Juan antes de aplicar.")
    monto = _validar_monto_final(args.monto)
    vigente_desde = args.vigente_desde or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", vigente_desde):
        raise CliError("--vigente-desde debe ser 'YYYY-MM-DD'.")
    client = _build_client(args)
    resultado = client.update_fixed(args.fixed_id, monto, vigente_desde)
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


def _build_parser():
    parser = _ArgumentParserSinSalida(description="Lee facturas de gastos fijos y propone/aplica el monto.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8765")
    parser.add_argument("--secret-file")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_extraer = sub.add_parser("extraer")
    p_extraer.add_argument("--texto", required=True)
    p_extraer.add_argument("--proveedor", choices=("auto",) + PROVEEDORES, default="auto")
    p_extraer.set_defaults(func=cmd_extraer)

    p_listar = sub.add_parser("listar-fijos")
    p_listar.set_defaults(func=cmd_listar_fijos)

    p_actualizar = sub.add_parser("actualizar")
    p_actualizar.add_argument("--fixed-id", type=int, required=True)
    p_actualizar.add_argument("--monto", type=float, required=True)
    p_actualizar.add_argument("--vigente-desde")
    p_actualizar.add_argument("--confirmado", action="store_true")
    p_actualizar.set_defaults(func=cmd_actualizar)

    return parser


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except CliError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2 if isinstance(exc, CliError) and "argumentos inválidos" in str(exc) else 1
    except ApiError as exc:
        payload = {"error": str(exc)}
        if exc.body:
            payload["detalle"] = exc.body
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    except Exception as exc:  # última red de contención, igual que telegram_ingesta
        print(json.dumps({"error": f"error interno: {type(exc).__name__}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
