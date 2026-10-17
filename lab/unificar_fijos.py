"""Previsualiza o aplica la unificación explícita de series migradas."""

import argparse
import json
import sqlite3
from pathlib import Path

import db

MAPPING_PATH = Path(__file__).with_name("fijos_series_mapping.json")


def cargar_mapping(path=MAPPING_PATH):
    with open(path, encoding="utf-8") as archivo:
        return json.load(archivo)


def plan_unificacion(conn, mapping):
    """Devuelve estado antes/después sin escribir."""
    planes = []
    hoy = db._now()[:10]
    for grupo in mapping["grupos"]:
        if grupo["confianza"] not in ("alta", "media"):
            continue
        ids = grupo["ids"]
        seleccionadas = conn.execute(
            f"SELECT id, nombre, fijo_grupo_id, vigente_desde, activo FROM gastos_fijos "
            f"WHERE id IN ({','.join('?' for _ in ids)}) ORDER BY vigente_desde, id", ids
        ).fetchall()
        if len(seleccionadas) != len(set(ids)):
            raise ValueError(f"Faltan ids del grupo {grupo['nombre']}.")
        grupos_actuales = sorted({fila["fijo_grupo_id"] for fila in seleccionadas})
        filas = conn.execute(
            f"SELECT id, nombre, fijo_grupo_id, vigente_desde, activo FROM gastos_fijos "
            f"WHERE fijo_grupo_id IN ({','.join('?' for _ in grupos_actuales)}) "
            "ORDER BY vigente_desde, id", grupos_actuales
        ).fetchall()
        destino = min(ids)
        antes = [dict(fila) for fila in filas]
        vigentes_antes = {fila["fijo_grupo_id"]: db.monto_fijo_vigente_en(
            conn, fila["fijo_grupo_id"], hoy) for fila in filas}
        versiones = sorted(antes, key=lambda fila: (fila["vigente_desde"], fila["id"]))
        vigente_despues = next((fila for fila in reversed(versiones)
                                  if fila["vigente_desde"] <= hoy), None)
        planes.append({"nombre": grupo["nombre"], "confianza": grupo["confianza"],
                      "ids": ids, "destino": destino, "antes": antes,
                      "despues": [{**fila, "fijo_grupo_id": destino} for fila in antes],
                      "vigentes_antes": vigentes_antes,
                      "vigente_despues": vigente_despues})
    return planes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Ruta explícita a la base SQLite")
    parser.add_argument("--apply", action="store_true", help="Aplicar grupos alta/media")
    parser.add_argument("--actor", default="unificar_fijos")
    args = parser.parse_args(argv)
    mapping = cargar_mapping()
    for item in mapping["a_confirmar"]:
        print(f"A confirmar en QA, sin tocar: {item['id']} {item['nombre']} - {item['nota']}")
    if not args.db:
        if args.apply:
            parser.error("--apply requiere --db explícito")
        print("Sin --db: no se abrió ninguna base. Indicá --db para ver el antes/después.")
        return 0
    ruta = Path(args.db).expanduser()
    if not ruta.is_file():
        parser.error("La ruta --db debe ser un archivo existente.")
    if args.apply:
        conn = db.get_connection(str(ruta))
    else:
        conn = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    try:
        if args.apply:
            conn.execute("BEGIN IMMEDIATE")
        planes = plan_unificacion(conn, mapping)
        for plan in planes:
            print(f"{plan['nombre']} ({plan['confianza']}): destino {plan['destino']}")
            print(f"  antes: {json.dumps(plan['antes'], ensure_ascii=False)}")
            print(f"  vigente hoy antes: {json.dumps(plan['vigentes_antes'], ensure_ascii=False)}")
            print(f"  después: {json.dumps(plan['despues'], ensure_ascii=False)}")
            print(f"  vigente hoy después: {json.dumps(plan['vigente_despues'], ensure_ascii=False)}")
        if args.apply:
            for plan in planes:
                db.unificar_series_fijos(conn, plan["ids"], args.actor, commit=False)
            conn.commit()
            print("Unificación aplicada.")
        else:
            print("DRY-RUN: sin cambios.")
    except Exception:
        if args.apply:
            conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
