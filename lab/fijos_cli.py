"""CLI local de Lasso para consultar y versionar gastos fijos."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import db


def crear_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Ruta explícita a la base SQLite")
    comandos = parser.add_subparsers(dest="comando", required=True)
    listar = comandos.add_parser("listar", help="Fijos vigentes en una fecha")
    listar.add_argument("--fecha")
    historial = comandos.add_parser("historial", help="Versiones de una serie")
    historial.add_argument("id", type=int)
    rango = comandos.add_parser("rango", help="Tramos por serie en un período")
    rango.add_argument("desde")
    rango.add_argument("hasta")
    alta = comandos.add_parser("alta", help="Crear una serie")
    alta.add_argument("--nombre", required=True)
    alta.add_argument("--monto", required=True, type=float)
    alta.add_argument("--periodicidad", required=True, choices=("mensual", "bimestral"))
    alta.add_argument("--responsable", required=True, choices=("Común", "JD", "Pinki"))
    alta.add_argument("--desde", required=True)
    alta.add_argument("--categoria")
    alta.add_argument("--subcategoria")
    alta.add_argument("--dia-vencimiento", type=int)
    alta.add_argument("--medio-pago")
    alta.add_argument("--actor", required=True)
    editar = comandos.add_parser("editar", help="Crear una versión modificada")
    editar.add_argument("id", type=int)
    editar.add_argument("--nombre")
    editar.add_argument("--monto", type=float)
    editar.add_argument("--periodicidad", choices=("mensual", "bimestral"))
    editar.add_argument("--responsable", choices=("Común", "JD", "Pinki"))
    editar.add_argument("--desde", required=True)
    editar.add_argument("--actor", required=True)
    baja = comandos.add_parser("baja", help="Cerrar vigencia de una serie")
    baja.add_argument("id", type=int)
    baja.add_argument("--desde", required=True)
    baja.add_argument("--actor", required=True)
    return parser


def _emitir(datos, en_json):
    if en_json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return
    if isinstance(datos, list):
        if not datos:
            print("Sin resultados.")
        for fila in datos:
            _emitir(fila, False)
        return
    if isinstance(datos, dict):
        print(" | ".join(f"{clave}: {valor}" for clave, valor in datos.items()))
        return
    print(datos)


def main(argv=None):
    argumentos = list(sys.argv[1:] if argv is None else argv)
    en_json = "--json" in argumentos
    confirmar = "--confirmar" in argumentos
    argumentos = [item for item in argumentos if item not in ("--json", "--confirmar")]
    parser = crear_parser()
    args = parser.parse_args(argumentos)
    ruta = Path(args.db).expanduser()
    if not ruta.is_file():
        parser.error("--db debe indicar un archivo existente")
    escritura = args.comando in ("alta", "editar", "baja")
    if escritura and not confirmar:
        resumen = {"accion": args.comando, **{
            clave: valor for clave, valor in vars(args).items()
            if clave not in ("db", "comando") and valor is not None
        }}
        _emitir({"requiere_confirmacion": True, "propuesta": resumen}, en_json)
        return 2
    if escritura:
        conn = db.get_connection(str(ruta))
    else:
        conn = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    try:
        if args.comando == "listar":
            resultado = db.get_fijos_vigentes(conn, args.fecha)
            resultado = [{**fila, "monto_mensual": db.monto_mensual(fila)} for fila in resultado]
        elif args.comando == "historial":
            referencia = conn.execute("SELECT fijo_grupo_id FROM gastos_fijos WHERE id = ?", (args.id,)).fetchone()
            if referencia is None:
                raise ValueError(f"No existe el fijo {args.id}.")
            resultado = db.historial_fijo(conn, referencia["fijo_grupo_id"])
        elif args.comando == "rango":
            resultado = db.fijos_por_rango(conn, args.desde, args.hasta)
        elif args.comando == "alta":
            nuevo_id = db.insert_gasto_fijo(conn, {
                "nombre": args.nombre, "monto_estimado": args.monto,
                "periodicidad": args.periodicidad, "responsable": args.responsable,
                "vigente_desde": args.desde, "categoria": args.categoria,
                "subcategoria": args.subcategoria, "dia_vencimiento": args.dia_vencimiento,
                "medio_pago": args.medio_pago,
            }, actor=args.actor)
            resultado = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        elif args.comando == "editar":
            nuevo_id = db.crear_version_fijo(
                conn, args.id, args.monto, args.desde, responsable=args.responsable,
                nombre=args.nombre, periodicidad=args.periodicidad, actor=args.actor,
            )
            resultado = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        else:
            nuevo_id = db.dar_baja_fijo(conn, args.id, args.desde, args.actor)
            resultado = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        _emitir(resultado, en_json)
    except (ValueError, sqlite3.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
