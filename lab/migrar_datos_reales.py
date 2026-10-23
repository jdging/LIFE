"""Migración de datos reales de LIFE (Finanzas + Inventario) desde Sheets.

Lee `finanzas_raw.json` e `inventario_raw.json` (export real de Juan, ya
parseado por el coordinador) y los vuelca en la base SQLite del laboratorio
usando el esquema de `db.py`, sin modificarlo. Ver README.md para el detalle
completo del mapeo de campos y las decisiones tomadas.

Uso: `python3 migrar_datos_reales.py` desde este workdir.

Backfill legacy de inventario (t_0e38e74e, hallazgo 1 del revisor
46d4f3d5), para bases donde `inventario_bienes` ya fue migrado con el
código viejo: `python3 migrar_datos_reales.py --backfill-legacy` (dry-run
por default, imprime el resumen sin escribir nada) o
`python3 migrar_datos_reales.py --backfill-legacy --apply` para aplicar los
cambios de verdad. Ver `backfill_inventario_legacy`.
"""

import argparse
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
    Mapea también `responsable` ('Común'/'JD'/'Pinki', tal cual viene del
    Excel, sin normalizar), `tipo_proporcion`, `proporcion_jd` y `medio_pago`
    (ver README: antes de esto quedaban todos mezclados sin distinción).

    Para responsable 'JD'/'Pinki' el reparto es implícito (ver
    `db.resolve_fixed_split`): un fijo personal no admite `tipo_proporcion`/
    `proporcion_jd` explícitos, aunque el Excel los traiga seteados (quedan
    redundantes del 100/0 que ya implica el responsable), así que no se
    reenvían para esos casos.
    """
    migrados = 0
    for fila in filas:
        nombre = fila["descripcion"]
        categoria = fila.get("categoria")
        subcategoria = fila.get("subcategoria")
        ultima_actualizacion = fila.get("vigente_desde")
        responsable = fila.get("responsable")
        es_personal = responsable in ("JD", "Pinki")

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
                "responsable": responsable,
                "tipo_proporcion": None if es_personal else fila.get("tipo_proporcion"),
                "proporcion_jd": None if es_personal else fila.get("proporcion_jd"),
                "medio_pago": fila.get("medio_pago"),
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


def mapear_saldado(raw_saldado):
    """Traduce el campo `saldado` del Excel al esquema del laboratorio.

    En el Excel, `saldado` es una fecha ISO (ej. "2026-04-29") si ese gasto
    específico ya fue saldado/compensado entre JD y Pinki, o `None`/`False`/
    vacío si sigue pendiente. Cualquier valor "truthy" que no sea una fecha
    válida se trata como error explícito, para no esconder datos raros del
    Excel silenciosamente.
    """
    if not raw_saldado:
        return None
    if not isinstance(raw_saldado, str):
        raise ValueError(f"saldado con tipo inesperado en el Excel: {raw_saldado!r}")
    return raw_saldado


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
                "saldado": mapear_saldado(fila.get("saldado")),
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
    """Reconstruye el bloque de texto que el migrador VIEJO (anterior a
    t_0e38e74e, hallazgo 1 del revisor 46d4f3d5) escribía en `notas` en vez
    de columnas estructuradas, pisando por completo la nota real.

    Ya no se usa para migrar de cero (ver `migrar_inventario_bienes`, que
    ahora llena columnas): queda solo como firma para que
    `backfill_inventario_legacy` reconozca, en una base ya migrada con el
    código viejo, qué filas todavía tienen ese bloque sin tocar y puedan
    recuperar la nota real + los datos estructurados desde `inventario_raw`.
    """
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


INVENTARIO_COLUMNAS_LEGACY = (
    "precio_ars", "cotizacion_usd_compra", "precio_usd_compra",
    "proporcion_jd", "precio_venta_estimado_usd", "estado",
)


def migrar_inventario_bienes(conn, filas: list) -> int:
    """Migra `inventario_bienes`, idempotente por clave natural (sin `origen`).

    Misma estrategia que `migrar_gastos_fijos`: clave natural (nombre,
    categoria, fecha_adquisicion), borrado + reinserción por fila.

    Paridad financiera con el legacy (t_0e38e74e, corrección del hallazgo 1
    del revisor 46d4f3d5): `precio_ars`, `cotizacion_usd_compra`,
    `precio_usd_compra`, `proporcion_jd`, `precio_venta_estimado_usd` y
    `estado` se escriben en sus columnas estructuradas, no solo en `notas`.
    `notas` queda con la nota real de `inventario_raw` únicamente — ya no
    con el bloque generado por `_armar_notas_inventario` (eso era lo que
    pisaba la nota real por completo en el migrador viejo).
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
        bien = {
            "nombre": nombre,
            "categoria": categoria,
            "valor_estimado": fila.get("precio_ars"),
            "fecha_adquisicion": fecha,
            "notas": fila.get("notas"),
        }
        for columna in INVENTARIO_COLUMNAS_LEGACY:
            bien[columna] = fila.get(columna)
        db.insert_inventario_bien(conn, bien)
        migrados += 1
    return migrados


