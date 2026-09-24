"""Exporta datos REALES (migrados + conversacionales) para el dashboard de LIFE Lab.

Reemplaza al export de ejemplo (seed_and_export.py, que sigue existiendo para poder volver
a generar datos de prueba si hace falta, pero ya NO es la fuente del dashboard).

Genera:
- data/gastos.json: gastos reales (origen='migracion' o el gasto conversacional real).
- data/ingresos.json: ingresos reales.
- data/resumen_meses.json: por cada mes con datos, total de gastos, total de ingresos,
  proporción JD/Pinki calculada (db.calcular_proporcion_mes) y deuda neta del mes
  (db.calcular_deudas_mes).
- data/gastos_fijos.json: gastos fijos activos, incluyendo `responsable`
  ('Común'/'JD'/'Pinki') y `tipo_proporcion`/`proporcion_jd`/`medio_pago`,
  para que el dashboard pueda separar "Fijos comunes" de "Fijos míos" y
  "Fijos de Pinki" en vez de sumarlos todos juntos (ver README).
- data/deuda_pendiente.json: deuda neta PENDIENTE actual (db.calcular_deudas_pendientes,
  sin filtro de mes) — solo gastos con saldado=NULL, sin importar de qué mes sean. Es lo
  que Juan pidió ver (no el histórico mes a mes, que ya está saldado en su mayoría).
"""

import json
import sys
from pathlib import Path

import db

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR.parent / "src" / "lab-dashboard" / "data"


def main() -> None:
    conn = db.get_connection()

    gastos = [g for g in db.get_gastos(conn) if g["origen"] == "migracion" or g["id"] == 21]
    ingresos = db.get_ingresos(conn)
    gastos_fijos = db.get_gastos_fijos(conn, solo_activos=True)
    deuda_pendiente = db.calcular_deudas_pendientes(conn)

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
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "gastos.json", "w", encoding="utf-8") as f:
        json.dump(gastos, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / "ingresos.json", "w", encoding="utf-8") as f:
        json.dump(ingresos, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / "gastos_fijos.json", "w", encoding="utf-8") as f:
        json.dump(gastos_fijos, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / "resumen_meses.json", "w", encoding="utf-8") as f:
        json.dump(resumen_meses, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / "deuda_pendiente.json", "w", encoding="utf-8") as f:
        json.dump(deuda_pendiente, f, ensure_ascii=False, indent=2)

    por_responsable = {}
    for gf in gastos_fijos:
        clave = gf.get("responsable") or "(sin responsable)"
        por_responsable[clave] = por_responsable.get(clave, 0) + 1

    print(f"Exportados: {len(gastos)} gastos, {len(ingresos)} ingresos, "
          f"{len(gastos_fijos)} gastos fijos, {len(resumen_meses)} meses con resumen, "
          f"deuda pendiente: {deuda_pendiente}.")
    print(f"Gastos fijos por responsable: {por_responsable}")
    conn.close()


if __name__ == "__main__":
    main()
