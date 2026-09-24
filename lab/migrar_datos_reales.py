"""Migración de datos reales de LIFE (Finanzas + Inventario) desde Sheets.

Lee `finanzas_raw.json` e `inventario_raw.json` (export real de Juan, ya
parseado por el coordinador) y los vuelca en la base SQLite del laboratorio
usando el esquema de `db.py`, sin modificarlo. Ver README.md para el detalle
completo del mapeo de campos y las decisiones tomadas.

Uso: `python3 migrar_datos_reales.py` desde este workdir.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import db

WORKDIR = Path(__file__).resolve().parent
FINANZAS_PATH = WORKDIR / "finanzas_raw.json"
INVENTARIO_PATH = WORKDIR / "inventario_raw.json"


def _cargar_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Tarjetas ----------------------------------------------------------

def migrar_tarjetas(conn, filas: list) -> int:
    """Inserta las tarjetas del Excel con sus ids exactos (TC1/TD1/TC2/TD2/TC3).

    Idempotente por PK: si el id ya existe (p.ej. TC1 marcada como default
    dinámico en una tarea anterior), la salteamos sin tocarla en vez de
    intentar un update, para no pisar el flag `es_default_dinamico` ya
    seteado (ver README).
    """
    existentes = {t["id"] for t in db.get_tarjetas(conn)}
    nuevas = 0
    for fila in filas:
        tarjeta_id = fila["id"]
        if tarjeta_id in existentes:
            continue
        db.insert_tarjeta(
            conn,
            {
                "id": tarjeta_id,
                "nombre": fila["nombre"],
                "tipo": fila["tipo"],
                "banco": fila.get("banco"),
                "titular": "JD",
                "dia_cierre": int(fila["dia_cierre"]) if fila.get("dia_cierre") is not None else None,
                "dia_vencimiento": (
                    int(fila["dia_vencimiento"]) if fila.get("dia_vencimiento") is not None else None
                ),
                # Solo TC1 (Visa BNA) está confirmada como default dinámico y
                # de uso compartido; el resto queda en False por default (ver
                # README: "no está confirmado" para TD1/TC2/TD2/TC3).
                "es_default_dinamico": tarjeta_id == "TC1",
                "uso_compartido": tarjeta_id == "TC1",
            },
        )
        nuevas += 1
    return nuevas


# --- Categorías ----------------------------------------------------------

def migrar_categorias(conn, filas: list) -> int:
    for fila in filas:
        db.crear_categoria_si_no_existe(
            conn, fila["tipo"], fila["categoria"], fila.get("subcategoria"),
            creada_por="migracion",
        )
    return len(filas)


# --- Gastos fijos ----------------------------------------------------------

def migrar_gastos_fijos(conn, filas: list) -> int:
    """Migra `gastos_fijos`, idempotente por clave natural (sin columna `origen`).

    Como la tabla no tiene `origen`, usamos (nombre, categoria, subcategoria,
    ultima_actualizacion) como clave natural de la fila del Excel: antes de
    insertar, borramos cualquier fila previa con esa misma clave y volvemos a
    insertar. Correr el script dos veces reemplaza cada fila por una idéntica
    en vez de duplicarla (ver README).
    """
    migrados = 0
    for fila in filas:
        nombre = fila["descripcion"]
        categoria = fila.get("categoria")
        subcategoria = fila.get("subcategoria")
        ultima_actualizacion = fila.get("vigente_desde")

        conn.execute(
            "DELETE FROM gastos_fijos WHERE nombre = ? AND categoria IS ? "
            "AND subcategoria IS ? AND ultima_actualizacion IS ?",
            (nombre, categoria, subcategoria, ultima_actualizacion),
        )
        db.insert_gasto_fijo(
            conn,
            {
                "nombre": nombre,
                "monto_estimado": float(fila["monto"]),
                "periodicidad": "bimestral" if fila.get("es_bimestral") else "mensual",
                "dia_vencimiento": None,
                "categoria": categoria,
                "subcategoria": subcategoria,
                "activo": bool(fila.get("activo")),
                "ultima_actualizacion": ultima_actualizacion,
            },
        )
        migrados += 1
    return migrados


# --- Log (ingresos y gastos) ------------------------------------------------

def mapear_tipo_proporcion(raw_tipo_proporcion, raw_proporcion_jd):
    """Traduce el `tipo_proporcion` del Excel al esquema del laboratorio.

    Devuelve (tipo_proporcion, proporcion_jd, proporcion_pinki).

    - 'dinamica' / vacío / None -> dinamico, sin proporciones (NULL/NULL).
    - '50/50' -> custom, 50/50.
    - '100% JD' -> custom, 100/0.
    - '100% Pinki' -> custom, 0/100.
    - 'custom' con proporcion_jd explícito -> custom, proporcion_jd/(100-jd).
    - 'custom' SIN proporcion_jd (vacío en el Excel) -> fallback a dinamico
      (supuesto documentado en README, no hay forma de recuperar ese dato).
    """
    if raw_tipo_proporcion in (None, "", "dinamica"):
        return "dinamico", None, None
    if raw_tipo_proporcion == "50/50":
        return "custom", 50.0, 50.0
    if raw_tipo_proporcion == "100% JD":
        return "custom", 100.0, 0.0
    if raw_tipo_proporcion == "100% Pinki":
        return "custom", 0.0, 100.0
    if raw_tipo_proporcion == "custom":
        if raw_proporcion_jd is None or raw_proporcion_jd == "":
            return "dinamico", None, None
        proporcion_jd = float(raw_proporcion_jd)
        return "custom", proporcion_jd, 100.0 - proporcion_jd
    raise ValueError(f"tipo_proporcion desconocido en el Excel: {raw_tipo_proporcion!r}")


def migrar_log(conn, filas: list) -> dict:
    """Migra las filas del Log (ingresos y gastos) en el orden del JSON.

    Mantiene `id_sheets_a_id_sqlite` para resolver `cuota_ref`: la primera
    cuota de un gasto se autorreferencia en el Excel (cuota_ref == su propio
    id de Sheets), así que se inserta primero y se actualiza su cuota_ref al
    id nuevo de SQLite después (mismo patrón que `insert_gasto_con_cuotas`
    en db.py). Las cuotas siguientes resuelven cuota_ref contra ese diccionario.
    """
    id_sheets_a_id_sqlite: dict = {}
    n_gastos = 0
    n_ingresos = 0
    n_borrados = 0
    n_cuota_ref_rotos = 0
    total_gastos = 0.0
    total_ingresos = 0.0

    for fila in filas:
        if fila.get("borrado"):
            n_borrados += 1
            continue

        fecha = fila["fecha"]
        monto = float(fila["monto_total"])
        tipo = fila["tipo"]
        sheets_id = fila["id"]

        if tipo == "Ingreso":
            nuevo_id = db.insert_ingreso(
                conn,
                {
                    "fecha": fecha,
                    "monto": monto,
                    "moneda": "ARS",
                    "categoria": fila.get("subcategoria"),
                    "persona": fila.get("pago"),
                    "descripcion_original": fila.get("descripcion"),
                    "origen": "migracion",
                    "confirmado": True,
                },
            )
            id_sheets_a_id_sqlite[sheets_id] = nuevo_id
            n_ingresos += 1
            total_ingresos += monto
            continue

        if tipo != "Gasto":
            raise ValueError(f"tipo de Log desconocido: {tipo!r} en {sheets_id}")

        tipo_proporcion, proporcion_jd, proporcion_pinki = mapear_tipo_proporcion(
            fila.get("tipo_proporcion"), fila.get("proporcion_jd")
        )

        cuota_ref_sheets = fila.get("cuota_ref") or None
        es_autoreferencia = cuota_ref_sheets == sheets_id
        cuota_ref_sqlite = None
        if cuota_ref_sheets and not es_autoreferencia:
            cuota_ref_sqlite = id_sheets_a_id_sqlite.get(cuota_ref_sheets)
            if cuota_ref_sqlite is None:
                n_cuota_ref_rotos += 1
                print(
                    f"AVISO: {sheets_id} referencia cuota_ref={cuota_ref_sheets!r} "
                    "que no fue migrado (probablemente borrado=True); se deja "
                    "cuota_ref=NULL para esta fila."
                )

        nuevo_id = db.insert_gasto(
            conn,
            {
                "fecha": fecha,
                "monto": monto,
                "moneda": "ARS",
                "categoria": fila.get("categoria"),
                "subcategoria": fila.get("subcategoria"),
                "medio_pago": fila.get("medio_pago"),
                "tarjeta_id": fila.get("tarjeta") or None,
                "pagado_por": fila.get("pago") or "Común",
                "tipo_proporcion": tipo_proporcion,
                "proporcion_jd": proporcion_jd,
                "proporcion_pinki": proporcion_pinki,
                "descripcion_original": fila.get("descripcion"),
                "origen": "migracion",
                "confirmado": True,
                "cuotas_total": int(fila.get("cuotas_total") or 1),
                "cuota_nro": int(fila.get("cuota_nro") or 1),
                "cuota_ref": cuota_ref_sqlite,
            },
        )

        if es_autoreferencia:
            conn.execute("UPDATE gastos SET cuota_ref = ? WHERE id = ?", (nuevo_id, nuevo_id))
            conn.commit()

        id_sheets_a_id_sqlite[sheets_id] = nuevo_id
        n_gastos += 1
        total_gastos += monto

    return {
        "n_gastos": n_gastos,
        "n_ingresos": n_ingresos,
        "n_borrados": n_borrados,
        "n_cuota_ref_rotos": n_cuota_ref_rotos,
        "total_gastos": total_gastos,
        "total_ingresos": total_ingresos,
    }


# --- Inventario de bienes ------------------------------------------------

def _convertir_fecha_bien(valor):
    """Convierte `fecha_compra` a ISO. Acepta string ISO ya convertido (caso
    real de `inventario_raw.json`) o serial de Excel (fallback documentado
    en README para el caso en que el parseo previo no lo hubiera convertido).
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor
    return (date(1899, 12, 30) + timedelta(days=int(valor))).isoformat()


