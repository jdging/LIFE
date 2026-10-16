"""Capa de acceso a SQLite para el bot Lasso (Fases 1, 3 y Finanzas completo).

Copia de trabajo de `reference/db.py` (t_65096083), extendida con:
    - Soft delete de `gastos` (`deleted_at`/`deleted_by` + tabla `auditoria`),
      aplicando la migración diseñada en `reference/migracion_soft_delete.sql`.
    - Edición de `ingresos` (`actualizar_ingreso`).
    - Versionado real de `gastos_fijos` (`vigente_desde` + `crear_version_fijo`
      + `monto_fijo_vigente_en` + `get_fijos_vigentes`), reemplazando el
      UPDATE in-place de `actualizar_monto_fijo` (bug reportado por CPO,
      t_85b8502b). Permite varias versiones con igual `vigente_desde` en
      una serie (corregir un fijo más de una vez el mismo día es normal);
      la vigente para una fecha es la de mayor `(vigente_desde, id)` — ver
      README "Versionado de fijos: varias versiones el mismo día".

Tablas (esquema reconciliado con LIFE-lab-propuesta.md sección 3):
    - gastos: registros de gastos ("Log" en el documento aprobado). Extendido
      con `tarjeta_id`, `tipo_proporcion`, `proporcion_jd`, `proporcion_pinki`
      (tarjetas/reparto), `cuotas_total`, `cuota_nro`, `cuota_ref` (cuotas,
      ver README sección "Cuotas") y `deleted_at`/`deleted_by` (soft delete,
      ver README sección "Soft delete de gastos").
    - auditoria: rastro genérico de alta/baja/edición sobre cualquier tabla
      (hoy solo usada por `eliminar_gasto_logico`), ver README.
    - tarjetas: catálogo de tarjetas (crédito/débito), portado de la hoja
      `Tarjetas` del sistema real (ver README).
    - categorias: catálogo dinámico de categorías/subcategorías (Gasto /
      Ingreso / Inversión), sembrado desde `seed_categorias.py` pero
      extensible en caliente vía `crear_categoria_si_no_existe` (ver README).
    - gastos_fijos: catálogo de gastos recurrentes (alquiler, expensas, etc.),
      portado de la hoja `GastosFijos` del sistema real. Versionado real por
      `vigente_desde` desde esta tarea (ver README sección "Versionado de
      fijos").
    - ingresos: movimientos de ingreso (Salario/Extra/Freelance/Otro),
      tabla hermana de `gastos` — separada porque en el laboratorio `gastos`
      ya es su propia tabla (ver README).
    - inversiones: movimientos de inversión (Plazo fijo/FCI/Dólar-MEP/
      Crypto/Otro), misma lógica que `ingresos`.
    - estado_conversacional: estado del flujo multi-turno por chat_id.
    - recetas / receta_ingredientes: recetario de ejemplo (Fase 3).
    - inventario_bienes: bienes del hogar (Fase 3, sin lógica de negocio
      todavía — solo CRUD básico, ver README).
    - inventario_cocina: stock de ingredientes disponibles (Fase 3).
    - lista_compras: items pendientes de comprar (Fase 3).

Principio no negociable: `insert_gasto`, `insert_ingreso` e `insert_inversion`
rechazan cualquier intento de insertar un registro que no venga marcado como
`confirmado=True`. La confirmación explícita del usuario se resuelve en
`conversation.py`; esta capa la vuelve a exigir como segunda barrera.
"""

import json
import sqlite3
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional

from validaciones import validar_expense, validar_gasto_fijo, validar_ingreso

DEFAULT_DB_PATH = str(Path(__file__).parent / "data" / "lasso.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'ARS',
    categoria TEXT,
    subcategoria TEXT,
    medio_pago TEXT,
    pagado_por TEXT NOT NULL DEFAULT 'Común',
    descripcion_original TEXT,
    origen TEXT NOT NULL DEFAULT 'texto',
    confirmado INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    -- chat_id no está en el esquema aprobado (LIFE-lab-propuesta.md sección 3),
    -- se agrega para poder filtrar gastos por conversación de Telegram; ver README.
    chat_id TEXT
);

CREATE TABLE IF NOT EXISTS estado_conversacional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id TEXT NOT NULL UNIQUE,
    usuario TEXT,
    intent_detectado TEXT NOT NULL DEFAULT 'gasto',
    payload_parcial TEXT,
    campo_pendiente TEXT,
    mensaje_original TEXT,
    estado TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    porciones INTEGER NOT NULL DEFAULT 1,
    tiempo_preparacion_min INTEGER,
    notas TEXT,
    activa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS receta_ingredientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receta_id INTEGER NOT NULL REFERENCES recetas(id),
    ingrediente_nombre TEXT NOT NULL,
    cantidad REAL,
    unidad TEXT
);

CREATE TABLE IF NOT EXISTS inventario_bienes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    categoria TEXT,
    ubicacion TEXT,
    valor_estimado REAL,
    fecha_adquisicion TEXT,
    notas TEXT
);

CREATE TABLE IF NOT EXISTS inventario_cocina (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingrediente_nombre TEXT NOT NULL,
    cantidad_actual REAL NOT NULL DEFAULT 0,
    unidad TEXT,
    ubicacion TEXT,
    fecha_vencimiento TEXT,
    ultima_actualizacion TEXT NOT NULL,
    actualizado_por TEXT
);

CREATE TABLE IF NOT EXISTS lista_compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_nombre TEXT NOT NULL,
    cantidad_deseada REAL,
    unidad TEXT,
    prioridad TEXT,
    agregado_por TEXT,
    comprado INTEGER NOT NULL DEFAULT 0,
    fecha_agregado TEXT NOT NULL,
    fecha_comprado TEXT
);

-- Catálogo de tarjetas (portado de la hoja `Tarjetas` del sistema real).
-- Extensión deliberada de esta tarea: `titular` acepta 'Común' además de
-- 'JD'/'Pinki', para modelar tarjetas de la cuenta conjunta (ver README).
CREATE TABLE IF NOT EXISTS tarjetas (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL,
    banco TEXT,
    titular TEXT NOT NULL,
    dia_cierre INTEGER,
    dia_vencimiento INTEGER,
    es_default_dinamico INTEGER NOT NULL DEFAULT 0,
    uso_compartido INTEGER NOT NULL DEFAULT 0
);

-- Catálogo dinámico de categorías (portado de la hoja `Categorías`).
-- La combinación (tipo, categoria, subcategoria) se trata como clave lógica
-- de idempotencia a nivel aplicación (ver `crear_categoria_si_no_existe`) en
-- vez de UNIQUE de SQL, porque SQLite no trata NULLs como iguales en un
-- UNIQUE compuesto y varias categorías (Ingreso/Inversión) no tienen
-- subcategoría.
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    categoria TEXT NOT NULL,
    subcategoria TEXT,
    creada_por TEXT,
    creada_en TEXT NOT NULL
);

-- Gastos recurrentes (portado de la hoja `GastosFijos`).
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    monto_estimado REAL NOT NULL,
    periodicidad TEXT NOT NULL,
    dia_vencimiento INTEGER,
    categoria TEXT,
    subcategoria TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    ultima_actualizacion TEXT NOT NULL,
    responsable TEXT,
    tipo_proporcion TEXT,
    proporcion_jd REAL,
    medio_pago TEXT
);