def backfill_inventario_legacy(conn, inventario_raw: dict) -> dict:
    """Completa paridad financiera retroactiva en bases donde
    `inventario_bienes` ya fue migrado con el migrador VIEJO (antes de
    t_0e38e74e, hallazgo 1 del revisor 46d4f3d5): esas filas solo tienen la
    cotización/USD/reparto/reventa/estado como texto libre dentro de
    `notas` (ver `_armar_notas_inventario`), nunca en columnas estructuradas.

    No borra ni reinserta nada — solo hace `UPDATE` columna por columna.
    Pensada para correr una sola vez sobre la base real ya en producción,
    pero es segura de correr más veces (ver abajo):

      - Emparejamiento por identidad: (nombre == descripcion,
        fecha_adquisicion == fecha_compra convertida, categoria ==
        categoria). Sin match o con más de un bien para la misma clave: se
        cuenta en el resumen y NO se toca nada (ambigüedad no se resuelve
        sola) — ver hallazgo 1 del revisor fc195491 (match por nombre+fecha
        sin categoría podía emparejar con el bien equivocado).
      - Procedencia (decisión del coordinador, hallazgos 1 y 2 del revisor
        fc195491): además del emparejamiento por identidad, un bien SOLO es
        elegible si su `notas` actual es EXACTAMENTE el bloque que
        `_armar_notas_inventario` genera para esta misma fila del raw. Esa
        es la única prueba de que el bien nunca fue tocado desde la web (la
        web nunca escribe ese bloque) y de que los valores que el bloque
        encierra (cotización, USD de compra, reparto, reventa, estado)
        coinciden con los del raw actual. Si la nota fue editada, limpiada
        por un backfill anterior, o el raw tiene valores distintos a los
        que el bloque encierra, NO es elegible: se omite por completo (ni
        columnas ni notas) y se cuenta en
        `bienes_sin_procedencia_legacy`.
      - Procedencia financiera (hallazgo 1 del revisor e54e9da9): la nota
        legacy intacta no prueba por sí sola que `valor_estimado` siga
        siendo el `precio_ars` original — el formulario web permite editar
        únicamente el valor estimado y reenviar la nota legacy sin cambios.
        Por eso, además de la nota exacta, se exige que
        `bien["valor_estimado"]` coincida con `fila["precio_ars"]` (con
        tolerancia 0,01, por redondeos de punto flotante). Si no coincide,
        el bien no es elegible: se omite por completo y se cuenta en
        `bienes_editados_en_web`.
      - Para cada bien elegible, solo escribe en las columnas de
        `INVENTARIO_COLUMNAS_LEGACY` que están en NULL en la base — nunca
        pisa un valor ya cargado por la web (el chequeo es `IS NULL` sobre
        la fila actual, no sobre el valor nuevo: un `0` cargado por la web
        para esa columna no se toca). Después reemplaza `notas` por la nota
        real de `inventario_raw` (o `NULL` si tampoco había), limpiando el
        bloque para que un bien ya procesado nunca vuelva a ser elegible.
      - Idempotente y respeta vaciados posteriores desde la web: una vez
        limpiado el bloque, `notas` ya no coincide con
        `_armar_notas_inventario(fila)` en ninguna corrida futura, así que
        el bien deja de ser elegible para siempre — incluso si la web vació
        después alguna de las columnas ya completadas (no se repueblan).

    No hace `commit()`: el caller decide (dry-run = rollback, --apply =
    commit), igual que el resto de operaciones multi-fila sensibles de este
    módulo.

    Devuelve un resumen:
      {'bienes_actualizados', 'campos_completados' (dict columna->cantidad),
       'notas_limpiadas', 'bienes_sin_match', 'bienes_con_match_ambiguo',
       'bienes_sin_procedencia_legacy', 'bienes_editados_en_web'}.
    """
    existentes = db.get_inventario_bienes(conn, incluir_borrados=True)
    por_clave: dict = {}
    for row in existentes:
        clave = (row["nombre"], row["fecha_adquisicion"], row["categoria"])
        por_clave.setdefault(clave, []).append(row)

    resumen = {
        "bienes_actualizados": 0,
        "campos_completados": {columna: 0 for columna in INVENTARIO_COLUMNAS_LEGACY},
        "notas_limpiadas": 0,
        "bienes_sin_match": 0,
        "bienes_con_match_ambiguo": 0,
        "bienes_sin_procedencia_legacy": 0,
        "bienes_editados_en_web": 0,
    }

    for fila in inventario_raw.get("Inventario", []):
        if fila.get("borrado"):
            continue

        nombre = fila["descripcion"]
        fecha = _convertir_fecha_bien(fila.get("fecha_compra"))
        categoria = fila.get("categoria")
        candidatos = por_clave.get((nombre, fecha, categoria), [])

        if not candidatos:
            resumen["bienes_sin_match"] += 1
            continue
        if len(candidatos) > 1:
            resumen["bienes_con_match_ambiguo"] += 1
            continue

        bien = candidatos[0]

        if bien["notas"] != _armar_notas_inventario(fila):
            resumen["bienes_sin_procedencia_legacy"] += 1
            continue

        precio_ars_raw = fila.get("precio_ars")
        valor_estimado = bien["valor_estimado"]
        if (
            precio_ars_raw is None
            or valor_estimado is None
            or abs(valor_estimado - precio_ars_raw) > 0.01
        ):
            resumen["bienes_editados_en_web"] += 1
            continue

        cambios = {}
        for columna in INVENTARIO_COLUMNAS_LEGACY:
            if bien[columna] is not None:
                continue  # nunca pisa lo ya cargado (incluido un 0 real).
            valor_raw = fila.get(columna)
            if valor_raw is None:
                continue
            cambios[columna] = valor_raw

        nota_real = fila.get("notas")
        if nota_real != bien["notas"]:
            cambios["notas"] = nota_real
            resumen["notas_limpiadas"] += 1

        if not cambios:
            continue

        conn.execute(
            f"UPDATE inventario_bienes SET {', '.join(f'{c} = ?' for c in cambios)} WHERE id = ?",
            (*cambios.values(), bien["id"]),
        )
        resumen["bienes_actualizados"] += 1
        for columna in cambios:
            if columna in resumen["campos_completados"]:
                resumen["campos_completados"][columna] += 1

    return resumen


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