def _armar_notas_inventario(fila: dict) -> str:
    cotizacion = fila.get("cotizacion_usd_compra")
    precio_usd = fila.get("precio_usd_compra")
    proporcion_jd = fila.get("proporcion_jd")
    precio_venta = fila.get("precio_venta_estimado_usd")
    estado = fila.get("estado")

    def _fmt(valor, sufijo=""):
        if valor is None:
            return "N/D"
        if isinstance(valor, float):
            return f"{round(valor, 2)}{sufijo}"
        return f"{valor}{sufijo}"

    return (
        f"Cotización USD compra: {_fmt(cotizacion)} | "
        f"Precio USD compra: {_fmt(precio_usd)} | "
        f"Proporción JD: {_fmt(proporcion_jd, '%')} | "
        f"Precio venta estimado USD: {_fmt(precio_venta)} | "
        f"Estado: {_fmt(estado)}"
    )


def migrar_inventario_bienes(conn, filas: list) -> int:
    """Migra `inventario_bienes`, idempotente por clave natural (sin `origen`).

    Misma estrategia que `migrar_gastos_fijos`: clave natural (nombre,
    categoria, fecha_adquisicion), borrado + reinserción por fila.
    """
    migrados = 0
    for fila in filas:
        if fila.get("borrado"):
            continue

        nombre = fila["descripcion"]
        categoria = fila.get("categoria")
        fecha = _convertir_fecha_bien(fila.get("fecha_compra"))

        conn.execute(
            "DELETE FROM inventario_bienes WHERE nombre = ? AND categoria IS ? "
            "AND fecha_adquisicion IS ?",
            (nombre, categoria, fecha),
        )
        db.insert_inventario_bien(
            conn,
            {
                "nombre": nombre,
                "categoria": categoria,
                "valor_estimado": fila.get("precio_ars"),
                "fecha_adquisicion": fecha,
                "notas": _armar_notas_inventario(fila),
            },
        )
        migrados += 1
    return migrados


