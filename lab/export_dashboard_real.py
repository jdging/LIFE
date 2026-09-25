"""Exporta datos REALES (migrados + validados manualmente) para el dashboard de LIFE Lab.

Reemplaza al export de ejemplo (seed_and_export.py, que sigue existiendo para poder
volver a generar datos de prueba si hace falta, pero ya NO es la fuente del
dashboard). Este script NO puede editar seed_and_export.py (fuera del alcance/
allowlist de esta tarea) — ver README.md sección "Bloqueos de procedencia" para
el detalle de qué falta para que la separación demo/real sea completa.

Genera:
- data/gastos.json: gastos reales — origen='migracion' (siempre confiable) o
  marcados explícitamente `es_real=1` tras validación manual (ver
  `es_gasto_real` y README). Ya NO depende de ningún id fijo (antes incluía
  a mano el id=21, el gasto demo 'Cine con Pinki' — ver retirar_cine_demo.py).
- data/ingresos.json: ingresos reales.
- data/resumen_meses.json: por cada mes con datos, total de gastos, total de
  ingresos, proporción JD/Pinki (db.calcular_proporcion_mes), deuda neta del
  mes (db.calcular_deudas_mes) y `estado_deuda` normalizado según la columna
  `saldado` (db.calcular_estado_saldado_mes): 'sin_deuda' | 'pendiente' |
  'parcial' | 'saldado'.
- data/gastos_fijos.json: gastos fijos activos, con responsable/reparto.
- data/deuda_pendiente.json: deuda neta PENDIENTE actual
  (db.calcular_deudas_pendientes, sin filtro de mes), con `estado_deuda`
  ('sin_deuda' o 'pendiente').
- data/compras.json: ítems de `lista_compras` marcados explícitamente como
  reales (`es_real=1`). Fail-closed: por defecto ningún ítem se exporta —
  ver README sección "Bloqueos de procedencia — compras".
- data/recetas.json: recetas activas marcadas `es_real=1`, con sus
  ingredientes embebidos (un fetch por receta, aceptado explícitamente por
  el brief). Fail-closed igual que compras — ver README sección "Bloqueos de
  procedencia — recetas" (hoy no hay marcador confiable para las 27 recetas
  sembradas, así que esto exportará vacío hasta que alguien las revise y
  marque a mano con `db.marcar_receta_real`).
"""

import json
import sys
from pathlib import Path

import db

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR.parent / "src" / "lab-dashboard" / "data"


def es_gasto_real(gasto: dict) -> bool:
    """Un gasto es real si viene de la migración masiva (`origen='migracion'`,
    ya confiable hoy) o si fue marcado explícitamente `es_real=1` tras
    validación manual de un gasto conversacional/web. Nunca por id fijo.
    """
    return gasto["origen"] == "migracion" or bool(gasto.get("es_real"))


def _sin_marcador_interno(fila: dict) -> dict:
    """Copia `fila` sin el marcador interno `es_real` (detalle de implementación,
    no debe filtrarse al JSON consumido por el dashboard)."""
    limpia = dict(fila)
    limpia.pop("es_real", None)
    return limpia


def _escribir_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    conn = db.get_connection()

    gastos = [g for g in db.get_gastos(conn) if es_gasto_real(g)]
    ingresos = db.get_ingresos(conn)
    gastos_fijos = db.get_gastos_fijos(conn, solo_activos=True)
    deuda_pendiente = dict(db.calcular_deudas_pendientes(conn))
    deuda_pendiente["estado_deuda"] = (
        "sin_deuda" if deuda_pendiente["monto"] == 0 else "pendiente"
    )

    meses = sorted({g["fecha"][:7] for g in gastos} | {i["fecha"][:7] for i in ingresos})
    resumen_meses = []
    for mes in meses:
        gastos_mes = [g for g in gastos if g["fecha"].startswith(mes)]
        ingresos_mes = [i for i in ingresos if i["fecha"].startswith(mes)]
        proporcion = db.calcular_proporcion_mes(conn, mes)
        deuda = db.calcular_deudas_mes(conn, mes)
        resumen_meses.append({
            "mes": mes,
            "total_gastos": sum(g["monto"] for g in gastos_mes),
            "total_ingresos": sum(i["monto"] for i in ingresos_mes),
            "proporcion_jd": proporcion.get("JD"),
            "proporcion_pinki": proporcion.get("Pinki"),
            "deuda": deuda,
            "estado_deuda": db.calcular_estado_saldado_mes(conn, mes),
        })

    compras = [
        _sin_marcador_interno(c) for c in db.get_lista_compras(conn) if c.get("es_real")
    ]

    recetas_activas = db.get_recetas(conn, activa=True)
    recetas = []
    for receta in recetas_activas:
        if not receta.get("es_real"):
            continue
        ingredientes = db.get_receta_ingredientes(conn, receta["id"])
        recetas.append({**_sin_marcador_interno(receta), "ingredientes": ingredientes})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _escribir_json(OUT_DIR / "gastos.json", gastos)
    _escribir_json(OUT_DIR / "ingresos.json", ingresos)
    _escribir_json(OUT_DIR / "gastos_fijos.json", gastos_fijos)
    _escribir_json(OUT_DIR / "resumen_meses.json", resumen_meses)
    _escribir_json(OUT_DIR / "deuda_pendiente.json", deuda_pendiente)
    _escribir_json(OUT_DIR / "compras.json", compras)
    _escribir_json(OUT_DIR / "recetas.json", recetas)

    por_responsable = {}
    for gf in gastos_fijos:
        clave = gf.get("responsable") or "(sin responsable)"
        por_responsable[clave] = por_responsable.get(clave, 0) + 1

    print(f"Exportados: {len(gastos)} gastos, {len(ingresos)} ingresos, "
          f"{len(gastos_fijos)} gastos fijos, {len(resumen_meses)} meses con resumen, "
          f"deuda pendiente: {deuda_pendiente}.")
    print(f"Gastos fijos por responsable: {por_responsable}")
    print(f"Exportados: {len(compras)} ítems de compras marcados como reales.")
    print(f"Exportadas: {len(recetas)} recetas marcadas como reales.")

    if not recetas and recetas_activas:
        print(
            f"AVISO: hay {len(recetas_activas)} recetas activas en la base pero "
            "ninguna tiene es_real=1, así que data/recetas.json quedó vacío "
            "(fail-closed). Ver README.md sección 'Bloqueos de procedencia — "
            "recetas' antes de asumir que el módulo Recetas está listo para "
            "mostrar datos.",
            file=sys.stderr,
        )

    conn.close()


if __name__ == "__main__":
    main()