-- Ingresos (tabla hermana de `gastos`, separada porque en este laboratorio
-- `gastos` ya es su propia tabla en vez de un "Log" único con columna tipo).
CREATE TABLE IF NOT EXISTS ingresos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'ARS',
    categoria TEXT NOT NULL,
    persona TEXT NOT NULL,
    descripcion_original TEXT,
    origen TEXT NOT NULL DEFAULT 'texto',
    confirmado INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Inversiones (misma lógica que `ingresos`; `persona` es nullable porque
-- una inversión puede ser conjunta).
CREATE TABLE IF NOT EXISTS inversiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'ARS',
    categoria TEXT NOT NULL,
    persona TEXT,
    descripcion_original TEXT,
    origen TEXT NOT NULL DEFAULT 'texto',
    confirmado INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Auditoría genérica de alta/baja/edición sobre cualquier tabla (hoy solo
-- `gastos`, vía `eliminar_gasto_logico`). Ver
-- `reference/migracion_soft_delete.sql` sección 2 y README sección
-- "Soft delete de gastos".
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla TEXT NOT NULL,
    fila_id INTEGER NOT NULL,
    accion TEXT NOT NULL,
    actor TEXT,
    antes_json TEXT,
    despues_json TEXT,
    creado_en TEXT NOT NULL
);
"""


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrar_columnas_gastos(conn: sqlite3.Connection) -> None:
    """Agrega a `gastos` las columnas de tarjetas/reparto/soft-delete si faltan.

    Usa ALTER TABLE ADD COLUMN en vez de recrear la tabla para no perder
    datos existentes en bases ya inicializadas (ver README).
    """
    existentes = _column_names(conn, "gastos")
    columnas_nuevas = (
        ("tarjeta_id", "TEXT REFERENCES tarjetas(id)"),
        ("tipo_proporcion", "TEXT NOT NULL DEFAULT 'dinamico'"),
        ("proporcion_jd", "REAL"),
        ("proporcion_pinki", "REAL"),
        ("cuotas_total", "INTEGER NOT NULL DEFAULT 1"),
        ("cuota_nro", "INTEGER NOT NULL DEFAULT 1"),
        ("cuota_ref", "INTEGER REFERENCES gastos(id)"),
        # Fecha ISO en la que ese gasto individual fue saldado/compensado
        # entre JD y Pinki, o NULL si sigue pendiente (ver README, mapeado
        # desde la columna `saldado` del Log real de Sheets).
        ("saldado", "TEXT"),
        # Marcador de procedencia retrocompatible (default 0 = fail-closed):
        # un gasto con origen distinto de 'migracion' solo se considera real
        # (y aparece en el dashboard) si fue validado manualmente y marcado
        # es_real=1. Los gastos ya migrados (origen='migracion') no lo
        # necesitan — ver README "Cómo se distingue un gasto real de uno de
        # ejemplo".
        ("es_real", "INTEGER NOT NULL DEFAULT 0"),
        # Soft delete (migración aplicada en esta tarea, ver
        # `reference/migracion_soft_delete.sql`): fecha ISO del borrado
        # lógico y quién lo ejecutó, o NULL si el gasto sigue activo.
        ("deleted_at", "TEXT"),
        ("deleted_by", "TEXT"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE gastos ADD COLUMN {columna} {definicion}")
    conn.commit()


def _migrar_columnas_tarjetas(conn: sqlite3.Connection) -> None:
    """Agrega a `tarjetas` las columnas nuevas si faltan (ver README).

    Mismo patrón que `_migrar_columnas_gastos`: ALTER TABLE ADD COLUMN en
    vez de recrear la tabla, para no perder datos en bases ya inicializadas.
    """
    existentes = _column_names(conn, "tarjetas")
    columnas_nuevas = (
        ("uso_compartido", "INTEGER NOT NULL DEFAULT 0"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE tarjetas ADD COLUMN {columna} {definicion}")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _migrar_columnas_gastos(conn)
    _migrar_columnas_tarjetas(conn)
    _migrar_columnas_gastos_fijos(conn)
    _migrar_columnas_lista_compras(conn)
    _migrar_columnas_recetas(conn)


def _migrar_columnas_lista_compras(conn: sqlite3.Connection) -> None:
    """Agrega a `lista_compras` el marcador de procedencia si falta.

    Mismo patrón que `_migrar_columnas_gastos`: ALTER TABLE ADD COLUMN
    retrocompatible, default 0 (fail-closed). Los ítems de ejemplo que ya
    existen en la tabla no deben presentarse como reales sin confirmación
    explícita (ver README "Bloqueos de procedencia — compras" y
    `marcar_lista_compras_confirmada`).
    """
    existentes = _column_names(conn, "lista_compras")
    columnas_nuevas = (
        ("es_real", "INTEGER NOT NULL DEFAULT 0"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE lista_compras ADD COLUMN {columna} {definicion}")
    conn.commit()


def _migrar_columnas_recetas(conn: sqlite3.Connection) -> None:
    """Agrega a `recetas` el marcador de procedencia si falta.

    Sin este marcador no hay forma de distinguir, de las recetas sembradas,
    cuáles son reales (esta misma tabla nació documentada como "recetario de
    ejemplo" en el encabezado de este archivo). Default 0 (fail-closed):
    ninguna receta se exporta como real hasta marcarse explícitamente con
    `marcar_receta_real` (ver README "Bloqueos de procedencia — recetas").
    """
    existentes = _column_names(conn, "recetas")
    columnas_nuevas = (
        ("es_real", "INTEGER NOT NULL DEFAULT 0"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE recetas ADD COLUMN {columna} {definicion}")
    conn.commit()


def _migrar_columnas_gastos_fijos(conn: sqlite3.Connection) -> None:
    """Agrega a `gastos_fijos` las columnas de responsable/reparto/versionado
    si faltan.

    Mismo patrón que `_migrar_columnas_gastos`: ALTER TABLE ADD COLUMN en
    vez de recrear la tabla, para no perder datos en bases ya inicializadas.

    `vigente_desde` (agregada en t_85b8502b): fecha ISO 'YYYY-MM-DD' desde la
    que esa FILA (esa versión del gasto fijo) es válida. Para filas
    insertadas antes de esta migración (o por `insert_gasto_fijo` sin el
    campo) se usa `ultima_actualizacion` recortada a fecha como mejor
    aproximación disponible, nunca NULL — una versión sin fecha de vigencia
    no se puede ordenar contra otras versiones (ver `monto_fijo_vigente_en`).

    `fijo_grupo_id` (agregada tras dictamen NO APTO del revisor
    independiente, run 3b184396, hallazgo 4): identidad ESTABLE de una
    serie de versiones de un mismo gasto fijo, separada de `nombre` (que
    puede repetirse entre gastos fijos distintos o cambiar al renombrar) y
    separada del `id` de cada versión individual. Para filas nuevas
    (`insert_gasto_fijo`), `fijo_grupo_id` es el propio `id` de esa primera
    versión (self-reference). Para versiones nuevas (`crear_version_fijo`),
    se hereda el `fijo_grupo_id` de la serie — nunca se recalcula por
    `nombre`.

    Backfill retrocompatible (corregido tras 2da pasada del revisor, run
    3e22f249, hallazgo 1 — la versión anterior de esta migración fusionaba
    silenciosamente filas legacy que compartían `nombre` asignándoles el
    `MIN(id)` de ese nombre como `fijo_grupo_id` común. Eso es INSEGURO:
    bajo el esquema legacy de `reference/db.py`, `actualizar_monto_fijo`
    hacía `UPDATE` in-place, así que nunca había más de una fila por gasto
    fijo real — si dos filas legacy comparten `nombre`, lo más probable es
    que sean dos gastos fijos DISTINTOS que coinciden en nombre por
    casualidad (ej. dos "Internet", uno de casa y otro de oficina), NO dos
    versiones de la misma serie. Fusionarlas mezclaría su histórico de
    forma irreversible y silenciosa.

    Política nueva: cada fila legacy sin `fijo_grupo_id` recibe su PROPIO
    grupo (`fijo_grupo_id = id`) por default — nunca se infiere continuidad
    a partir de `nombre` solo. Si en el futuro se encuentra evidencia
    inequívoca de que dos filas son la misma serie (ej. un campo de
    referencia explícito que hoy no existe en los datos legacy), se puede
    migrar manualmente con un `UPDATE` puntual. Para ayudar a identificar
    esos casos, `detectar_fijos_nombre_duplicado(conn)` lista los `nombre`
    que terminan repartidos en más de un `fijo_grupo_id`, sin fusionar nada
    automáticamente — es solo diagnóstico para revisión manual.

    La migración es idempotente: solo toca filas con `fijo_grupo_id IS
    NULL`, así que correrla una segunda vez (ej. sobre una base que ya la
    tiene aplicada) no reasigna ni duplica nada.
    """
    existentes = _column_names(conn, "gastos_fijos")
    columnas_nuevas = (
        ("responsable", "TEXT"),
        ("tipo_proporcion", "TEXT"),
        ("proporcion_jd", "REAL"),
        ("medio_pago", "TEXT"),
        ("vigente_desde", "TEXT"),
        ("fijo_grupo_id", "INTEGER"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE gastos_fijos ADD COLUMN {columna} {definicion}")
    conn.commit()
    conn.execute(
        "UPDATE gastos_fijos SET vigente_desde = substr(ultima_actualizacion, 1, 10) "
        "WHERE vigente_desde IS NULL"
    )
    conn.execute(
        "UPDATE gastos_fijos SET fijo_grupo_id = id WHERE fijo_grupo_id IS NULL"
    )
    conn.commit()


def detectar_fijos_nombre_duplicado(conn: sqlite3.Connection) -> list:
    """Diagnóstico (NO fusión automática) de `nombre`s de `gastos_fijos` que
    aparecen repartidos en más de un `fijo_grupo_id` (más de una serie).

    Útil tanto para datos legacy migrados (ver `_migrar_columnas_gastos_fijos`,
    que ya NO fusiona por `nombre`) como para altas nuevas: dos gastos fijos
    con el mismo `nombre` son ambiguos para un humano que mire el listado
    ("¿esto es un error de tipeo o son dos gastos fijos distintos que se
    llaman igual?"). Esta función se limita a listar los candidatos — la
    decisión de fusionarlos (con un `UPDATE` manual) queda para quien
    revise el reporte, nunca se infiere sola.

    Devuelve una lista de dicts `{'nombre': str, 'fijo_grupo_ids': [int,
    ...], 'ids': [int, ...]}`, uno por cada `nombre` con más de una serie
    (`fijo_grupo_id` distinto) entre sus filas. Lista vacía si no hay
    ambigüedades.
    """
    rows = conn.execute(
        "SELECT nombre, fijo_grupo_id, id FROM gastos_fijos ORDER BY nombre, fijo_grupo_id, id"
    ).fetchall()

    grupos_por_nombre: dict = {}
    for row in rows:
        grupos = grupos_por_nombre.setdefault(row["nombre"], {})
        grupos.setdefault(row["fijo_grupo_id"], []).append(row["id"])

    candidatos = []
    for nombre, grupos in grupos_por_nombre.items():
        if len(grupos) > 1:
            candidatos.append(
                {
                    "nombre": nombre,
                    "fijo_grupo_ids": sorted(grupos.keys()),
                    "ids": sorted(id_ for ids in grupos.values() for id_ in ids),
                }
            )
    return candidatos


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_gasto_tx(conn: sqlite3.Connection, gasto: dict) -> int:
    """Igual que `insert_gasto`, pero sin `commit()` — para uso interno de
    `insert_gasto` y `insert_gasto_con_cuotas`, que controlan la transacción
    completa (ver nota de atomicidad en `insert_gasto_con_cuotas`).

    Corre `validar_expense(gasto)` antes de tocar la base: es la barrera que
    el revisor independiente (run 3b184396, hallazgo 1) encontró ausente —
    antes se podía insertar `monto<=0`, `categoria=""`, `pagado_por`
    inválido o `cuotas_total<=0` llamando a `insert_gasto` directamente,
    porque solo se chequeaban `confirmado` y las proporciones a mano.
    """
    errores = validar_expense(gasto)
    if errores:
        raise ValueError(f"Gasto inválido: {errores}")

    tipo_proporcion = gasto.get("tipo_proporcion") or "dinamico"
    proporcion_jd = gasto.get("proporcion_jd")
    proporcion_pinki = gasto.get("proporcion_pinki")
    cuotas_total = gasto.get("cuotas_total", 1)
    if cuotas_total is None:
        cuotas_total = 1
    cuota_nro = gasto.get("cuota_nro", 1)
    if cuota_nro is None:
        cuota_nro = 1

    cursor = conn.execute(
        """
        INSERT INTO gastos
            (fecha, monto, moneda, categoria, subcategoria, medio_pago,
             pagado_por, descripcion_original, origen, chat_id, confirmado,
             created_at, tarjeta_id, tipo_proporcion, proporcion_jd,
             proporcion_pinki, cuotas_total, cuota_nro, cuota_ref, saldado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gasto.get("fecha") or _now(),
            gasto["monto"],
            gasto.get("moneda") or "ARS",
            gasto.get("categoria"),
            gasto.get("subcategoria"),
            gasto.get("medio_pago"),
            gasto.get("pagado_por") or "Común",
            gasto.get("descripcion_original"),
            gasto.get("origen") or "texto",
            gasto.get("chat_id"),
            1,
            _now(),
            gasto.get("tarjeta_id"),
            tipo_proporcion,
            proporcion_jd,
            proporcion_pinki,
            cuotas_total,
            cuota_nro,
            gasto.get("cuota_ref"),
            gasto.get("saldado"),
        ),
    )
    return cursor.lastrowid


def insert_gasto(conn: sqlite3.Connection, gasto: dict) -> int:
    """Inserta un gasto. Exige `gasto['confirmado'] is True` y que el payload
    cumpla `validar_expense` (monto>0 finito, categoria, pagado_por,
    tipo_proporcion/proporciones, cuotas_total/cuota_nro) — ver
    `_insert_gasto_tx`. El chequeo de `confirmado` es deliberado y redundante
    con la máquina de estados de `conversation.py`: el bot nunca debe
    escribir en la base sin confirmación explícita del usuario, sin
    excepciones.

    Campos de reparto (retrocompatibles — si no se pasan, un gasto queda
    `tipo_proporcion='dinamico'` sin proporciones explícitas, igual que
    antes de esta extensión):
        - tarjeta_id: FK opcional a `tarjetas`.
        - tipo_proporcion: 'dinamico' (default) o 'custom'.
        - proporcion_jd / proporcion_pinki: sólo válidas (y obligatorias)
          si tipo_proporcion='custom'; deben sumar 100 (±0.01). En modo
          'dinamico' deben venir vacías — el cálculo se hace por fuera.

    Campos de cuotas (retrocompatibles, default = gasto sin cuotas): ver
    `insert_gasto_con_cuotas` para la generación automática de N filas.
        - cuotas_total: default 1, debe ser entero >= 1 (ver `validar_expense`
          — un `2.9` o un `0` se rechazan con `ValueError`, nunca se
          truncan ni se reemplazan en silencio).
        - cuota_nro: default 1.
        - cuota_ref: FK opcional a `gastos.id` (vincula todas las cuotas
          del mismo gasto original); default None.

    Campo de saldado (retrocompatible, default None = pendiente):
        - saldado: fecha ISO ('YYYY-MM-DD') en la que este gasto individual
          fue saldado/compensado entre JD y Pinki, o None si sigue
          pendiente. Ver `calcular_deudas_pendientes`.
    """
    if gasto.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un gasto sin confirmación explícita "
            "(confirmado debe ser True)."
        )
    try:
        gasto_id = _insert_gasto_tx(conn, gasto)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return gasto_id


def get_gastos(
    conn: sqlite3.Connection,
    chat_id: Optional[str] = None,
    incluir_borrados: bool = False,
) -> list:
    """Devuelve gastos ordenados por id.

    Por default excluye los gastos con `deleted_at IS NOT NULL` (soft
    delete, ver `eliminar_gasto_logico`). Pasar `incluir_borrados=True`
    para incluirlos también (p.ej. para una vista de auditoría/papelera).
    """
    condiciones = []
    parametros: list = []
    if chat_id is not None:
        condiciones.append("chat_id = ?")
        parametros.append(chat_id)
    if not incluir_borrados:
        condiciones.append("deleted_at IS NULL")

    where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    rows = conn.execute(f"SELECT * FROM gastos{where} ORDER BY id", parametros).fetchall()
    return [dict(row) for row in rows]


def _sumar_meses(fecha_str: str, meses: int) -> str:
    """Suma `meses` a una fecha 'YYYY-MM-DD' (o con sufijo de hora, se ignora).

    Clampea el día al último día válido del mes destino (ej. 31 de enero +
    1 mes -> 28/29 de febrero), evitando `ValueError` de `date()`.
    """
    import calendar

    year, month, day = (int(p) for p in fecha_str[:10].split("-"))
    indice_mes = (month - 1) + meses
    nuevo_year = year + indice_mes // 12
    nuevo_mes = indice_mes % 12 + 1
    ultimo_dia = calendar.monthrange(nuevo_year, nuevo_mes)[1]
    nuevo_dia = min(day, ultimo_dia)
    return f"{nuevo_year:04d}-{nuevo_mes:02d}-{nuevo_dia:02d}"


def insert_gasto_con_cuotas(conn: sqlite3.Connection, gasto: dict, cuotas_total: int) -> "int | list":
    """Inserta un gasto, expandiéndolo en N filas si tiene cuotas.

    - `cuotas_total` None: se toma como 1 (retrocompatible).
    - `cuotas_total` inválido (no entero, `bool`, o `< 1` — ej. `2.9` o `0`):
      levanta `ValueError` de inmediato, SIN truncar ni reemplazar en
      silencio (hallazgo de revisor independiente, run 3b184396, hallazgo 2).
    - `cuotas_total == 1`: idéntico a `insert_gasto` (devuelve un solo id).
    - `cuotas_total > 1`: inserta `cuotas_total` filas, una por mes
      consecutivo a partir de la fecha del gasto, EN UNA SOLA TRANSACCIÓN:
      si falla cualquier cuota intermedia (validación o error de SQLite), se
      hace `rollback()` de todas las cuotas ya insertadas en esta llamada —
      antes cada cuota hacía su propio `commit()` y una falla a mitad de
      camino dejaba cuotas previas persistidas sin las restantes. `cuota_nro`
      va de 1 a N y `cuota_ref` = id de la primera fila (incluida ella
      misma). El resto de los campos (categoría, tarjeta, tipo_proporcion,
      pagado_por, etc.) se hereda igual en todas las cuotas. Devuelve la
      lista de ids insertados, en orden.

    Redondeo de montos cuando `monto_total` no es divisible exacto por
    `cuotas_total` (condición de QA, run 735a6e21, ver README): se calcula
    `monto_total / cuotas_total` con `Decimal` y se redondea a 2 decimales
    (centavos) con `ROUND_HALF_UP`. Esa cuota redondeada se repite en todas
    las cuotas salvo la ÚLTIMA, que absorbe la diferencia (`monto_total -
    monto_cuota_redondeada * (cuotas_total - 1)`) para que la suma de todas
    las cuotas sea exactamente `monto_total`, nunca unos centavos de más o
    de menos por acumulación de redondeo. Ej.: 100 / 3 -> cuotas 1 y 2 en
    33.33, cuota 3 en 33.34 (suma 100.00). Si `monto_total` es divisible
    exacto (ej. 3000 / 3), la última cuota coincide con las demás, igual que
    antes de este ajuste.
    """
    if cuotas_total is None:
        cuotas_total = 1
    if (
        not isinstance(cuotas_total, int)
        or isinstance(cuotas_total, bool)
        or cuotas_total < 1
    ):
        raise ValueError(
            f"cuotas_total debe ser un entero >= 1 (recibido {cuotas_total!r})."
        )
    if cuotas_total == 1:
        return insert_gasto(conn, gasto)

    if gasto.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un gasto sin confirmación explícita "
            "(confirmado debe ser True)."
        )

    monto_total_dec = Decimal(str(gasto["monto"]))
    monto_cuota_dec = (monto_total_dec / Decimal(cuotas_total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    monto_ultima_cuota_dec = monto_total_dec - monto_cuota_dec * (cuotas_total - 1)
    fecha_base = (gasto.get("fecha") or _now())[:10]

    ids = []
    cuota_ref = None
    try:
        for numero in range(1, cuotas_total + 1):
            es_ultima = numero == cuotas_total
            gasto_cuota = dict(gasto)
            gasto_cuota["monto"] = float(
                monto_ultima_cuota_dec if es_ultima else monto_cuota_dec
            )
            gasto_cuota["fecha"] = _sumar_meses(fecha_base, numero - 1)
            gasto_cuota["cuotas_total"] = cuotas_total
            gasto_cuota["cuota_nro"] = numero
            gasto_cuota["cuota_ref"] = cuota_ref
            nuevo_id = _insert_gasto_tx(conn, gasto_cuota)
            if cuota_ref is None:
                cuota_ref = nuevo_id
                conn.execute(
                    "UPDATE gastos SET cuota_ref = ? WHERE id = ?", (cuota_ref, nuevo_id)
                )
            ids.append(nuevo_id)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return ids


# --- Soft delete de gastos + auditoría --------------------------------------


def eliminar_gasto_logico(conn: sqlite3.Connection, gasto_id: int, actor: str) -> None:
    """Marca `gastos.id = gasto_id` como borrado lógico (soft delete).

    No borra la fila físicamente — solo setea `deleted_at`/`deleted_by` y
    deja rastro en `auditoria` con el snapshot previo de la fila (ver
    `reference/migracion_soft_delete.sql`). Levanta `ValueError` si el
    gasto no existe o ya estaba borrado (no hay doble-borrado silencioso).

    Atomicidad (corrección pedida por revisor independiente, run 3b184396,
    hallazgo 3):
      - El `UPDATE` filtra además por `deleted_at IS NULL` y se verifica
        `cursor.rowcount == 1`. Si otra conexión ya marcó el borrado entre
        nuestro `SELECT` inicial y este `UPDATE` (doble baja concurrente),
        `rowcount` da 0 y se levanta `ValueError` SIN pisar el
        `deleted_by`/`deleted_at` que puso la otra conexión.
      - Si falla el `INSERT` en `auditoria` (o cualquier otro paso después
        del `UPDATE`), se hace `rollback()` explícito antes de propagar la
        excepción — nunca debe quedar un `UPDATE` de baja persistido sin su
        fila de auditoría correspondiente.
    """
    fila = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ningún gasto con id={gasto_id}.")
    if fila["deleted_at"] is not None:
        raise ValueError(f"El gasto id={gasto_id} ya está borrado.")

    snapshot_antes = json.dumps(dict(fila), ensure_ascii=False)
    ahora = _now()

    try:
        cursor = conn.execute(
            "UPDATE gastos SET deleted_at = ?, deleted_by = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (ahora, actor, gasto_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"El gasto id={gasto_id} ya fue borrado por otra operación "
                "concurrente (detectado al aplicar la baja)."
            )
        conn.execute(
            """
            INSERT INTO auditoria (tabla, fila_id, accion, actor, antes_json, despues_json, creado_en)
            VALUES ('gastos', ?, 'baja', ?, ?, NULL, ?)
            """,
            (gasto_id, actor, snapshot_antes, ahora),
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def get_estado(conn: sqlite3.Connection, chat_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM estado_conversacional WHERE telegram_chat_id = ?", (chat_id,)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["payload_parcial"] = (
        json.loads(data["payload_parcial"]) if data["payload_parcial"] else {}
    )
    return data


def set_estado(
    conn: sqlite3.Connection,
    chat_id: str,
    estado: str,
    campo_pendiente: Optional[str] = None,
    payload_parcial: Optional[dict] = None,
    mensaje_original: Optional[str] = None,
    usuario: Optional[str] = None,
    intent_detectado: str = "gasto",
) -> None:
    """Crea o actualiza la fila de estado conversacional de `chat_id`.

    `intent_detectado` queda fijo en "gasto" por ahora (Fase 1 sólo
    implementa ese intent; receta/inventario/compra quedan para fases
    futuras, ver LIFE-lab-propuesta.md sección 3).
    """
    conn.execute(
        """
        INSERT INTO estado_conversacional
            (telegram_chat_id, usuario, intent_detectado, payload_parcial,
             campo_pendiente, mensaje_original, estado, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_chat_id) DO UPDATE SET
            usuario = excluded.usuario,
            intent_detectado = excluded.intent_detectado,
            payload_parcial = excluded.payload_parcial,
            campo_pendiente = excluded.campo_pendiente,
            mensaje_original = excluded.mensaje_original,
            estado = excluded.estado,
            updated_at = excluded.updated_at
        """,
        (
            chat_id,
            usuario,
            intent_detectado,
            json.dumps(payload_parcial or {}, ensure_ascii=False),
            campo_pendiente,
            mensaje_original,
            estado,
            _now(),
            _now(),
        ),
    )
    conn.commit()


def clear_estado(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute(
        "DELETE FROM estado_conversacional WHERE telegram_chat_id = ?", (chat_id,)
    )
    conn.commit()


# --- Recetas -----------------------------------------------------------


def insert_receta(conn: sqlite3.Connection, receta: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO recetas (nombre, porciones, tiempo_preparacion_min, notas, activa)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            receta["nombre"],
            receta.get("porciones") or 1,
            receta.get("tiempo_preparacion_min"),
            receta.get("notas"),
            1 if receta.get("activa", True) else 0,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recetas(conn: sqlite3.Connection, activa: Optional[bool] = None) -> list:
    if activa is not None:
        rows = conn.execute(
            "SELECT * FROM recetas WHERE activa = ? ORDER BY id", (1 if activa else 0,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM recetas ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def insert_receta_ingrediente(conn: sqlite3.Connection, ingrediente: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO receta_ingredientes (receta_id, ingrediente_nombre, cantidad, unidad)
        VALUES (?, ?, ?, ?)
        """,
        (
            ingrediente["receta_id"],
            ingrediente["ingrediente_nombre"],
            ingrediente.get("cantidad"),
            ingrediente.get("unidad"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_receta_ingredientes(conn: sqlite3.Connection, receta_id: int) -> list:
    rows = conn.execute(
        "SELECT * FROM receta_ingredientes WHERE receta_id = ? ORDER BY id",
        (receta_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def marcar_receta_real(conn: sqlite3.Connection, receta_id: int) -> None:
    """Marca `es_real=1` en la receta `receta_id`, tras validación manual.

    Requiere el id explícito porque, a diferencia de `lista_compras`, no hay
    campos observables que identifiquen sin ambigüedad una receta real (ver
    README "Bloqueos de procedencia — recetas"). Este helper no decide por sí
    solo qué recetas son reales: solo aplica una decisión ya tomada afuera,
    por eso valida que el id exista antes de tocar nada.
    """
    fila = conn.execute("SELECT id FROM recetas WHERE id = ?", (receta_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ninguna receta con id={receta_id}.")
    conn.execute("UPDATE recetas SET es_real = 1 WHERE id = ?", (receta_id,))
    conn.commit()


# --- Inventario de bienes ------------------------------------------------


def insert_inventario_bien(conn: sqlite3.Connection, bien: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO inventario_bienes
            (nombre, categoria, ubicacion, valor_estimado, fecha_adquisicion, notas)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            bien["nombre"],
            bien.get("categoria"),
            bien.get("ubicacion"),
            bien.get("valor_estimado"),
            bien.get("fecha_adquisicion"),
            bien.get("notas"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_inventario_bienes(conn: sqlite3.Connection, categoria: Optional[str] = None) -> list:
    if categoria is not None:
        rows = conn.execute(
            "SELECT * FROM inventario_bienes WHERE categoria = ? ORDER BY id",
            (categoria,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM inventario_bienes ORDER BY id").fetchall()
    return [dict(row) for row in rows]


# --- Inventario de cocina ------------------------------------------------


def insert_inventario_cocina(conn: sqlite3.Connection, item: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO inventario_cocina
            (ingrediente_nombre, cantidad_actual, unidad, ubicacion,
             fecha_vencimiento, ultima_actualizacion, actualizado_por)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["ingrediente_nombre"],
            item.get("cantidad_actual") or 0,
            item.get("unidad"),
            item.get("ubicacion"),
            item.get("fecha_vencimiento"),
            item.get("ultima_actualizacion") or _now(),
            item.get("actualizado_por"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_inventario_cocina(conn: sqlite3.Connection, ubicacion: Optional[str] = None) -> list:
    if ubicacion is not None:
        rows = conn.execute(
            "SELECT * FROM inventario_cocina WHERE ubicacion = ? ORDER BY id",
            (ubicacion,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM inventario_cocina ORDER BY id").fetchall()
    return [dict(row) for row in rows]


# --- Lista de compras -----------------------------------------------------


def insert_lista_compras(conn: sqlite3.Connection, item: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO lista_compras
            (item_nombre, cantidad_deseada, unidad, prioridad, agregado_por,
             comprado, fecha_agregado)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            item["item_nombre"],
            item.get("cantidad_deseada"),
            item.get("unidad"),
            item.get("prioridad"),
            item.get("agregado_por"),
            item.get("fecha_agregado") or _now(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_lista_compras(conn: sqlite3.Connection, comprado: Optional[bool] = None) -> list:
    if comprado is not None:
        rows = conn.execute(
            "SELECT * FROM lista_compras WHERE comprado = ? ORDER BY id",
            (1 if comprado else 0,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM lista_compras ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def marcar_comprado(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute(
        "UPDATE lista_compras SET comprado = 1, fecha_comprado = ? WHERE id = ?",
        (_now(), item_id),
    )
    conn.commit()


def marcar_lista_compras_confirmada(
    conn: sqlite3.Connection,
    item_nombre: str,
    cantidad_deseada: Optional[float] = None,
    unidad: Optional[str] = None,
) -> int:
    """Marca `es_real=1` en el único ítem de `lista_compras` que coincida
    exactamente con `item_nombre` (+ `cantidad_deseada`/`unidad` si se pasan).

    Deliberadamente NO recibe un id fijo: confirma un ítem por sus datos
    observables, igual que `retirar_cine_demo.py` verifica el gasto demo por
    fecha/monto/descripción en vez de confiar ciegamente en un id. Lanza
    `ValueError` si no hay ninguna coincidencia o si hay más de una
    (ambigüedad — el caller debe acotar más los criterios).
    """
    condiciones = ["item_nombre = ?"]
    parametros: list = [item_nombre]
    if cantidad_deseada is not None:
        condiciones.append("cantidad_deseada = ?")
        parametros.append(cantidad_deseada)
    if unidad is not None:
        condiciones.append("unidad = ?")
        parametros.append(unidad)

    filas = conn.execute(
        f"SELECT id FROM lista_compras WHERE {' AND '.join(condiciones)}",
        parametros,
    ).fetchall()

    if not filas:
        raise ValueError(
            f"No hay ningún ítem en lista_compras que coincida con "
            f"item_nombre={item_nombre!r}, cantidad_deseada={cantidad_deseada!r}, "
            f"unidad={unidad!r}."
        )
    if len(filas) > 1:
        raise ValueError(
            f"Hay {len(filas)} ítems que coinciden con los criterios dados; "
            "acotá más (agregá cantidad_deseada y/o unidad) para desambiguar."
        )

    item_id = filas[0]["id"]
    conn.execute("UPDATE lista_compras SET es_real = 1 WHERE id = ?", (item_id,))
    conn.commit()
    return item_id


# --- Sugerencias de recetas cocinables ------------------------------------


def _inventario_disponible_por_ingrediente(conn: sqlite3.Connection) -> dict:
    """Suma `cantidad_actual` por nombre de ingrediente (case-insensitive)."""
    disponible: dict = {}
    for item in get_inventario_cocina(conn):
        clave = item["ingrediente_nombre"].strip().lower()
        disponible[clave] = disponible.get(clave, 0) + (item["cantidad_actual"] or 0)
    return disponible


def sugerir_receta_cocinable(conn: sqlite3.Connection) -> dict:
    """Devuelve recetas cocinables con el inventario actual.

    - `cocinables`: recetas activas cuyos ingredientes están todos
      disponibles en cantidad suficiente.
    - `casi_cocinables`: solo se calcula/devuelve cuando `cocinables` está
      vacía. Son recetas a las que les falta como máximo 1 ingrediente
      (o cantidad insuficiente de 1 ingrediente), con el nombre del
      faltante, para poder sugerir algo igualmente útil.
    """
    disponible = _inventario_disponible_por_ingrediente(conn)

    cocinables = []
    casi_cocinables = []
    for receta in get_recetas(conn, activa=True):
        faltantes = []
        for ing in get_receta_ingredientes(conn, receta["id"]):
            requerido = ing["cantidad"]
            if requerido is None:
                continue  # ingrediente "a gusto", sin restricción de cantidad
            clave = ing["ingrediente_nombre"].strip().lower()
            if disponible.get(clave, 0) < requerido:
                faltantes.append(ing["ingrediente_nombre"])

        if not faltantes:
            cocinables.append(receta)
        elif len(faltantes) == 1:
            casi_cocinables.append({**receta, "falta": faltantes[0]})

    return {
        "cocinables": cocinables,
        "casi_cocinables": [] if cocinables else casi_cocinables,
    }


def descontar_stock_por_receta(conn: sqlite3.Connection, receta_id: int) -> None:
    """Resta del inventario los ingredientes usados al cocinar una receta.

    Decisión de diseño: si el stock disponible es menor a lo requerido,
    se clampea a 0 en vez de dejar cantidades negativas (el registro de
    "faltante" ya lo resuelve `sugerir_receta_cocinable`, no esta función).
    Si hay más de una fila de inventario con el mismo `ingrediente_nombre`
    (p.ej. mismo ingrediente en heladera y en alacena), se descuenta primero
    de la que aparece antes (menor `id`) hasta agotar la cantidad requerida.
    """
    for ing in get_receta_ingredientes(conn, receta_id):
        requerido = ing["cantidad"]
        if requerido is None:
            continue

        filas = conn.execute(
            "SELECT id, cantidad_actual FROM inventario_cocina "
            "WHERE lower(ingrediente_nombre) = lower(?) ORDER BY id",
            (ing["ingrediente_nombre"],),
        ).fetchall()

        restante = requerido
        for fila in filas:
            if restante <= 0:
                break
            descuento = min(fila["cantidad_actual"], restante)
            nueva_cantidad = max(0.0, fila["cantidad_actual"] - descuento)
            conn.execute(
                "UPDATE inventario_cocina SET cantidad_actual = ?, "
                "ultima_actualizacion = ? WHERE id = ?",
                (nueva_cantidad, _now(), fila["id"]),
            )
            restante -= descuento

    conn.commit()


# --- Tarjetas --------------------------------------------------------------


def insert_tarjeta(conn: sqlite3.Connection, tarjeta: dict) -> str:
    """Inserta una tarjeta. Valida que a lo sumo una tenga `es_default_dinamico=1`.

    Si ya existe una tarjeta marcada como default dinámico y se intenta
    insertar otra con el flag en 1, rechaza con `ValueError` — el caller
    debe desmarcar la anterior explícitamente primero (no hay update
    automático implícito, para evitar cambios de default silenciosos).
    """
    es_default = 1 if tarjeta.get("es_default_dinamico") else 0
    if es_default:
        existente = conn.execute(
            "SELECT id FROM tarjetas WHERE es_default_dinamico = 1"
        ).fetchone()
        if existente is not None:
            raise ValueError(
                f"Ya existe una tarjeta default dinámico ({existente['id']}); "
                "desmarcá esa antes de marcar una nueva."
            )

    uso_compartido = 1 if tarjeta.get("uso_compartido") else 0

    conn.execute(
        """
        INSERT INTO tarjetas
            (id, nombre, tipo, banco, titular, dia_cierre, dia_vencimiento,
             es_default_dinamico, uso_compartido)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tarjeta["id"],
            tarjeta["nombre"],
            tarjeta["tipo"],
            tarjeta.get("banco"),
            tarjeta["titular"],
            tarjeta.get("dia_cierre"),
            tarjeta.get("dia_vencimiento"),
            es_default,
            uso_compartido,
        ),
    )
    conn.commit()
    return tarjeta["id"]


def get_tarjetas(conn: sqlite3.Connection, titular: Optional[str] = None) -> list:
    if titular is not None:
        rows = conn.execute(
            "SELECT * FROM tarjetas WHERE titular = ? ORDER BY id", (titular,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tarjetas ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_tarjeta_default_dinamico(conn: sqlite3.Connection) -> Optional[dict]:
    """Devuelve la tarjeta marcada como default para pagos dinámicos, o None."""
    row = conn.execute(
        "SELECT * FROM tarjetas WHERE es_default_dinamico = 1"
    ).fetchone()
    return dict(row) if row is not None else None


# --- Categorías (dinámicas) -------------------------------------------------


def get_categorias(conn: sqlite3.Connection, tipo: Optional[str] = None) -> list:
    if tipo is not None:
        rows = conn.execute(
            "SELECT * FROM categorias WHERE tipo = ? ORDER BY id", (tipo,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM categorias ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def crear_categoria_si_no_existe(
    conn: sqlite3.Connection,
    tipo: str,
    categoria: str,
    subcategoria: Optional[str] = None,
    creada_por: Optional[str] = None,
) -> dict:
    """Crea (tipo, categoria, subcategoria) si no existe; si existe, la devuelve.

    Idempotente por diseño: es la pieza que le permite al bot crear
    categorías nuevas sobre la marcha cuando detecta algo no catalogado en
    una conversación real, sin duplicar si ya fue creada antes (por el bot
    mismo o por otra conversación).
    """
    subcategoria = subcategoria or None
    if subcategoria is None:
        existente = conn.execute(
            "SELECT * FROM categorias WHERE tipo = ? AND categoria = ? "
            "AND subcategoria IS NULL",
            (tipo, categoria),
        ).fetchone()
    else:
        existente = conn.execute(
            "SELECT * FROM categorias WHERE tipo = ? AND categoria = ? "
            "AND subcategoria = ?",
            (tipo, categoria, subcategoria),
        ).fetchone()

    if existente is not None:
        return dict(existente)

    cursor = conn.execute(
        """
        INSERT INTO categorias (tipo, categoria, subcategoria, creada_por, creada_en)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tipo, categoria, subcategoria, creada_por, _now()),
    )
    conn.commit()
    nueva = conn.execute(
        "SELECT * FROM categorias WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(nueva)


# --- Gastos fijos ------------------------------------------------------------


def insert_gasto_fijo(conn: sqlite3.Connection, gasto_fijo: dict) -> int:
    """Inserta un gasto fijo (primera versión de una serie nueva).

    Campos de responsable/reparto:
        - responsable: 'Común' / 'JD' / 'Pinki' — OPCIONAL (compatibilidad
          legacy con `reference/db.py`, donde siempre fue opcional y
          default `NULL`; ver `validar_gasto_fijo`, corregido tras 2da
          pasada del revisor, run 3e22f249, hallazgo 2). Si no se pasa,
          queda `NULL` — esta capa NO le inventa un dueño a un gasto fijo
          legacy. Si se pasa, debe ser uno de los 3 valores válidos. La
          futura capa web (cuando exista) exigirá `responsable` obligatorio
          en el payload de alta; esta capa de dominio sigue siendo
          retrocompatible con datos/llamadas legacy sin ese campo.
        - tipo_proporcion: 'dinamica' / 'custom' / None; solo relevante si
          responsable='Común'.
        - proporcion_jd: solo si tipo_proporcion='custom'.
        - medio_pago: informativo.

    `vigente_desde` (versionado, ver README): fecha ISO 'YYYY-MM-DD' desde la
    que esta fila es la versión vigente. Default: la fecha de
    `ultima_actualizacion` (o hoy si tampoco se pasa). Para cambios de monto
    posteriores usar `crear_version_fijo`, NUNCA actualizar esta fila.

    `fijo_grupo_id` (identidad estable de la serie, ver
    `_migrar_columnas_gastos_fijos`): se fija automáticamente al propio `id`
    de esta fila (self-reference) — es el ancla de la que `crear_version_fijo`
    cuelga todas las versiones futuras, independiente de si `nombre` cambia.
    """
    ultima_actualizacion = gasto_fijo.get("ultima_actualizacion") or _now()
    vigente_desde = gasto_fijo.get("vigente_desde") or ultima_actualizacion[:10]

    errores = validar_gasto_fijo(
        {
            "monto_estimado": gasto_fijo.get("monto_estimado"),
            "vigente_desde": vigente_desde,
            "responsable": gasto_fijo.get("responsable"),
        }
    )
    if errores:
        raise ValueError(f"Gasto fijo inválido: {errores}")

    try:
        cursor = conn.execute(
            """
            INSERT INTO gastos_fijos
                (nombre, monto_estimado, periodicidad, dia_vencimiento, categoria,
                 subcategoria, activo, ultima_actualizacion, responsable,
                 tipo_proporcion, proporcion_jd, medio_pago, vigente_desde)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gasto_fijo["nombre"],
                gasto_fijo["monto_estimado"],
                gasto_fijo["periodicidad"],
                gasto_fijo.get("dia_vencimiento"),
                gasto_fijo.get("categoria"),
                gasto_fijo.get("subcategoria"),
                1 if gasto_fijo.get("activo", True) else 0,
                ultima_actualizacion,
                gasto_fijo.get("responsable"),
                gasto_fijo.get("tipo_proporcion"),
                gasto_fijo.get("proporcion_jd"),
                gasto_fijo.get("medio_pago"),
                vigente_desde,
            ),
        )
        nuevo_id = cursor.lastrowid
        fijo_grupo_id = gasto_fijo.get("fijo_grupo_id") or nuevo_id
        conn.execute(
            "UPDATE gastos_fijos SET fijo_grupo_id = ? WHERE id = ?",
            (fijo_grupo_id, nuevo_id),
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return nuevo_id


def get_gastos_fijos(conn: sqlite3.Connection, solo_activos: bool = True) -> list:
    if solo_activos:
        rows = conn.execute(
            "SELECT * FROM gastos_fijos WHERE activo = 1 ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM gastos_fijos ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def crear_version_fijo(
    conn: sqlite3.Connection,
    gasto_fijo_id: int,
    monto_nuevo: float,
    vigente_desde: str,
    responsable: Optional[str] = None,
    nombre: Optional[str] = None,
) -> int:
    """Crea una versión NUEVA de un gasto fijo, vigente desde `vigente_desde`.

    Reemplaza el UPDATE in-place de `actualizar_monto_fijo` (bug reportado
    por CPO, t_85b8502b: pisaba el histórico de montos). INSERTA una fila
    nueva en vez de modificar la anterior, para que
    `monto_fijo_vigente_en` pueda reconstruir cuánto costaba este gasto fijo
    en cualquier fecha pasada.

    Identidad de la serie (corrección tras dictamen NO APTO del revisor
    independiente, run 3b184396, hallazgo 4): la fila nueva hereda
    `fijo_grupo_id` de la SERIE a la que pertenece `gasto_fijo_id` — NUNCA
    se recalcula por `nombre`.

    Versión base (corregido tras 2da pasada del revisor, run 3e22f249,
    hallazgo 1): `gasto_fijo_id` solo se usa para RESOLVER a qué serie
    (`fijo_grupo_id`) pertenece la nueva versión. Los campos heredados
    (`nombre`/`periodicidad`/`categoria`/`subcategoria`/`responsable`/
    `tipo_proporcion`/`proporcion_jd`/`medio_pago`/`activo`) se copian de la
    versión VIGENTE MÁS RECIENTE de esa serie (mayor `vigente_desde`, no
    necesariamente la fila con mayor `id`) — NO de la fila literal que
    recibió `gasto_fijo_id`, que puede ser una versión histórica vieja. Sin
    esto, pasar el `id` de una versión antigua para crear una tercera
    versión pisaría silenciosamente un rename o cambio de responsable hecho
    en la versión intermedia. `responsable` y `nombre` igual se pueden
    pisar explícitamente vía los parámetros de esta función (p.ej. si
    cambia quién paga, o se renombra el gasto fijo manteniendo su identidad
    y su historial).

    `vigente_desde` duplicada dentro de la misma serie está PERMITIDA
    (decisión t_65096083, revirtiendo el rechazo de la ronda anterior:
    corregir dos veces un gasto fijo el mismo día es un uso normal —p.ej.
    un error de tipeo detectado minutos después— y no debe fallar, pero
    tampoco debe pisarse la fila vieja, porque Juan pidió histórico
    completo). Varias versiones pueden compartir `vigente_desde`; el
    desempate es determinístico por `(vigente_desde, id)`: entre versiones
    con igual `vigente_desde`, gana la de mayor `id` (la insertada más
    recientemente). Ver `monto_fijo_vigente_en` / `get_fijos_vigentes`, que
    aplican el mismo criterio de orden, y la sección "Versionado de fijos:
    varias versiones el mismo día" del README.

    Valida con `validar_gasto_fijo` (monto positivo finito, `vigente_desde`
    ISO válida, `responsable` resultante válido si no es `None`) antes de
    insertar nada. Lanza `ValueError` si `gasto_fijo_id` no existe o si la
    validación falla.
    """
    fila_referencia = conn.execute(
        "SELECT * FROM gastos_fijos WHERE id = ?", (gasto_fijo_id,)
    ).fetchone()
    if fila_referencia is None:
        raise ValueError(f"No existe ningún gasto fijo con id={gasto_fijo_id}.")

    fijo_grupo_id = fila_referencia["fijo_grupo_id"] or fila_referencia["id"]

    anterior = conn.execute(
        "SELECT * FROM gastos_fijos WHERE fijo_grupo_id = ? "
        "ORDER BY vigente_desde DESC, id DESC LIMIT 1",
        (fijo_grupo_id,),
    ).fetchone()

    nuevo_responsable = responsable if responsable is not None else anterior["responsable"]
    nuevo_nombre = nombre if nombre is not None else anterior["nombre"]

    errores = validar_gasto_fijo(
        {
            "monto_estimado": monto_nuevo,
            "vigente_desde": vigente_desde,
            "responsable": nuevo_responsable,
        }
    )
    if errores:
        raise ValueError(f"Nueva versión de gasto fijo inválida: {errores}")

    cursor = conn.execute(
        """
        INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, dia_vencimiento, categoria,
             subcategoria, activo, ultima_actualizacion, responsable,
             tipo_proporcion, proporcion_jd, medio_pago, vigente_desde, fijo_grupo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nuevo_nombre,
            monto_nuevo,
            anterior["periodicidad"],
            anterior["dia_vencimiento"],
            anterior["categoria"],
            anterior["subcategoria"],
            anterior["activo"],
            _now(),
            nuevo_responsable,
            anterior["tipo_proporcion"],
            anterior["proporcion_jd"],
            anterior["medio_pago"],
            vigente_desde,
            fijo_grupo_id,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _version_vigente_en(conn: sqlite3.Connection, fijo_grupo_id: int, fecha: str) -> Optional[dict]:
    """Resuelve la versión vigente de la serie `fijo_grupo_id` en `fecha`.

    Orden determinístico, compartido por `monto_fijo_vigente_en` y
    `get_fijos_vigentes` (ver README "Versionado de fijos: varias versiones
    el mismo día"): la vigente es la de mayor `(vigente_desde, id)` entre
    las versiones (activas o no) con `vigente_desde <= fecha`. Cuando dos
    versiones de la misma serie comparten `vigente_desde` (corrección del
    mismo gasto fijo más de una vez el mismo día), desempata la de mayor
    `id` — la insertada más recientemente. Devuelve `None` si no hay
    ninguna versión con `vigente_desde <= fecha`.
    """
    row = conn.execute(
        "SELECT * FROM gastos_fijos WHERE fijo_grupo_id = ? AND vigente_desde <= ? "
        "ORDER BY vigente_desde DESC, id DESC LIMIT 1",
        (fijo_grupo_id, fecha),
    ).fetchone()
    return dict(row) if row is not None else None


def monto_fijo_vigente_en(conn: sqlite3.Connection, fijo_grupo_id: int, fecha: str) -> Optional[dict]:
    """Devuelve la versión de un gasto fijo (serie `fijo_grupo_id`) vigente en
    `fecha`.

    `fijo_grupo_id` es la identidad estable de la serie (ver
    `_migrar_columnas_gastos_fijos`), NO el `nombre` (que puede repetirse o
    cambiar sin afectar la identidad de la serie). Para la primera versión
    de un gasto fijo, `fijo_grupo_id` es el `id` devuelto por
    `insert_gasto_fijo`.

    "Vigente en `fecha`" = la versión de mayor `(vigente_desde, id)` entre
    todas las de esa serie con `vigente_desde <= fecha` (ver
    `_version_vigente_en` para el criterio de desempate entre versiones con
    igual `vigente_desde`). Devuelve `None` si no hay ninguna versión con
    `vigente_desde <= fecha` (p.ej. se consulta una fecha anterior a la
    creación del gasto fijo).
    """
    return _version_vigente_en(conn, fijo_grupo_id, fecha)


def get_fijos_vigentes(conn: sqlite3.Connection, fecha: Optional[str] = None) -> list:
    """Devuelve una fila por SERIE (`fijo_grupo_id`) con la versión vigente a
    `fecha` ('YYYY-MM-DD'; default hoy), excluyendo series inactivas.

    A diferencia de `get_gastos_fijos` (que devuelve TODAS las filas de la
    tabla, histórico incluido, y no sabe nada de versionado), esta función
    resuelve para cada serie cuál de sus versiones es la vigente a la fecha
    pedida (mismo criterio que `monto_fijo_vigente_en`: mayor
    `(vigente_desde, id)` entre las versiones con `vigente_desde <= fecha`)
    y arma una lista con una única fila por serie.

    "Serie inactiva" = la versión vigente resuelta tiene `activo = 0`. Una
    serie sin ninguna versión con `vigente_desde <= fecha` (todavía no
    empezó a esa fecha) tampoco aparece en el resultado.
    """
    if fecha is None:
        fecha = _now()[:10]

    fijo_grupo_ids = [
        row["fijo_grupo_id"]
        for row in conn.execute(
            "SELECT DISTINCT fijo_grupo_id FROM gastos_fijos ORDER BY fijo_grupo_id"
        ).fetchall()
    ]

    vigentes = []
    for fijo_grupo_id in fijo_grupo_ids:
        version = _version_vigente_en(conn, fijo_grupo_id, fecha)
        if version is not None and version["activo"]:
            vigentes.append(version)
    return vigentes


def actualizar_monto_fijo(
    conn: sqlite3.Connection, gasto_fijo_id: int, monto_nuevo: float
) -> int:
    """DEPRECADA: delega en `crear_version_fijo` con `vigente_desde=hoy`.

    Antes hacía `UPDATE gastos_fijos SET monto_estimado = ...` in-place,
    borrando el histórico de montos anteriores (bug reportado por CPO,
    t_85b8502b). Ya NO modifica la fila anterior — inserta una versión
    nueva y devuelve su id. Preferir `crear_version_fijo` directamente
    cuando se conozca la fecha de vigencia real (no siempre es "hoy").
    """
    hoy = _now()[:10]
    return crear_version_fijo(conn, gasto_fijo_id, monto_nuevo, vigente_desde=hoy)


# --- Ingresos ----------------------------------------------------------------


def insert_ingreso(conn: sqlite3.Connection, ingreso: dict) -> int:
    """Inserta un ingreso. Exige `ingreso['confirmado'] is True`.

    Mismo principio no negociable que `insert_gasto`. Antes de insertar
    valida con `validar_ingreso` (misma barrera que ya existe en la capa de
    API para `validar_expense` — acá se aplica también dentro de `db.py`
    para que ningún caller pueda saltearla).
    """
    if ingreso.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un ingreso sin confirmación explícita "
            "(confirmado debe ser True)."
        )
    errores = validar_ingreso(ingreso)
    if errores:
        raise ValueError(f"Ingreso inválido: {errores}")

    cursor = conn.execute(
        """
        INSERT INTO ingresos
            (fecha, monto, moneda, categoria, persona, descripcion_original,
             origen, confirmado, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ingreso.get("fecha") or _now(),
            ingreso["monto"],
            ingreso.get("moneda") or "ARS",
            ingreso["categoria"],
            ingreso["persona"],
            ingreso.get("descripcion_original"),
            ingreso.get("origen") or "texto",
            1,
            _now(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_ingresos(conn: sqlite3.Connection, mes: Optional[str] = None) -> list:
    if mes is not None:
        rows = conn.execute(
            "SELECT * FROM ingresos WHERE substr(fecha, 1, 7) = ? ORDER BY id",
            (mes,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM ingresos ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def actualizar_ingreso(conn: sqlite3.Connection, ingreso_id: int, cambios: dict) -> None:
    """Edición parcial de un ingreso existente.

    Campos editables: fecha/monto/moneda/categoria/persona/descripcion_original.
    Valida el estado RESULTANTE (fila actual + `cambios` superpuestos) con
    `validar_ingreso` antes de aplicar nada — si la validación falla, no se
    ejecuta ningún UPDATE. Lanza `ValueError` si el ingreso no existe, si la
    validación falla, si `cambios` trae alguna clave fuera de las editables,
    o si `cambios` está vacío (rechazado explícitamente — con `cambios={}`
    el `UPDATE ingresos SET  WHERE id = ?` resultante es SQL inválido;
    hallazgo de revisor independiente, run 3b184396, hallazgo 7).
    """
    if not cambios:
        raise ValueError(
            "actualizar_ingreso requiere al menos un campo en `cambios` "
            "(no se aceptan ediciones vacías)."
        )

    CAMPOS_EDITABLES = (
        "fecha", "monto", "moneda", "categoria", "persona", "descripcion_original",
    )

    claves_invalidas = set(cambios) - set(CAMPOS_EDITABLES)
    if claves_invalidas:
        raise ValueError(
            f"Campos no editables en actualizar_ingreso: {sorted(claves_invalidas)} "
            f"(editables: {CAMPOS_EDITABLES})."
        )

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ningún ingreso con id={ingreso_id}.")

    resultante = {**dict(fila), **cambios}
    errores = validar_ingreso(resultante)
    if errores:
        raise ValueError(f"Edición de ingreso inválida: {errores}")

    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = list(cambios.values()) + [ingreso_id]
    conn.execute(f"UPDATE ingresos SET {columnas} WHERE id = ?", valores)
    conn.commit()


# --- Inversiones ---------------------------------------------------------


def insert_inversion(conn: sqlite3.Connection, inversion: dict) -> int:
    """Inserta una inversión. Exige `inversion['confirmado'] is True`.

    Mismo principio no negociable que `insert_gasto`.
    """
    if inversion.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar una inversión sin confirmación explícita "
            "(confirmado debe ser True)."
        )
    cursor = conn.execute(
        """
        INSERT INTO inversiones
            (fecha, monto, moneda, categoria, persona, descripcion_original,
             origen, confirmado, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inversion.get("fecha") or _now(),
            inversion["monto"],
            inversion.get("moneda") or "ARS",
            inversion["categoria"],
            inversion.get("persona"),
            inversion.get("descripcion_original"),
            inversion.get("origen") or "texto",
            1,
            _now(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_inversiones(conn: sqlite3.Connection, mes: Optional[str] = None) -> list:
    if mes is not None:
        rows = conn.execute(
            "SELECT * FROM inversiones WHERE substr(fecha, 1, 7) = ? ORDER BY id",
            (mes,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM inversiones ORDER BY id").fetchall()
    return [dict(row) for row in rows]


# --- Proporción dinámica y deudas -----------------------------------------


def _proporcion_salarios_mes(conn: sqlite3.Connection, mes: str) -> Optional[dict]:
    """Devuelve {'JD': pct, 'Pinki': pct} para `mes`, o None si no hay salarios."""
    rows = conn.execute(
        "SELECT persona, SUM(monto) AS total FROM ingresos "
        "WHERE categoria = 'Salario' AND substr(fecha, 1, 7) = ? "
        "GROUP BY persona",
        (mes,),
    ).fetchall()
    if not rows:
        return None

    total_general = sum(row["total"] for row in rows)
    if total_general <= 0:
        return None

    proporciones = {"JD": 0.0, "Pinki": 0.0}
    for row in rows:
        proporciones[row["persona"]] = round((row["total"] / total_general) * 100, 4)
    return proporciones


def calcular_proporcion_mes(conn: sqlite3.Connection, mes: str) -> dict:
    """Calcula la proporción JD/Pinki (0-100, suman 100) para `mes` ('YYYY-MM').

    Lógica portada tal cual del sistema real (no hay salarios fijos
    configurados en ningún lado):
      1. Suma `ingresos` con categoria='Salario' del mes, agrupado por persona.
      2. Si el mes no tiene salarios cargados, usa la proporción del último
         mes ANTERIOR que sí tenga (fallback explícito del modelo real).
      3. Si nunca hubo salarios cargados, devuelve 50/50 como default
         documentado.
    """
    proporciones = _proporcion_salarios_mes(conn, mes)
    if proporciones is not None:
        return proporciones

    meses_con_datos = sorted(
        {
            row["fecha"][:7]
            for row in conn.execute(
                "SELECT fecha FROM ingresos WHERE categoria = 'Salario'"
            ).fetchall()
        }
    )
    candidatos = [m for m in meses_con_datos if m < mes]
    if candidatos:
        return _proporcion_salarios_mes(conn, max(candidatos))

    return {"JD": 50.0, "Pinki": 50.0}


def calcular_deudas_mes(conn: sqlite3.Connection, mes: str) -> dict:
    """Calcula el saldo neto de deudas del mes ('YYYY-MM') entre JD y Pinki.

    Es un cálculo derivado, no una tabla propia: recorre `gastos` activos
    (no borrados, ver `eliminar_gasto_logico`) del mes con `pagado_por` en
    ('JD', 'Pinki') (los pagados por 'Común' no generan deuda) y, para cada
    uno, determina cuánto le correspondía pagar al que NO puso la plata:
      - `tipo_proporcion='dinamico'`: usa `calcular_proporcion_mes(mes)`
        (una sola vez por mes, no por gasto — la proporción es la misma
        para todos los gastos dinámicos de ese mes).
      - `tipo_proporcion='custom'`: usa la proporción explícita ya guardada
        en la fila (`proporcion_jd`/`proporcion_pinki`), porque esa es la
        excepción explícita del gasto y no depende del cálculo del mes.
    Todos los gastos del mes se acumulan en un único saldo neto (no se
    evalúa gasto por gasto de forma aislada).

    Devuelve {'deudor': 'JD'|'Pinki'|None, 'acreedor': ..., 'monto': float}.
    """
    rows = conn.execute(
        "SELECT * FROM gastos WHERE substr(fecha, 1, 7) = ? "
        "AND pagado_por IN ('JD', 'Pinki') AND deleted_at IS NULL",
        (mes,),
    ).fetchall()

    proporcion_dinamica = None
    saldo_a_favor_de_jd = 0.0

    for row in rows:
        gasto = dict(row)
        monto = gasto["monto"]

        if gasto["tipo_proporcion"] == "custom":
            pct_jd = gasto["proporcion_jd"]
            pct_pinki = gasto["proporcion_pinki"]
        else:
            if proporcion_dinamica is None:
                proporcion_dinamica = calcular_proporcion_mes(conn, mes)
            pct_jd = proporcion_dinamica["JD"]
            pct_pinki = proporcion_dinamica["Pinki"]

        corresponde_jd = monto * (pct_jd / 100)
        corresponde_pinki = monto * (pct_pinki / 100)

        if gasto["pagado_por"] == "JD":
            saldo_a_favor_de_jd += corresponde_pinki
        else:  # 'Pinki'
            saldo_a_favor_de_jd -= corresponde_jd

    if saldo_a_favor_de_jd > 0.0001:
        return {"deudor": "Pinki", "acreedor": "JD", "monto": round(saldo_a_favor_de_jd, 2)}
    if saldo_a_favor_de_jd < -0.0001:
        return {"deudor": "JD", "acreedor": "Pinki", "monto": round(-saldo_a_favor_de_jd, 2)}
    return {"deudor": None, "acreedor": None, "monto": 0.0}


def calcular_estado_saldado_mes(conn: sqlite3.Connection, mes: str) -> str:
    """Clasifica el estado de saldado de la deuda de `mes` ('YYYY-MM').

    Se basa pura y exclusivamente en la columna `saldado` de los gastos
    activos (no borrados) que generan deuda ese mes (`pagado_por` en
    JD/Pinki) — no en si el saldo neto calculado da 0, que es un cálculo
    aparte (`calcular_deudas_mes`).

    Devuelve:
      - 'sin_deuda': no hubo gastos de JD/Pinki ese mes.
      - 'pendiente': ninguno de esos gastos está saldado.
      - 'saldado': todos están saldados.
      - 'parcial': mezcla de saldados y pendientes.
    """
    rows = conn.execute(
        "SELECT saldado FROM gastos WHERE substr(fecha, 1, 7) = ? "
        "AND pagado_por IN ('JD', 'Pinki') AND deleted_at IS NULL",
        (mes,),
    ).fetchall()
    if not rows:
        return "sin_deuda"

    saldados = [row["saldado"] is not None for row in rows]
    if all(saldados):
        return "saldado"
    if not any(saldados):
        return "pendiente"
    return "parcial"


def _ultimo_dia_mes(mes: str) -> str:
    """Devuelve 'YYYY-MM-DD' del último día de `mes` ('YYYY-MM')."""
    import calendar

    year, month = (int(p) for p in mes.split("-"))
    ultimo_dia = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{ultimo_dia:02d}"


def calcular_deudas_pendientes(conn: sqlite3.Connection, hasta_mes: Optional[str] = None) -> dict:
    """Calcula el saldo neto de deudas PENDIENTES (no saldadas) entre JD y Pinki.

    A diferencia de `calcular_deudas_mes` (que arma el saldo de un mes
    puntual), esta función recorre TODOS los gastos activos (no borrados)
    con `pagado_por` en ('JD', 'Pinki') que tengan `saldado IS NULL` — sin
    importar de qué mes sean — porque a Juan solo le interesa la deuda
    pendiente real, no el histórico ya saldado (ver brief). Los gastos
    borrados lógicamente (`deleted_at IS NOT NULL`) se excluyen siempre:
    un gasto borrado no puede generar una deuda vigente.

    Decisión de diseño (documentada en README): para gastos
    `tipo_proporcion='dinamico'`, la proporción se calcula con
    `calcular_proporcion_mes` del mes DEL GASTO (no del mes en que se
    saldó), igual criterio que `calcular_deudas_mes`.

    `hasta_mes` ('YYYY-MM') opcional: si se pasa, solo considera gastos con
    `fecha <= último día de ese mes` (para consultas históricas bajo
    demanda). Sin `hasta_mes`, considera todos los gastos sin filtro de
    fecha.

    Devuelve {'deudor': 'JD'|'Pinki'|None, 'acreedor': ..., 'monto': float},
    igual forma que `calcular_deudas_mes`. Si no hay ninguna deuda
    pendiente, devuelve {'deudor': None, 'acreedor': None, 'monto': 0.0}
    (no None, para que el caller no tenga que manejar dos formas distintas
    de "sin deuda").
    """
    if hasta_mes is not None:
        rows = conn.execute(
            "SELECT * FROM gastos WHERE pagado_por IN ('JD', 'Pinki') "
            "AND saldado IS NULL AND deleted_at IS NULL AND fecha <= ?",
            (_ultimo_dia_mes(hasta_mes),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM gastos WHERE pagado_por IN ('JD', 'Pinki') "
            "AND saldado IS NULL AND deleted_at IS NULL"
        ).fetchall()

    proporciones_por_mes: dict = {}
    saldo_a_favor_de_jd = 0.0

    for row in rows:
        gasto = dict(row)
        monto = gasto["monto"]

        if gasto["tipo_proporcion"] == "custom":
            pct_jd = gasto["proporcion_jd"]
            pct_pinki = gasto["proporcion_pinki"]
        else:
            mes_gasto = gasto["fecha"][:7]
            if mes_gasto not in proporciones_por_mes:
                proporciones_por_mes[mes_gasto] = calcular_proporcion_mes(conn, mes_gasto)
            proporcion = proporciones_por_mes[mes_gasto]
            pct_jd = proporcion["JD"]
            pct_pinki = proporcion["Pinki"]

        corresponde_jd = monto * (pct_jd / 100)
        corresponde_pinki = monto * (pct_pinki / 100)

        if gasto["pagado_por"] == "JD":
            saldo_a_favor_de_jd += corresponde_pinki
        else:  # 'Pinki'
            saldo_a_favor_de_jd -= corresponde_jd

    if saldo_a_favor_de_jd > 0.0001:
        return {"deudor": "Pinki", "acreedor": "JD", "monto": round(saldo_a_favor_de_jd, 2)}
    if saldo_a_favor_de_jd < -0.0001:
        return {"deudor": "JD", "acreedor": "Pinki", "monto": round(-saldo_a_favor_de_jd, 2)}
    return {"deudor": None, "acreedor": None, "monto": 0.0}