# --- Orquestación ------------------------------------------------------

def migrar_todo(conn, finanzas_raw: dict, inventario_raw: dict) -> dict:
    """Corre la migración completa en el orden requerido por el brief:
    tarjetas -> categorías -> gastos_fijos -> Log -> inventario_bienes.

    Idempotente: gastos/ingresos se limpian por `origen='migracion'` antes de
    reinsertar; gastos_fijos/inventario_bienes usan clave natural por fila
    (ver README, no tienen columna `origen`); tarjetas/categorías ya son
    idempotentes por PK / `crear_categoria_si_no_existe`.
    """
    n_tarjetas = migrar_tarjetas(conn, finanzas_raw.get("Tarjetas", []))
    n_categorias = migrar_categorias(conn, finanzas_raw.get("Categorías", []))
    n_gastos_fijos = migrar_gastos_fijos(conn, finanzas_raw.get("GastosFijos", []))

    # Limpieza previa de gastos/ingresos migrados, para poder reinsertar todo
    # desde cero sin duplicar. Se desactivan las FK momentáneamente porque
    # `gastos.cuota_ref` referencia a `gastos.id`: al borrar de a un único
    # DELETE todas las filas de origen='migracion' (incluidas cadenas de
    # cuotas completas), no queremos que SQLite se queje de una fila hija
    # que todavía "ve" a su padre borrado dentro del mismo statement.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM gastos WHERE origen = 'migracion'")
    conn.execute("DELETE FROM ingresos WHERE origen = 'migracion'")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")

    stats_log = migrar_log(conn, finanzas_raw.get("Log", []))
    n_inventario = migrar_inventario_bienes(conn, inventario_raw.get("Inventario", []))

    return {
        "tarjetas_nuevas": n_tarjetas,
        "categorias_procesadas": n_categorias,
        "gastos_fijos_migrados": n_gastos_fijos,
        "gastos_migrados": stats_log["n_gastos"],
        "ingresos_migrados": stats_log["n_ingresos"],
        "inventario_bienes_migrados": n_inventario,
        "filas_borrado_omitidas": stats_log["n_borrados"],
        "cuota_ref_rotos": stats_log["n_cuota_ref_rotos"],
        "total_gastos_ars": stats_log["total_gastos"],
        "total_ingresos_ars": stats_log["total_ingresos"],
    }