def _imprimir_resumen_backfill(resumen: dict, aplicado: bool) -> None:
    encabezado = "aplicado" if aplicado else "DRY-RUN (nada se escribió; agregá --apply para aplicar)"
    print(f"=== Backfill legacy de inventario_bienes: {encabezado} ===")
    print(f"Bienes actualizados:        {resumen['bienes_actualizados']}")
    for columna, cantidad in resumen["campos_completados"].items():
        print(f"  {columna}: {cantidad} completados")
    print(f"Notas limpiadas (nota real recuperada): {resumen['notas_limpiadas']}")
    print(f"Sin match en inventario_bienes:         {resumen['bienes_sin_match']}")
    print(f"Con match ambiguo (no se tocaron):      {resumen['bienes_con_match_ambiguo']}")
    print(f"Sin procedencia legacy (nota editada/vaciada o raw distinto, no se tocaron): {resumen['bienes_sin_procedencia_legacy']}")
    print(f"Editados en la web (valor_estimado != precio_ars del raw, no se tocaron): {resumen['bienes_editados_en_web']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra datos reales de LIFE (Finanzas + Inventario) a SQLite."
    )
    parser.add_argument(
        "--backfill-legacy", action="store_true",
        help=(
            "En vez de migrar todo de cero, completa paridad financiera legacy "
            "de inventario_bienes ya migrados con el código viejo (ver "
            "backfill_inventario_legacy)."
        ),
    )
    parser.add_argument(
        "--apply", action="store_true",
        help=(
            "Solo junto con --backfill-legacy: aplica los cambios de verdad. "
            "Sin esta flag, --backfill-legacy corre en modo dry-run (no escribe "
            "nada) e imprime el resumen igual."
        ),
    )
    args = parser.parse_args()
    if args.apply and not args.backfill_legacy:
        parser.error("--apply solo tiene efecto junto con --backfill-legacy.")

    conn = db.get_connection()
    db.init_db(conn)

    if args.backfill_legacy:
        inventario_raw = _cargar_json(INVENTARIO_PATH)
        resumen = backfill_inventario_legacy(conn, inventario_raw)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        conn.close()
        _imprimir_resumen_backfill(resumen, aplicado=args.apply)
        return

    finanzas_raw = _cargar_json(FINANZAS_PATH)
    inventario_raw = _cargar_json(INVENTARIO_PATH)

    resumen = migrar_todo(conn, finanzas_raw, inventario_raw)

    tarjetas_total = len(db.get_tarjetas(conn))
    categorias_total = len(db.get_categorias(conn))
    conn.close()

    _imprimir_resumen(resumen, tarjetas_total, categorias_total)


if __name__ == "__main__":
    main()