def _imprimir_resumen(resumen: dict, tarjetas_total: int, categorias_total: int) -> None:
    print("=== Resumen de migración de datos reales de LIFE ===")
    print(f"Tarjetas:        {resumen['tarjetas_nuevas']} nuevas insertadas (total en tabla: {tarjetas_total})")
    print(f"Categorías:      {resumen['categorias_procesadas']} procesadas (total en tabla: {categorias_total})")
    print(f"Gastos fijos:    {resumen['gastos_fijos_migrados']} migrados")
    print(f"Ingresos:        {resumen['ingresos_migrados']} migrados")
    print(f"Gastos:          {resumen['gastos_migrados']} migrados")
    print(f"Inventario:      {resumen['inventario_bienes_migrados']} bienes migrados")
    print(f"Filas 'borrado' omitidas del Log: {resumen['filas_borrado_omitidas']}")
    print(f"Referencias cuota_ref rotas (dejadas en NULL): {resumen['cuota_ref_rotos']}")
    print("--- Sanity check de plata (cruzar contra el Excel original) ---")
    print(f"Total ARS de gastos migrados:   {resumen['total_gastos_ars']:,.2f}")
    print(f"Total ARS de ingresos migrados: {resumen['total_ingresos_ars']:,.2f}")


def main() -> None:
    conn = db.get_connection()
    db.init_db(conn)

    finanzas_raw = _cargar_json(FINANZAS_PATH)
    inventario_raw = _cargar_json(INVENTARIO_PATH)

    resumen = migrar_todo(conn, finanzas_raw, inventario_raw)

    tarjetas_total = len(db.get_tarjetas(conn))
    categorias_total = len(db.get_categorias(conn))
    conn.close()

    _imprimir_resumen(resumen, tarjetas_total, categorias_total)


if __name__ == "__main__":
    main()
