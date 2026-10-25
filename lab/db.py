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
    - auditoria: rastro genérico de cambios en gastos y gastos fijos.
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
      ya es su propia tabla (ver README). Tiene soft delete propio
      (`deleted_at`/`deleted_by` + `auditoria`, t_ce790609), mismo patrón
      que `gastos` (ver `eliminar_ingreso_logico`).
    - inversiones: movimientos de inversión (Plazo fijo/FCI/Dólar-MEP/
      Crypto/Otro), misma lógica que `ingresos`.
    - estado_conversacional: estado del flujo multi-turno por chat_id.
    - recetas / receta_ingredientes: recetario de ejemplo (Fase 3).
    - inventario_bienes: bienes del hogar (Fase 3). Extendida (t_0e38e74e,
      fix de alcance por decisión del coordinador: revierte la decisión
      previa de no agregar estos campos) con las columnas financieras del
      legacy real (`reference-legacy/inventario-setup.js`): `precio_ars`,
      `cotizacion_usd_compra`, `precio_usd_compra`, `proporcion_jd` (reparto
      JD/Pinki, 0-100), `precio_venta_estimado_usd` y `estado` (Activo/
      Vendido/Donado/Desechado) — ver README sección "Inventario: paridad
      con el legacy" y `_migrar_columnas_inventario_bienes`. Mapeo con los
      nombres del legacy: `nombre` = `descripcion`, `fecha_adquisicion` =
      `fecha_compra` — mismos datos; esta base ya usaba `nombre`/
      `fecha_adquisicion` antes de esta extensión y no se renombran columnas
      ni campos de API para no romper el CRUD existente.
    - inventario_cocina: stock de ingredientes disponibles (Fase 3).
    - lista_compras: items pendientes de comprar (Fase 3).

Principio no negociable: `insert_gasto`, `insert_ingreso` e `insert_inversion`
rechazan cualquier intento de insertar un registro que no venga marcado como
`confirmado=True`. La confirmación explícita del usuario se resuelve en
`conversation.py`; esta capa la vuelve a exigir como segunda barrera.
"""

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional

from validaciones import (
    _es_fecha_iso,
    _es_numero,
    validar_expense,
    validar_gasto_fijo,
    validar_ingreso,
    validar_telegram_expense,
    validar_telegram_ingreso,
)

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

-- UNIQUE(telegram_chat_id, usuario) en vez de UNIQUE(telegram_chat_id) solo
-- (esquema previo, t_65096083): permite que dos usuarios del mismo chat
-- tengan borradores independientes sin pisarse (ver DECISIONES.md S2/S3 y
-- `set_estado`/`get_estado`/`clear_estado`). Esta definición solo aplica a
-- bases nuevas (CREATE TABLE IF NOT EXISTS); una base existente con el
-- esquema viejo se recrea en `_migrar_estado_conversacional`, porque SQLite
-- no permite alterar una restricción UNIQUE in-place.
CREATE TABLE IF NOT EXISTS estado_conversacional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id TEXT NOT NULL,
    usuario TEXT,
    intent_detectado TEXT NOT NULL DEFAULT 'gasto',
    payload_parcial TEXT,
    campo_pendiente TEXT,
    mensaje_original TEXT,
    estado TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(telegram_chat_id, usuario)
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

-- Comprobantes (foto/PDF) de gastos/ingresos ingresados por Telegram
-- (brief S2/S3, T1). `hash_archivo` es la clave de dedupe exacta (ver
-- `_insert_comprobante_tx`/`buscar_comprobante_dedupe`); `gasto_id`/
-- `ingreso_id` son mutuamente excluyentes en la práctica (un comprobante
-- vincula a lo sumo uno de los dos), pero no se fuerza con CHECK a nivel
-- SQL -- la capa de API decide a cuál de los dos vincula cada alta.
CREATE TABLE IF NOT EXISTS comprobantes_telegram (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_archivo TEXT NOT NULL UNIQUE,
    chat_id TEXT,
    telegram_user_id TEXT,
    telegram_message_id TEXT,
    texto_extraido TEXT,
    monto_detectado REAL,
    fecha_detectada TEXT,
    comercio_detectado TEXT,
    ruta_archivo TEXT,
    gasto_id INTEGER REFERENCES gastos(id),
    ingreso_id INTEGER REFERENCES ingresos(id),
    creado_en TEXT NOT NULL
);

-- Umbrales de gasto en crédito detectados por mes calendario (brief S2/S3,
-- T1; cambio respecto del CTO 66f52e78: esta API no tiene token de
-- Telegram, así que solo DETECTA y registra -- `enviado_en` arranca en NULL
-- y lo marca Lasso después de enviar el aviso, ver
-- `/api/avisos-credito/marcar-enviados`). PRIMARY KEY compuesta: un umbral
-- ya registrado para un mes nunca se vuelve a registrar ni se borra, aunque
-- el total baje y vuelva a subir (ver `detectar_umbrales_credito`).
CREATE TABLE IF NOT EXISTS avisos_credito (
    mes TEXT NOT NULL,
    umbral INTEGER NOT NULL,
    total_al_detectar REAL NOT NULL,
    detectado_en TEXT NOT NULL,
    enviado_en TEXT,
    PRIMARY KEY (mes, umbral)
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
        # Telegram (brief S2/S3, T1): `chat_id` ya existía; estas dos
        # identifican quién mandó el mensaje y cuál fue, para trazabilidad
        # y para vincular `comprobantes_telegram` sin volver a preguntar.
        ("telegram_user_id", "TEXT"),
        ("telegram_message_id", "TEXT"),
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


def _estado_conversacional_tiene_unique_compuesto(conn: sqlite3.Connection) -> bool:
    """True si `estado_conversacional` ya tiene un índice UNIQUE sobre
    `(telegram_chat_id, usuario)` -- esquema ya migrado, o creado directo
    con el esquema nuevo en una base recién inicializada. Se usa
    `PRAGMA index_list`/`index_info` en vez de parsear el texto del
    `CREATE TABLE` en `sqlite_master`, para no depender de su formato
    exacto.
    """
    indices = conn.execute("PRAGMA index_list('estado_conversacional')").fetchall()
    for indice in indices:
        if not indice["unique"]:
            continue
        columnas = [
            fila["name"]
            for fila in conn.execute(f"PRAGMA index_info('{indice['name']}')").fetchall()
        ]
        if columnas == ["telegram_chat_id", "usuario"]:
            return True
    return False


def _migrar_estado_conversacional(conn: sqlite3.Connection) -> None:
    """Pasa `estado_conversacional` de `UNIQUE(telegram_chat_id)` a
    `UNIQUE(telegram_chat_id, usuario)` (brief S2/S3, T1; DECISIONES.md).

    SQLite no permite alterar una restricción UNIQUE existente -- se
    recrea la tabla preservando las filas en una sola transacción
    (rename -> create -> copy -> drop). Es seguro copiar sin riesgo de
    choque contra la nueva UNIQUE compuesta: bajo el esquema viejo nunca
    pudo existir más de una fila por `telegram_chat_id`, así que tampoco
    puede haber dos filas con el mismo `(telegram_chat_id, usuario)`.

    Idempotente: si la tabla ya tiene el índice único compuesto (porque ya
    fue migrada antes, o porque `SCHEMA` la creó directamente con el
    esquema nuevo), no hace nada.
    """
    if _estado_conversacional_tiene_unique_compuesto(conn):
        return

    try:
        # BEGIN explícito: el módulo `sqlite3` de Python solo abre una
        # transacción implícita antes de sentencias DML (INSERT/UPDATE/
        # DELETE), no antes de DDL como `ALTER`/`CREATE`/`DROP`. Sin este
        # `BEGIN`, cada paso de la secuencia rename -> create -> copy ->
        # drop correría en autocommit por separado, y un `rollback()` ante
        # una falla a mitad de camino no deshaería los pasos ya aplicados.
        conn.execute("BEGIN")
        conn.execute(
            "ALTER TABLE estado_conversacional RENAME TO estado_conversacional_legacy"
        )
        conn.execute(
            """
            CREATE TABLE estado_conversacional (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_chat_id TEXT NOT NULL,
                usuario TEXT,
                intent_detectado TEXT NOT NULL DEFAULT 'gasto',
                payload_parcial TEXT,
                campo_pendiente TEXT,
                mensaje_original TEXT,
                estado TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(telegram_chat_id, usuario)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO estado_conversacional
                (id, telegram_chat_id, usuario, intent_detectado, payload_parcial,
                 campo_pendiente, mensaje_original, estado, created_at, updated_at)
            SELECT id, telegram_chat_id, usuario, intent_detectado, payload_parcial,
                   campo_pendiente, mensaje_original, estado, created_at, updated_at
            FROM estado_conversacional_legacy
            """
        )
        conn.execute("DROP TABLE estado_conversacional_legacy")
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _migrar_columnas_gastos(conn)
    _migrar_columnas_tarjetas(conn)
    _migrar_columnas_gastos_fijos(conn)
    _migrar_columnas_lista_compras(conn)
    _migrar_columnas_recetas(conn)
    _migrar_columnas_ingresos(conn)
    _migrar_columnas_inventario_bienes(conn)
    _migrar_columnas_comprobantes_telegram(conn)
    _migrar_estado_conversacional(conn)


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


INVENTARIO_ESTADOS = ("Activo", "Vendido", "Donado", "Desechado")


def _migrar_columnas_inventario_bienes(conn: sqlite3.Connection) -> None:
    """Agrega a `inventario_bienes` las columnas de soft delete y de paridad
    financiera con el legacy si faltan (t_0e38e74e).

    Mismo patrón que `_migrar_columnas_ingresos`: ALTER TABLE ADD COLUMN
    retrocompatible en vez de recrear la tabla, para no perder datos ya
    migrados por `migrar_datos_reales.migrar_inventario_bienes`. Idempotente:
    solo agrega las columnas que todavía no existen.

    Decisión de columnas (reversión de una decisión previa de esta misma
    tarea, por indicación del coordinador — Juan pidió explícitamente
    paridad con la pestaña legacy, BRIEF.md punto 1): el legacy
    (`reference-legacy/inventario-setup.js` / `inventario-index.html`)
    expone `precio_ars`, `cotizacion_usd_compra`, `precio_usd_compra`,
    `proporcion_jd`, `precio_venta_estimado_usd` y `estado`. Todas se
    agregan acá como columnas nullable — nunca `NOT NULL` a nivel SQL —
    porque:
      - Los registros ya migrados por `migrar_inventario_bienes` no tienen
        estos valores en columnas estructuradas (están, si existen, como
        texto libre dentro de `notas`); esta migración NO los retro-parsea
        desde `notas` — son columnas nuevas que arrancan en `NULL` para
        filas preexistentes, no un backfill automático.
      - Los defaults de negocio (`proporcion_jd=50`, `estado='Activo'`)
        se aplican en `insert_inventario_bien` (capa Python) cuando el
        caller no los especifica, no en el `ALTER TABLE` — así una fila
        vieja sin estos valores queda en `NULL` en vez de asumir
        silenciosamente "Activo"/"50% JD" para datos que nunca se
        declararon.

    `estado` se valida contra `INVENTARIO_ESTADOS` en
    `validar_inventario_bien`, no con un `CHECK` de SQL — mismo criterio que
    el resto del esquema (ver `PAGADO_POR_VALIDOS` en validaciones.py).

    Mapeo con los nombres del legacy (ver módulo, encabezado): `nombre` =
    `descripcion`, `fecha_adquisicion` = `fecha_compra`. No se agregan
    columnas duplicadas para esos dos campos — ya existían con estos nombres
    antes de esta extensión.
    """
    existentes = _column_names(conn, "inventario_bienes")
    columnas_nuevas = (
        ("deleted_at", "TEXT"),
        ("deleted_by", "TEXT"),
        ("precio_ars", "REAL"),
        ("cotizacion_usd_compra", "REAL"),
        ("precio_usd_compra", "REAL"),
        ("proporcion_jd", "REAL"),
        ("precio_venta_estimado_usd", "REAL"),
        ("estado", "TEXT"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE inventario_bienes ADD COLUMN {columna} {definicion}")
    conn.commit()


def _migrar_columnas_comprobantes_telegram(conn: sqlite3.Connection) -> None:
    """Agrega a `comprobantes_telegram` la columna `nro_operacion` si falta,
    más un índice único PARCIAL sobre ella (brief: dedupe de comprobantes
    por número de operación bancaria, además del hash exacto y la
    coincidencia aproximada por monto/fecha/comercio que ya existían).

    Mismo patrón que el resto de `_migrar_columnas_*`: `ALTER TABLE ADD
    COLUMN` retrocompatible, nunca recrea la tabla. Nullable a nivel SQL --
    no todo comprobante trae un número de operación (ej. comprobantes
    tipeados a mano, o formatos todavía no soportados por `extraer-
    campos`/`formato_desconocido`).

    El índice es PARCIAL (`WHERE nro_operacion IS NOT NULL`) a propósito:
    SQLite no considera iguales dos `NULL` a los fines de un índice UNIQUE
    normal (no haría falta la cláusula `WHERE` por esa razón sola), pero la
    cláusula deja explícito que la restricción de unicidad solo aplica a
    comprobantes que SÍ tienen un número de operación -- evita cualquier
    ambigüedad si en el futuro cambia el motor o se migra el esquema.
    `CREATE UNIQUE INDEX IF NOT EXISTS` hace esto idempotente: correrlo de
    nuevo sobre una base ya migrada no falla ni duplica el índice.
    """
    existentes = _column_names(conn, "comprobantes_telegram")
    if "nro_operacion" not in existentes:
        conn.execute("ALTER TABLE comprobantes_telegram ADD COLUMN nro_operacion TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_comprobantes_telegram_nro_operacion "
        "ON comprobantes_telegram(nro_operacion) WHERE nro_operacion IS NOT NULL"
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


def _insert_gasto_tx(
    conn: sqlite3.Connection, gasto: dict, *, monto_total_original: Optional[float] = None,
) -> int:
    """Igual que `insert_gasto`, pero sin `commit()` — para uso interno de
    `insert_gasto` y `insert_gasto_con_cuotas`, que controlan la transacción
    completa (ver nota de atomicidad en `insert_gasto_con_cuotas`).

    Corre `validar_expense` antes de tocar la base: es la barrera que
    el revisor independiente (run 3b184396, hallazgo 1) encontró ausente —
    antes se podía insertar `monto<=0`, `categoria=""`, `pagado_por`
    inválido o `cuotas_total<=0` llamando a `insert_gasto` directamente,
    porque solo se chequeaban `confirmado` y las proporciones a mano. Para
    cuotas expandidas, `monto_total_original` permite validar el mínimo de
    centavos contra el total sin dejar de exigir monto positivo en cada fila.
    """
    # Al expandir cuotas, `monto` es el importe de esta fila, mientras que
    # `cuotas_total` describe el gasto completo. El mínimo de un centavo por
    # cuota se comprueba contra el monto original, no contra cada fila.
    gasto_para_validar = (
        gasto if monto_total_original is None
        else {**gasto, "monto": monto_total_original}
    )
    errores = validar_expense(gasto_para_validar)
    if monto_total_original is not None and (
        not _es_numero(gasto.get("monto")) or gasto["monto"] <= 0
    ):
        errores.append("monto de cuota debe ser mayor a 0.")
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
             proporcion_pinki, cuotas_total, cuota_nro, cuota_ref, saldado,
             telegram_user_id, telegram_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            gasto.get("telegram_user_id"),
            gasto.get("telegram_message_id"),
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


def _repartir_cuotas_centavos(monto_total: float, cuotas_total: int) -> list[int]:
    """Reparte un monto en centavos enteros, con el resto al comienzo."""
    centavos_exactos = Decimal(str(monto_total)) * 100
    if centavos_exactos != centavos_exactos.to_integral_value():
        raise ValueError("monto_total debe tener como máximo dos decimales.")
    total_centavos = int(centavos_exactos)
    if total_centavos < cuotas_total:
        raise ValueError("cuotas_total excede los centavos disponibles del monto.")
    base, resto = divmod(total_centavos, cuotas_total)
    return [base + (indice < resto) for indice in range(cuotas_total)]


def insert_gasto_con_cuotas(conn: sqlite3.Connection, gasto: dict, cuotas_total: int) -> "int | list":
    """Inserta un gasto, expandiéndolo en N filas si tiene cuotas.

    - `cuotas_total` None: se toma como 1 (retrocompatible).
    - `cuotas_total` inválido (no entero, `bool`, o fuera de 1..120):
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

    El monto se distribuye en centavos enteros: `divmod` asigna un centavo
    adicional a las primeras cuotas que lo necesitan. Todas quedan positivas,
    suman exactamente el total y difieren a lo sumo en un centavo.
    """
    if cuotas_total is None:
        cuotas_total = 1
    if (
        not isinstance(cuotas_total, int)
        or isinstance(cuotas_total, bool)
        or not 1 <= cuotas_total <= 120
    ):
        raise ValueError(
            f"cuotas_total debe ser un entero entre 1 y 120 (recibido {cuotas_total!r})."
        )
    if cuotas_total == 1:
        return insert_gasto(conn, gasto)

    if gasto.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un gasto sin confirmación explícita "
            "(confirmado debe ser True)."
        )

    montos_centavos = _repartir_cuotas_centavos(gasto["monto"], cuotas_total)
    fecha_base = (gasto.get("fecha") or _now())[:10]

    ids = []
    cuota_ref = None
    try:
        for numero, centavos in enumerate(montos_centavos, start=1):
            gasto_cuota = dict(gasto)
            gasto_cuota["monto"] = float(Decimal(centavos) / 100)
            gasto_cuota["fecha"] = _sumar_meses(fecha_base, numero - 1)
            gasto_cuota["cuotas_total"] = cuotas_total
            gasto_cuota["cuota_nro"] = numero
            gasto_cuota["cuota_ref"] = cuota_ref
            nuevo_id = _insert_gasto_tx(
                conn, gasto_cuota, monto_total_original=gasto["monto"]
            )
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


def get_estado(
    conn: sqlite3.Connection, chat_id: str, usuario: Optional[str] = None
) -> Optional[dict]:
    """Devuelve el estado conversacional de `(chat_id, usuario)`, o `None`
    si no hay ninguno. `usuario=None` (default) busca el borrador "sin
    usuario identificado" de ese chat -- nunca cualquier usuario del chat
    (ver `set_estado`, DECISIONES.md: dos usuarios del mismo chat tienen
    borradores independientes desde la migración a
    `UNIQUE(telegram_chat_id, usuario)`).
    """
    row = conn.execute(
        "SELECT * FROM estado_conversacional WHERE telegram_chat_id = ? AND usuario IS ?",
        (chat_id, usuario),
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
    """Crea o actualiza la fila de estado conversacional de `(chat_id, usuario)`.

    Desde la migración a `UNIQUE(telegram_chat_id, usuario)` (ver
    DECISIONES.md), dos usuarios del mismo chat tienen borradores
    independientes: `usuario` identifica cuál se crea o actualiza. No se usa
    `INSERT ... ON CONFLICT` porque SQLite nunca considera iguales dos
    `NULL` a los fines de un índice UNIQUE (el conflicto no se dispararía
    para `usuario=None`, dejando crear una fila nueva en vez de actualizar
    la existente); en su lugar se busca la fila con `usuario IS ?`
    (comparación NULL-safe) y se actualiza o inserta explícitamente.

    `intent_detectado` queda fijo en "gasto" por ahora (Fase 1 sólo
    implementa ese intent; receta/inventario/compra quedan para fases
    futuras, ver LIFE-lab-propuesta.md sección 3).
    """
    existente = conn.execute(
        "SELECT id FROM estado_conversacional WHERE telegram_chat_id = ? AND usuario IS ?",
        (chat_id, usuario),
    ).fetchone()
    payload_json = json.dumps(payload_parcial or {}, ensure_ascii=False)
    ahora = _now()
    if existente is not None:
        conn.execute(
            """
            UPDATE estado_conversacional SET
                intent_detectado = ?, payload_parcial = ?, campo_pendiente = ?,
                mensaje_original = ?, estado = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                intent_detectado, payload_json, campo_pendiente, mensaje_original,
                estado, ahora, existente["id"],
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO estado_conversacional
                (telegram_chat_id, usuario, intent_detectado, payload_parcial,
                 campo_pendiente, mensaje_original, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id, usuario, intent_detectado, payload_json, campo_pendiente,
                mensaje_original, estado, ahora, ahora,
            ),
        )
    conn.commit()


def clear_estado(conn: sqlite3.Connection, chat_id: str, usuario: Optional[str] = None) -> None:
    """Borra el estado conversacional de `(chat_id, usuario)` -- solo ese
    borrador, no los de otros usuarios del mismo chat (ver `set_estado`)."""
    conn.execute(
        "DELETE FROM estado_conversacional WHERE telegram_chat_id = ? AND usuario IS ?",
        (chat_id, usuario),
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

INVENTARIO_CAMPOS_EDITABLES = (
    "nombre", "categoria", "ubicacion", "valor_estimado", "fecha_adquisicion", "notas",
    "precio_ars", "cotizacion_usd_compra", "precio_usd_compra", "proporcion_jd",
    "precio_venta_estimado_usd", "estado",
)


def validar_inventario_bien(bien: dict) -> list:
    """Valida un payload de alta/edición de `inventario_bienes`, mismas
    convenciones que `validar_ingreso`/`validar_expense` (ver validaciones.py).

    Reglas (t_0e38e74e):
      - `nombre` obligatorio, no vacío.
      - `valor_estimado` obligatorio, numérico finito, > 0 — mismo criterio
        que `monto` en gastos/ingresos: un bien sin valor estimado no aporta
        nada al total que muestra la pestaña.
      - `categoria`/`ubicacion`/`notas`: opcionales, pero si se especifican
        no pueden ser strings vacíos (excepto `notas`, que admite cualquier
        texto, incluido vacío, porque es de uso libre).
      - `fecha_adquisicion`: opcional, si se especifica debe ser fecha ISO
        'YYYY-MM-DD' válida.
      - `precio_ars`, `cotizacion_usd_compra`, `precio_usd_compra`,
        `precio_venta_estimado_usd`: opcionales (paridad con el legacy, ver
        `_migrar_columnas_inventario_bienes`); si se especifican deben ser
        numéricos finitos y >= 0 (admiten 0, a diferencia de `valor_estimado`
        — un bien puede tener cotización o precio de reventa en 0 mientras
        se completa el dato, nunca negativo).
      - `proporcion_jd`: opcional (default 50 al crear si no viene, ver
        `insert_inventario_bien`); si se especifica debe ser numérico finito
        entre 0 y 100 inclusive. Pinki = 100 - proporcion_jd, igual que el
        legacy — no se guarda una columna separada para Pinki.
      - `estado`: opcional (default 'Activo' al crear si no viene); si se
        especifica debe ser uno de `INVENTARIO_ESTADOS`.

    Devuelve una lista de errores (vacía si el payload es válido). No muta
    `bien` ni toca la base de datos.
    """
    errores = []

    nombre = bien.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        errores.append("nombre es obligatorio y no puede estar vacío.")

    valor_estimado = bien.get("valor_estimado")
    if not _es_numero(valor_estimado):
        errores.append("valor_estimado es obligatorio y debe ser numérico.")
    elif valor_estimado <= 0:
        errores.append("valor_estimado debe ser mayor a 0.")

    categoria = bien.get("categoria")
    if categoria is not None and (not isinstance(categoria, str) or not categoria.strip()):
        errores.append("categoria, si se especifica, no puede estar vacía.")

    ubicacion = bien.get("ubicacion")
    if ubicacion is not None and (not isinstance(ubicacion, str) or not ubicacion.strip()):
        errores.append("ubicacion, si se especifica, no puede estar vacía.")

    fecha_adquisicion = bien.get("fecha_adquisicion")
    if fecha_adquisicion is not None and not _es_fecha_iso(fecha_adquisicion):
        errores.append(
            f"fecha_adquisicion, si se especifica, debe ser fecha ISO 'YYYY-MM-DD' "
            f"válida (recibido {fecha_adquisicion!r})."
        )

    notas = bien.get("notas")
    if notas is not None and not isinstance(notas, str):
        errores.append("notas, si se especifica, debe ser texto.")

    for campo in ("precio_ars", "cotizacion_usd_compra", "precio_usd_compra", "precio_venta_estimado_usd"):
        valor = bien.get(campo)
        if valor is None:
            continue
        if not _es_numero(valor):
            errores.append(f"{campo}, si se especifica, debe ser numérico.")
        elif valor < 0:
            errores.append(f"{campo} debe ser mayor o igual a 0.")

    proporcion_jd = bien.get("proporcion_jd")
    if proporcion_jd is not None:
        if not _es_numero(proporcion_jd):
            errores.append("proporcion_jd, si se especifica, debe ser numérico.")
        elif not (0 <= proporcion_jd <= 100):
            errores.append("proporcion_jd debe estar entre 0 y 100.")

    estado = bien.get("estado")
    if estado is not None and estado not in INVENTARIO_ESTADOS:
        errores.append(
            f"estado, si se especifica, debe ser uno de {INVENTARIO_ESTADOS} (recibido {estado!r})."
        )

    return errores


def insert_inventario_bien(conn: sqlite3.Connection, bien: dict) -> int:
    """Inserta un bien de inventario. Valida con `_validar_inventario_bien`
    antes de insertar — misma barrera no negociable que `insert_gasto`/
    `insert_ingreso` (ver esas funciones), aplicada acá dentro de `db.py`
    para que ningún caller pueda saltearla.

    Defaults de negocio (t_0e38e74e, paridad con el legacy): si no vienen en
    `bien`, `proporcion_jd` se guarda en `50` y `estado` en `'Activo'` — se
    chequea `is None` explícitamente (no `bien.get(...) or default`) porque
    `proporcion_jd=0` (100% Pinki) es un valor válido y no debe pisarse por
    ser falsy.
    """
    errores = validar_inventario_bien(bien)
    if errores:
        raise ValueError(f"Bien de inventario inválido: {errores}")

    proporcion_jd = bien.get("proporcion_jd")
    if proporcion_jd is None:
        proporcion_jd = 50
    estado = bien.get("estado")
    if estado is None:
        estado = "Activo"

    cursor = conn.execute(
        """
        INSERT INTO inventario_bienes
            (nombre, categoria, ubicacion, valor_estimado, fecha_adquisicion, notas,
             precio_ars, cotizacion_usd_compra, precio_usd_compra, proporcion_jd,
             precio_venta_estimado_usd, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bien["nombre"],
            bien.get("categoria"),
            bien.get("ubicacion"),
            bien.get("valor_estimado"),
            bien.get("fecha_adquisicion"),
            bien.get("notas"),
            bien.get("precio_ars"),
            bien.get("cotizacion_usd_compra"),
            bien.get("precio_usd_compra"),
            proporcion_jd,
            bien.get("precio_venta_estimado_usd"),
            estado,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_inventario_bienes(
    conn: sqlite3.Connection,
    categoria: Optional[str] = None,
    incluir_borrados: bool = False,
) -> list:
    """Devuelve bienes de inventario ordenados por id.

    Por default excluye los bienes con `deleted_at IS NOT NULL` (soft
    delete, ver `eliminar_inventario_bien_logico`). Pasar
    `incluir_borrados=True` para incluirlos también (p.ej. para una vista
    de auditoría/papelera).
    """
    condiciones = []
    parametros: list = []
    if categoria is not None:
        condiciones.append("categoria = ?")
        parametros.append(categoria)
    if not incluir_borrados:
        condiciones.append("deleted_at IS NULL")

    where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    rows = conn.execute(
        f"SELECT * FROM inventario_bienes{where} ORDER BY id", parametros
    ).fetchall()
    return [dict(row) for row in rows]


def actualizar_inventario_bien(conn: sqlite3.Connection, bien_id: int, cambios: dict) -> None:
    """Edición parcial de un bien de inventario existente.

    Mismo contrato que `actualizar_ingreso`: campos editables limitados a
    `INVENTARIO_CAMPOS_EDITABLES`, valida el estado RESULTANTE (fila actual
    + `cambios` superpuestos) antes de aplicar nada, y rechaza `cambios`
    vacío o con claves no editables. Lanza `ValueError` si el bien no
    existe, si ya está borrado lógicamente (debe restaurarse primero, lo
    que hoy no existe), o si la validación falla.
    """
    if not cambios:
        raise ValueError(
            "actualizar_inventario_bien requiere al menos un campo en `cambios` "
            "(no se aceptan ediciones vacías)."
        )

    claves_invalidas = set(cambios) - set(INVENTARIO_CAMPOS_EDITABLES)
    if claves_invalidas:
        raise ValueError(
            f"Campos no editables en actualizar_inventario_bien: {sorted(claves_invalidas)} "
            f"(editables: {INVENTARIO_CAMPOS_EDITABLES})."
        )

    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ningún bien de inventario con id={bien_id}.")
    if fila["deleted_at"] is not None:
        raise ValueError(f"No se puede editar el bien de inventario id={bien_id}: está borrado.")

    resultante = {**dict(fila), **cambios}
    errores = validar_inventario_bien(resultante)
    if errores:
        raise ValueError(f"Edición de bien de inventario inválida: {errores}")

    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = list(cambios.values()) + [bien_id]
    conn.execute(f"UPDATE inventario_bienes SET {columnas} WHERE id = ?", valores)
    conn.commit()


# --- Soft delete de inventario_bienes + auditoría ---------------------------


def eliminar_inventario_bien_logico(conn: sqlite3.Connection, bien_id: int, actor: str) -> None:
    """Marca `inventario_bienes.id = bien_id` como borrado lógico (soft delete).

    Mismo contrato que `eliminar_ingreso_logico` (ver esa función para el
    detalle de atomicidad y de la condición de carrera): no borra la fila
    físicamente, deja rastro en `auditoria` con el snapshot previo de la
    fila, y levanta `ValueError` si el bien no existe o ya estaba borrado
    — incluyendo el caso de doble baja concurrente, detectado por
    `cursor.rowcount != 1` en el `UPDATE` condicionado a `deleted_at IS
    NULL`. Si falla el `INSERT` en `auditoria` después del `UPDATE`, se
    hace `rollback()` explícito antes de propagar la excepción.
    """
    fila = conn.execute("SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ningún bien de inventario con id={bien_id}.")
    if fila["deleted_at"] is not None:
        raise ValueError(f"El bien de inventario id={bien_id} ya está borrado.")

    snapshot_antes = json.dumps(dict(fila), ensure_ascii=False)
    ahora = _now()

    try:
        cursor = conn.execute(
            "UPDATE inventario_bienes SET deleted_at = ?, deleted_by = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (ahora, actor, bien_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"El bien de inventario id={bien_id} ya fue borrado por otra operación "
                "concurrente (detectado al aplicar la baja)."
            )
        conn.execute(
            """
            INSERT INTO auditoria (tabla, fila_id, accion, actor, antes_json, despues_json, creado_en)
            VALUES ('inventario_bienes', ?, 'baja', ?, ?, NULL, ?)
            """,
            (bien_id, actor, snapshot_antes, ahora),
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()


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

_FIXED_UNSET = object()


class FixedSplitError(ValueError):
    """Invalid fixed-expense allocation supplied by a caller."""


class FixedNoChangeError(ValueError):
    """A proposed version has the same business fields as its predecessor."""


def resolve_fixed_split(responsable, tipo_proporcion=_FIXED_UNSET,
                        proporcion_jd=_FIXED_UNSET, anterior=None):
    """Return the stored split for a new version without changing older rows.

    A missing field inherits only within a common-to-common edit. Moving from
    a personal expense back to common starts in dynamic mode unless the caller
    explicitly supplies a complete custom split.
    """
    if responsable in ("JD", "Pinki"):
        if tipo_proporcion not in (_FIXED_UNSET, None) or proporcion_jd not in (_FIXED_UNSET, None):
            raise FixedSplitError("El reparto explícito solo corresponde a responsable Común.")
        return None, 100.0 if responsable == "JD" else 0.0

    if responsable is None:
        if tipo_proporcion is not _FIXED_UNSET or proporcion_jd is not _FIXED_UNSET:
            raise FixedSplitError("No se puede asignar reparto sin responsable.")
        return (anterior["tipo_proporcion"], anterior["proporcion_jd"]) if anterior else (None, None)

    if responsable != "Común":
        raise FixedSplitError("Responsable inválido.")

    inherited = anterior is not None and anterior["responsable"] == "Común"
    if tipo_proporcion is _FIXED_UNSET:
        tipo = anterior["tipo_proporcion"] if inherited else "dinamica"
    else:
        tipo = tipo_proporcion
    if tipo == "dinamico":
        tipo = "dinamica"
    if tipo is None and inherited and tipo_proporcion is _FIXED_UNSET:
        tipo = "dinamica"
    if tipo not in ("dinamica", "custom"):
        raise FixedSplitError("tipo_proporcion debe ser dinamica o custom.")

    if tipo == "dinamica":
        if proporcion_jd not in (_FIXED_UNSET, None):
            raise FixedSplitError("La proporción dinámica no admite porcentaje explícito.")
        return "dinamica", None

    if proporcion_jd is _FIXED_UNSET:
        pct = anterior["proporcion_jd"] if inherited and anterior["tipo_proporcion"] == "custom" else None
    else:
        pct = proporcion_jd
    if (isinstance(pct, bool) or not isinstance(pct, (int, float))
            or not math.isfinite(pct) or not 0 <= pct <= 100):
        raise FixedSplitError("custom requiere proporcion_jd numérico y finito entre 0 y 100.")
    return "custom", float(pct)


def _auditar_fijo(conn, fila_id, accion, actor, antes, despues):
    conn.execute(
        "INSERT INTO auditoria (tabla, fila_id, accion, actor, antes_json, despues_json, creado_en) "
        "VALUES ('gastos_fijos', ?, ?, ?, ?, ?, ?)",
        (fila_id, accion, actor,
         json.dumps(antes, ensure_ascii=False) if antes is not None else None,
         json.dumps(despues, ensure_ascii=False) if despues is not None else None, _now()),
    )


def monto_mensual(version: dict) -> float:
    """Monto mensual equivalente, con redondeo decimal comercial a centavos."""
    divisor = 2 if version["periodicidad"] == "bimestral" else 1
    return float((Decimal(str(version["monto_estimado"])) / divisor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ))


def insert_gasto_fijo(conn: sqlite3.Connection, gasto_fijo: dict, actor: Optional[str] = None) -> int:
    """Inserta un gasto fijo (primera versión de una serie nueva).

    Campos de responsable/reparto:
        - responsable: 'Común' / 'JD' / 'Pinki' — OPCIONAL (compatibilidad
          legacy con `reference/db.py`, donde siempre fue opcional y
          default `NULL`; ver `validar_gasto_fijo`, corregido tras 2da
          pasada del revisor, run 3e22f249, hallazgo 2). Si no se pasa,
          queda `NULL` — esta capa NO le inventa un dueño a un gasto fijo
          legacy. Si se pasa, debe ser uno de los 3 valores válidos. La
          capa web exige `responsable` obligatorio en el payload de alta;
          esta capa de dominio sigue siendo
          retrocompatible con datos/llamadas legacy sin ese campo.
        - tipo_proporcion: 'dinamica' / 'custom' solo para 'Común'; el alias
          de entrada 'dinamico' se guarda como 'dinamica'.
        - proporcion_jd: porcentaje manual para 'Común' + 'custom'; para
          'JD'/'Pinki' se guarda 100/0 con tipo_proporcion NULL.
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
            "nombre": gasto_fijo.get("nombre"),
            "periodicidad": gasto_fijo.get("periodicidad"),
        }
    )
    if errores:
        raise ValueError(f"Gasto fijo inválido: {errores}")
    tipo_proporcion, proporcion_jd = resolve_fixed_split(
        gasto_fijo.get("responsable"),
        gasto_fijo.get("tipo_proporcion", _FIXED_UNSET),
        gasto_fijo.get("proporcion_jd", _FIXED_UNSET),
    )

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
                tipo_proporcion,
                proporcion_jd,
                gasto_fijo.get("medio_pago"),
                vigente_desde,
            ),
        )
        nuevo_id = cursor.lastrowid
        fijo_grupo_id = nuevo_id
        conn.execute(
            "UPDATE gastos_fijos SET fijo_grupo_id = ? WHERE id = ?",
            (fijo_grupo_id, nuevo_id),
        )
        despues = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        _auditar_fijo(conn, nuevo_id, "alta", actor, None, despues)
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
    monto_nuevo: Optional[float] = None,
    vigente_desde: Optional[str] = None,
    responsable: Optional[str] = None,
    nombre: Optional[str] = None,
    periodicidad: Optional[str] = None,
    actor: Optional[str] = None,
    tipo_proporcion=_FIXED_UNSET,
    proporcion_jd=_FIXED_UNSET,
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

    `gasto_fijo_id` solo resuelve la serie. Los campos no modificados se
    heredan de la versión vigente en `vigente_desde` (mayor fecha anterior
    o igual, luego mayor id). Así una edición retroactiva conserva los
    metadatos de su época y no altera las versiones posteriores. No se
    permite crear una versión anterior al comienzo de la serie.

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

    Valida el gasto y su reparto antes de insertar nada. Los dos argumentos
    de reparto se agregan al final para conservar la posición de `actor`;
    su centinela distingue omisión, NULL explícito y porcentaje cero.
    """
    fila_referencia = conn.execute(
        "SELECT * FROM gastos_fijos WHERE id = ?", (gasto_fijo_id,)
    ).fetchone()
    if fila_referencia is None:
        raise ValueError(f"No existe ningún gasto fijo con id={gasto_fijo_id}.")

    fijo_grupo_id = fila_referencia["fijo_grupo_id"] or fila_referencia["id"]

    try:
        fecha = date.fromisoformat(vigente_desde)
        if fecha.isoformat() != vigente_desde:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Fecha de vigencia inválida: usar YYYY-MM-DD.") from None

    anterior = _version_vigente_en(conn, fijo_grupo_id, vigente_desde)
    if anterior is None:
        raise ValueError("La fecha de vigencia precede al inicio de la serie.")
    if not anterior["activo"]:
        raise ValueError("La serie está de baja en esa fecha; reactivarla está fuera de alcance.")
    nuevo_responsable = responsable if responsable is not None else anterior["responsable"]
    nuevo_nombre = nombre if nombre is not None else anterior["nombre"]
    nueva_periodicidad = periodicidad if periodicidad is not None else anterior["periodicidad"]
    nuevo_monto = monto_nuevo if monto_nuevo is not None else anterior["monto_estimado"]
    nuevo_tipo, nueva_proporcion = resolve_fixed_split(
        nuevo_responsable, tipo_proporcion, proporcion_jd, anterior
    )
    if (nuevo_nombre, nuevo_monto, nueva_periodicidad, nuevo_responsable,
            nuevo_tipo, nueva_proporcion) == (
            anterior["nombre"], anterior["monto_estimado"], anterior["periodicidad"],
            anterior["responsable"], anterior["tipo_proporcion"], anterior["proporcion_jd"]):
        raise FixedNoChangeError("La nueva versión no tiene cambios reales.")

    errores = validar_gasto_fijo(
        {
            "monto_estimado": nuevo_monto,
            "vigente_desde": vigente_desde,
            "responsable": nuevo_responsable,
            "nombre": nuevo_nombre,
            "periodicidad": nueva_periodicidad,
        }
    )
    if errores:
        raise ValueError(f"Nueva versión de gasto fijo inválida: {errores}")

    try:
        cursor = conn.execute(
            """INSERT INTO gastos_fijos
                (nombre, monto_estimado, periodicidad, dia_vencimiento, categoria,
                 subcategoria, activo, ultima_actualizacion, responsable,
                 tipo_proporcion, proporcion_jd, medio_pago, vigente_desde, fijo_grupo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nuevo_nombre, nuevo_monto, nueva_periodicidad, anterior["dia_vencimiento"],
             anterior["categoria"], anterior["subcategoria"], anterior["activo"],
             _now(), nuevo_responsable, nuevo_tipo,
             nueva_proporcion, anterior["medio_pago"], vigente_desde,
             fijo_grupo_id),
        )
        nuevo_id = cursor.lastrowid
        despues = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        _auditar_fijo(conn, nuevo_id, "version", actor, dict(anterior), despues)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return nuevo_id


def dar_baja_fijo(conn: sqlite3.Connection, gasto_fijo_id: int, fecha_baja: str, actor: str) -> int:
    """Cierra una serie con una nueva versión inactiva desde la fecha indicada."""
    referencia = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (gasto_fijo_id,)).fetchone()
    if referencia is None:
        raise ValueError(f"No existe ningún gasto fijo con id={gasto_fijo_id}.")
    try:
        fecha = date.fromisoformat(fecha_baja)
        if fecha.isoformat() != fecha_baja:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Fecha de baja inválida.")
    grupo = referencia["fijo_grupo_id"] or referencia["id"]
    actual = _version_vigente_en(conn, grupo, fecha_baja)
    if actual is None or not actual["activo"]:
        raise ValueError("La serie no está vigente en esa fecha.")
    if fecha_baja < max(row["vigente_desde"] for row in conn.execute(
        "SELECT vigente_desde FROM gastos_fijos WHERE fijo_grupo_id = ?", (grupo,)
    )):
        raise ValueError("La baja no puede preceder a una versión posterior.")
    try:
        cursor = conn.execute(
            """INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, dia_vencimiento, categoria, subcategoria,
             activo, ultima_actualizacion, responsable, tipo_proporcion, proporcion_jd,
             medio_pago, vigente_desde, fijo_grupo_id)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
            (actual["nombre"], actual["monto_estimado"], actual["periodicidad"],
             actual["dia_vencimiento"], actual["categoria"], actual["subcategoria"],
             _now(), actual["responsable"], actual["tipo_proporcion"],
             actual["proporcion_jd"], actual["medio_pago"], fecha_baja, grupo),
        )
        nuevo_id = cursor.lastrowid
        despues = dict(conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (nuevo_id,)).fetchone())
        _auditar_fijo(conn, nuevo_id, "baja", actor, actual, despues)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return nuevo_id


def historial_fijo(conn: sqlite3.Connection, fijo_grupo_id: int) -> list:
    """Versiones auditables; las desplazadas el mismo día no tienen intervalo."""
    filas = [dict(row) for row in conn.execute(
        "SELECT * FROM gastos_fijos WHERE fijo_grupo_id = ? ORDER BY vigente_desde, id",
        (fijo_grupo_id,),
    )]
    for index, fila in enumerate(filas):
        siguiente = filas[index + 1] if index + 1 < len(filas) else None
        mismo_dia = siguiente is not None and siguiente["vigente_desde"] == fila["vigente_desde"]
        fila["supersedida_mismo_dia"] = mismo_dia
        fila["tiene_intervalo_vigencia"] = not mismo_dia
        fila["vigente_hasta"] = (
            (date.fromisoformat(siguiente["vigente_desde"]) - timedelta(days=1)).isoformat()
            if siguiente is not None and not mismo_dia else None
        )
        fila["monto_mensual"] = monto_mensual(fila)
    return filas


def fijos_por_rango(conn: sqlite3.Connection, desde: str, hasta: str) -> list:
    """Series con los tramos históricos que intersectan el rango inclusivo."""
    try:
        inicio, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
        if inicio.isoformat() != desde or fin.isoformat() != hasta or inicio > fin:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Rango inválido: usar fechas YYYY-MM-DD con desde <= hasta.") from None
    resultado = []
    grupos = conn.execute("SELECT DISTINCT fijo_grupo_id FROM gastos_fijos ORDER BY fijo_grupo_id")
    for grupo in grupos:
        tramos = []
        for version in historial_fijo(conn, grupo["fijo_grupo_id"]):
            if not version["tiene_intervalo_vigencia"]:
                continue
            tramo_desde = max(desde, version["vigente_desde"])
            tramo_hasta = min(hasta, version["vigente_hasta"] or hasta)
            if tramo_desde <= tramo_hasta:
                tramos.append({**version, "desde": tramo_desde, "hasta": tramo_hasta})
        if tramos:
            resultado.append({"fijo_grupo_id": grupo["fijo_grupo_id"], "tramos": tramos})
    return resultado


def unificar_series_fijos(conn: sqlite3.Connection, ids: list, actor: str,
                          *, commit: bool = True) -> int:
    """Une series. Con `commit=False`, el llamador gestiona la transacción completa."""
    if not ids or any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        raise ValueError("Se requiere una lista de ids enteros.")
    ids = sorted(set(ids))
    filas = conn.execute(
        f"SELECT * FROM gastos_fijos WHERE id IN ({','.join('?' for _ in ids)})", ids
    ).fetchall()
    if len(filas) != len(ids):
        raise ValueError("Uno o más ids de gasto fijo no existen.")
    grupos = sorted({fila["fijo_grupo_id"] for fila in filas})
    todas = [dict(row) for row in conn.execute(
        f"SELECT * FROM gastos_fijos WHERE fijo_grupo_id IN ({','.join('?' for _ in grupos)})",
        grupos,
    )]
    destino = min(ids)
    if all(fila["fijo_grupo_id"] == destino for fila in todas):
        return destino
    # `id` es clave primaria; por lo tanto (vigente_desde, id) es único.
    claves = [(fila["vigente_desde"], fila["id"]) for fila in todas]
    if len(set(claves)) != len(claves):
        raise ValueError("La unificación dejaría versiones ambiguas.")
    try:
        for antes in todas:
            if antes["fijo_grupo_id"] == destino:
                continue
            conn.execute("UPDATE gastos_fijos SET fijo_grupo_id = ? WHERE id = ?", (destino, antes["id"]))
            despues = {**antes, "fijo_grupo_id": destino}
            _auditar_fijo(conn, antes["id"], "unificar", actor, antes, despues)
    except Exception:
        if commit:
            conn.rollback()
        raise
    if commit:
        conn.commit()
    return destino


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
    try:
        fecha_normalizada = date.fromisoformat(fecha)
        if fecha_normalizada.isoformat() != fecha:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Fecha inválida: usar YYYY-MM-DD.") from None

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


def _migrar_columnas_ingresos(conn: sqlite3.Connection) -> None:
    """Agrega a `ingresos` las columnas de soft delete si faltan (t_ce790609).

    Mismo patrón que `_migrar_columnas_gastos`: ALTER TABLE ADD COLUMN en
    vez de recrear la tabla, para no perder datos en bases ya inicializadas.
    Idempotente: correrla dos veces (ej. sobre una base que ya la tiene
    aplicada) no vuelve a tocar las columnas existentes.
    """
    existentes = _column_names(conn, "ingresos")
    columnas_nuevas = (
        ("deleted_at", "TEXT"),
        ("deleted_by", "TEXT"),
        # Telegram (brief S2/S3, T1): a diferencia de `gastos`, `ingresos`
        # no tenía ninguna columna de Telegram todavía -- se agregan las
        # tres (incluido `chat_id`) de una.
        ("chat_id", "TEXT"),
        ("telegram_user_id", "TEXT"),
        ("telegram_message_id", "TEXT"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE ingresos ADD COLUMN {columna} {definicion}")
    conn.commit()


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


def get_ingresos(
    conn: sqlite3.Connection,
    mes: Optional[str] = None,
    incluir_borrados: bool = False,
) -> list:
    """Devuelve ingresos ordenados por id.

    Por default excluye los ingresos con `deleted_at IS NOT NULL` (soft
    delete, ver `eliminar_ingreso_logico`). Pasar `incluir_borrados=True`
    para incluirlos también (p.ej. para una vista de auditoría/papelera).
    """
    condiciones = []
    parametros: list = []
    if mes is not None:
        condiciones.append("substr(fecha, 1, 7) = ?")
        parametros.append(mes)
    if not incluir_borrados:
        condiciones.append("deleted_at IS NULL")

    where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    rows = conn.execute(f"SELECT * FROM ingresos{where} ORDER BY id", parametros).fetchall()
    return [dict(row) for row in rows]


def actualizar_ingreso(conn: sqlite3.Connection, ingreso_id: int, cambios: dict) -> None:
    """Edición parcial de un ingreso existente.

    Campos editables: fecha/monto/moneda/categoria/persona/descripcion_original.
    Valida el estado RESULTANTE (fila actual + `cambios` superpuestos) con
    `validar_ingreso` antes de aplicar nada — si la validación falla, no se
    ejecuta ningún UPDATE. Lanza `ValueError` si el ingreso no existe, si ya
    está borrado lógicamente (ver `eliminar_ingreso_logico` — un ingreso de
    la papelera no se edita, se debe restaurar explícitamente primero, lo
    que hoy no existe), si la validación falla, si `cambios` trae alguna
    clave fuera de las editables, o si `cambios` está vacío (rechazado
    explícitamente — con `cambios={}` el `UPDATE ingresos SET  WHERE id = ?`
    resultante es SQL inválido; hallazgo de revisor independiente, run
    3b184396, hallazgo 7).
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
    if fila["deleted_at"] is not None:
        raise ValueError(f"No se puede editar el ingreso id={ingreso_id}: está borrado.")

    resultante = {**dict(fila), **cambios}
    errores = validar_ingreso(resultante)
    if errores:
        raise ValueError(f"Edición de ingreso inválida: {errores}")

    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = list(cambios.values()) + [ingreso_id]
    conn.execute(f"UPDATE ingresos SET {columnas} WHERE id = ?", valores)
    conn.commit()


# --- Soft delete de ingresos + auditoría ------------------------------------


def eliminar_ingreso_logico(conn: sqlite3.Connection, ingreso_id: int, actor: str) -> None:
    """Marca `ingresos.id = ingreso_id` como borrado lógico (soft delete).

    Mismo contrato que `eliminar_gasto_logico` (ver esa función para el
    detalle de atomicidad y de la condición de carrera): no borra la fila
    físicamente, deja rastro en `auditoria` con el snapshot previo de la
    fila, y levanta `ValueError` si el ingreso no existe o ya estaba
    borrado — incluyendo el caso de doble baja concurrente, detectado por
    `cursor.rowcount != 1` en el `UPDATE` condicionado a `deleted_at IS
    NULL`. Si falla el `INSERT` en `auditoria` después del `UPDATE`, se
    hace `rollback()` explícito antes de propagar la excepción.
    """
    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    if fila is None:
        raise ValueError(f"No existe ningún ingreso con id={ingreso_id}.")
    if fila["deleted_at"] is not None:
        raise ValueError(f"El ingreso id={ingreso_id} ya está borrado.")

    snapshot_antes = json.dumps(dict(fila), ensure_ascii=False)
    ahora = _now()

    try:
        cursor = conn.execute(
            "UPDATE ingresos SET deleted_at = ?, deleted_by = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (ahora, actor, ingreso_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"El ingreso id={ingreso_id} ya fue borrado por otra operación "
                "concurrente (detectado al aplicar la baja)."
            )
        conn.execute(
            """
            INSERT INTO auditoria (tabla, fila_id, accion, actor, antes_json, despues_json, creado_en)
            VALUES ('ingresos', ?, 'baja', ?, ?, NULL, ?)
            """,
            (ingreso_id, actor, snapshot_antes, ahora),
        )
    except Exception:
        conn.rollback()
        raise
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
    """Devuelve {'JD': pct, 'Pinki': pct} para `mes`, o None si no hay salarios.

    Excluye ingresos borrados lógicamente (`deleted_at IS NOT NULL`, ver
    `eliminar_ingreso_logico`) — un ingreso borrado no debe afectar la
    proporción del mes.
    """
    rows = conn.execute(
        "SELECT persona, SUM(monto) AS total FROM ingresos "
        "WHERE categoria = 'Salario' AND substr(fecha, 1, 7) = ? "
        "AND deleted_at IS NULL "
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
      1. Suma `ingresos` con categoria='Salario' del mes, agrupado por
         persona (excluyendo ingresos borrados lógicamente, ver
         `eliminar_ingreso_logico`).
      2. Si el mes no tiene salarios cargados, usa la proporción del último
         mes ANTERIOR que sí tenga (fallback explícito del modelo real,
         también excluyendo borrados).
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
                "SELECT fecha FROM ingresos WHERE categoria = 'Salario' "
                "AND deleted_at IS NULL"
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


# --- Telegram: altas con comprobante en la misma transacción ----------------


class ComprobanteDuplicadoError(ValueError):
    """`hash_archivo` ya registrado en `comprobantes_telegram`; ninguna
    escritura (gasto/ingreso ni comprobante) se aplicó -- ver
    `insert_gasto_telegram`/`insert_ingreso_telegram`."""


def _insertar_gasto_expandido_tx(conn: sqlite3.Connection, gasto: dict, cuotas_total: int) -> list:
    """Variante de `insert_gasto_con_cuotas` SIN commit/rollback propio, para
    uso interno de `insert_gasto_telegram` -- el caller controla la
    transacción completa (tiene que compartirla con la inserción opcional
    de `comprobantes_telegram`). Misma validación y expansión de cuotas que
    `insert_gasto_con_cuotas`; no delega en esa función ni en `insert_gasto`
    (ambas hacen su propio `commit`) para no romper la atomicidad que exige
    el brief S2/S3. Devuelve la lista de ids insertados (longitud 1 si no
    hay cuotas).
    """
    if cuotas_total is None:
        cuotas_total = 1
    if (
        not isinstance(cuotas_total, int)
        or isinstance(cuotas_total, bool)
        or not 1 <= cuotas_total <= 120
    ):
        raise ValueError(
            f"cuotas_total debe ser un entero entre 1 y 120 (recibido {cuotas_total!r})."
        )
    if gasto.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un gasto sin confirmación explícita "
            "(confirmado debe ser True)."
        )
    if cuotas_total == 1:
        return [_insert_gasto_tx(conn, gasto)]

    montos_centavos = _repartir_cuotas_centavos(gasto["monto"], cuotas_total)
    fecha_base = (gasto.get("fecha") or _now())[:10]

    ids = []
    cuota_ref = None
    for numero, centavos in enumerate(montos_centavos, start=1):
        gasto_cuota = dict(gasto)
        gasto_cuota["monto"] = float(Decimal(centavos) / 100)
        gasto_cuota["fecha"] = _sumar_meses(fecha_base, numero - 1)
        gasto_cuota["cuotas_total"] = cuotas_total
        gasto_cuota["cuota_nro"] = numero
        gasto_cuota["cuota_ref"] = cuota_ref
        nuevo_id = _insert_gasto_tx(
            conn, gasto_cuota, monto_total_original=gasto["monto"]
        )
        if cuota_ref is None:
            cuota_ref = nuevo_id
            conn.execute("UPDATE gastos SET cuota_ref = ? WHERE id = ?", (cuota_ref, nuevo_id))
        ids.append(nuevo_id)
    return ids


def _insert_comprobante_tx(
    conn: sqlite3.Connection,
    comprobante: dict,
    *,
    chat_id: Optional[str] = None,
    telegram_user_id: Optional[str] = None,
    telegram_message_id: Optional[str] = None,
    gasto_id: Optional[int] = None,
    ingreso_id: Optional[int] = None,
) -> int:
    """Inserta una fila en `comprobantes_telegram`, SIN commit propio (el
    caller controla la transacción). Levanta `ComprobanteDuplicadoError` si
    `hash_archivo` ya existe, sin insertar nada -- el chequeo previo evita
    depender únicamente de la excepción de SQLite por la columna `UNIQUE`,
    para poder distinguirla de cualquier otro `sqlite3.IntegrityError`.
    """
    hash_archivo = comprobante.get("hash_archivo")
    existente = conn.execute(
        "SELECT id FROM comprobantes_telegram WHERE hash_archivo = ?", (hash_archivo,)
    ).fetchone()
    if existente is not None:
        raise ComprobanteDuplicadoError(
            f"Ya existe un comprobante con hash_archivo={hash_archivo!r}."
        )
    cursor = conn.execute(
        """
        INSERT INTO comprobantes_telegram
            (hash_archivo, chat_id, telegram_user_id, telegram_message_id,
             texto_extraido, monto_detectado, fecha_detectada, comercio_detectado,
             ruta_archivo, nro_operacion, gasto_id, ingreso_id, creado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_archivo,
            chat_id,
            telegram_user_id,
            telegram_message_id,
            comprobante.get("texto_extraido"),
            comprobante.get("monto_detectado"),
            comprobante.get("fecha_detectada"),
            comprobante.get("comercio_detectado"),
            comprobante.get("ruta_archivo"),
            comprobante.get("nro_operacion"),
            gasto_id,
            ingreso_id,
            (datetime.fromisoformat(comprobante["received_at"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
             if comprobante.get("received_at") else _now()),
        ),
    )
    return cursor.lastrowid


def insert_gasto_telegram(
    conn: sqlite3.Connection,
    gasto: dict,
    cuotas_total: int,
    comprobante: Optional[dict] = None,
) -> dict:
    """Inserta un gasto de origen Telegram (con cuotas opcionales) y, si
    viene, su comprobante vinculado -- TODO en una sola transacción (brief
    S2/S3, punto 2): un hash de comprobante duplicado revierte el gasto y
    sus cuotas sin dejar nada creado (`ComprobanteDuplicadoError`).

    Devuelve `{'gasto_ids': [...], 'comprobante_id': int|None}`.
    """
    errores = validar_telegram_expense(gasto)
    if errores:
        raise ValueError(f"Gasto Telegram inválido: {errores}")
    try:
        gasto_ids = _insertar_gasto_expandido_tx(conn, gasto, cuotas_total)
        comprobante_id = None
        if comprobante:
            comprobante_id = _insert_comprobante_tx(
                conn, comprobante,
                chat_id=gasto.get("chat_id"),
                telegram_user_id=gasto.get("telegram_user_id"),
                telegram_message_id=gasto.get("telegram_message_id"),
                gasto_id=gasto_ids[0],
            )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return {"gasto_ids": gasto_ids, "comprobante_id": comprobante_id}


def insert_ingreso_telegram(
    conn: sqlite3.Connection, ingreso: dict, comprobante: Optional[dict] = None,
) -> dict:
    """Inserta un ingreso de origen Telegram y, si viene, su comprobante
    vinculado, en una sola transacción -- mismo contrato que
    `insert_gasto_telegram` para ingresos.

    Devuelve `{'ingreso_id': int, 'comprobante_id': int|None}`.
    """
    if ingreso.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un ingreso sin confirmación explícita "
            "(confirmado debe ser True)."
        )
    errores = validar_telegram_ingreso(ingreso)
    if errores:
        raise ValueError(f"Ingreso inválido: {errores}")

    try:
        cursor = conn.execute(
            """
            INSERT INTO ingresos
                (fecha, monto, moneda, categoria, persona, descripcion_original,
                 origen, confirmado, created_at, chat_id, telegram_user_id,
                 telegram_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ingreso.get("chat_id"),
                ingreso.get("telegram_user_id"),
                ingreso.get("telegram_message_id"),
            ),
        )
        ingreso_id = cursor.lastrowid
        comprobante_id = None
        if comprobante:
            comprobante_id = _insert_comprobante_tx(
                conn, comprobante,
                chat_id=ingreso.get("chat_id"),
                telegram_user_id=ingreso.get("telegram_user_id"),
                telegram_message_id=ingreso.get("telegram_message_id"),
                ingreso_id=ingreso_id,
            )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return {"ingreso_id": ingreso_id, "comprobante_id": comprobante_id}


def buscar_comprobante_dedupe(
    conn: sqlite3.Connection,
    hash_archivo: str,
    monto: Optional[float] = None,
    fecha: Optional[str] = None,
    comercio: Optional[str] = None,
    nro_operacion: Optional[str] = None,
) -> dict:
    """Busca si `hash_archivo` (o, en su defecto, un comprobante aproximado)
    ya fue registrado en `comprobantes_telegram` -- caso "mismo comprobante
    reenviado con nombre de archivo distinto" (brief S2/S3, punto 2).

    1. Coincidencia exacta de `hash_archivo`: la más fuerte, se prueba
       siempre primero.
    2. Si no hay coincidencia de hash y se pasa `nro_operacion`:
       coincidencia exacta por número de operación bancaria (brief t_a3f2bbb5
       -- un comprobante de transferencia reenviado como foto distinta pero
       con el mismo número de operación es inequívocamente el mismo
       movimiento, aunque no coincida ni el hash del archivo ni monto/fecha
       si alguno de los dos se tipeó distinto).
    3. Si no hay coincidencia de hash ni de operación y se pasan `monto` y
       `fecha`: coincidencia aproximada = mismo `monto_detectado` (±0,01) y
       `fecha_detectada` dentro de ±1 día; `comercio` solo filtra si se
       pasa (ver brief -- no todos los comprobantes traen comercio
       detectado).

    Devuelve `{'duplicado': bool, 'gasto_id': int|None, 'ingreso_id':
    int|None, 'coincidencia': 'hash'|'operacion'|'aproximada'|None}`.
    """
    fila_hash = conn.execute(
        "SELECT gasto_id, ingreso_id FROM comprobantes_telegram WHERE hash_archivo = ?",
        (hash_archivo,),
    ).fetchone()
    if fila_hash is not None:
        return {
            "duplicado": True,
            "gasto_id": fila_hash["gasto_id"],
            "ingreso_id": fila_hash["ingreso_id"],
            "coincidencia": "hash",
        }

    if nro_operacion:
        fila_operacion = conn.execute(
            "SELECT gasto_id, ingreso_id FROM comprobantes_telegram WHERE nro_operacion = ?",
            (nro_operacion,),
        ).fetchone()
        if fila_operacion is not None:
            return {
                "duplicado": True,
                "gasto_id": fila_operacion["gasto_id"],
                "ingreso_id": fila_operacion["ingreso_id"],
                "coincidencia": "operacion",
            }

    if monto is None or fecha is None:
        return {"duplicado": False, "gasto_id": None, "ingreso_id": None, "coincidencia": None}

    fecha_dt = date.fromisoformat(fecha)
    desde = (fecha_dt - timedelta(days=1)).isoformat()
    hasta = (fecha_dt + timedelta(days=1)).isoformat()

    # Comparación en centavos enteros (hallazgo 2 del revisor run 65c69e0c):
    # `ABS(monto_detectado - ?) <= 0.01` fallaba en parte del límite inclusivo
    # por error de coma flotante (ej. 1.02 vs 1.01 daba 0.010000000000000009,
    # mayor a 0.01). Redondear ambos montos a centavos antes de restar hace
    # la comparación exacta en aritmética entera.
    condiciones = [
        "monto_detectado IS NOT NULL",
        "ABS(CAST(ROUND(monto_detectado * 100) AS INTEGER) - CAST(ROUND(? * 100) AS INTEGER)) <= 1",
        "fecha_detectada IS NOT NULL",
        "fecha_detectada BETWEEN ? AND ?",
    ]
    parametros = [monto, desde, hasta]
    if comercio is not None:
        condiciones.append("comercio_detectado = ?")
        parametros.append(comercio)

    fila_aprox = conn.execute(
        f"SELECT gasto_id, ingreso_id FROM comprobantes_telegram "
        f"WHERE {' AND '.join(condiciones)} ORDER BY id LIMIT 1",
        parametros,
    ).fetchone()
    if fila_aprox is not None:
        return {
            "duplicado": True,
            "gasto_id": fila_aprox["gasto_id"],
            "ingreso_id": fila_aprox["ingreso_id"],
            "coincidencia": "aproximada",
        }
    return {"duplicado": False, "gasto_id": None, "ingreso_id": None, "coincidencia": None}


def limpiar_texto_comprobantes_vencidos(
    conn: sqlite3.Connection, *, ahora: Optional[datetime] = None, apply: bool = False,
) -> dict:
    """Limpia solo texto extraído de comprobantes recibidos hace >=40 días.

    Función acotada para integrar desde la API; no se invoca automáticamente.
    Conserva hash, número de operación y vínculos contables. `creado_en` es
    la fecha de recepción en UTC, nunca la fecha impresa `fecha_detectada`.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        raise ValueError("ahora debe tener zona horaria")
    limite = (ahora.astimezone(timezone.utc) - timedelta(days=40)).isoformat()
    condicion = "texto_extraido IS NOT NULL AND creado_en <= ?"
    cantidad = conn.execute(
        f"SELECT COUNT(*) FROM comprobantes_telegram WHERE {condicion}", (limite,),
    ).fetchone()[0]
    if apply and cantidad:
        with conn:
            conn.execute(
                f"UPDATE comprobantes_telegram SET texto_extraido = NULL WHERE {condicion}",
                (limite,),
            )
    return {"candidatos": cantidad, "limite_recepcion": limite, "aplicado": bool(apply)}


# --- Avisos de crédito (S3) --------------------------------------------------

UMBRAL_CREDITO_BASE = 100000
UMBRAL_CREDITO_PASO = 50000


def _total_credito_mes_centavos(conn: sqlite3.Connection, mes: str) -> int:
    """Igual que `total_credito_mes`, pero en centavos enteros.

    Hallazgo 1 del revisor run 65c69e0c: sumar `gastos.monto` directo como
    `REAL` puede perder un umbral alcanzado exactamente por error de coma
    flotante (ej. 353.34 + 72252.93 + 27393.73 = 100000.00 exacto, pero
    SQLite devuelve 99999.99999999999 sumando los `REAL` tal cual). Cada
    monto se redondea a centavos ANTES de sumar, así la suma es exacta en
    aritmética entera.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(CAST(ROUND(monto * 100) AS INTEGER)), 0) AS total_centavos "
        "FROM gastos WHERE medio_pago = 'Crédito' AND deleted_at IS NULL "
        "AND substr(fecha, 1, 7) = ?",
        (mes,),
    ).fetchone()
    return int(row["total_centavos"])


def total_credito_mes(conn: sqlite3.Connection, mes: str) -> float:
    """Suma `gastos.monto` con `medio_pago='Crédito'`, `deleted_at IS NULL`
    y mes calendario `mes` ('YYYY-MM') -- cada cuota ya es su propia fila
    con su propia fecha (ver `insert_gasto_con_cuotas`), así que este total
    ya refleja lo que cae ese mes sin trabajo adicional (brief S2/S3,
    punto 1; DECISIONES.md punto 2: mes calendario, no ciclo de cierre).

    La suma se calcula en centavos enteros (ver `_total_credito_mes_centavos`)
    y se devuelve en pesos, redondeada a 2 decimales.
    """
    return round(_total_credito_mes_centavos(conn, mes) / 100, 2)


def detectar_umbrales_credito(conn: sqlite3.Connection, mes: str) -> dict:
    """Detecta los umbrales de crédito (100000 + 50000·n) cruzados por el
    total de `mes` que todavía no estén registrados en `avisos_credito`,
    los registra con `enviado_en=NULL` (esta API solo DETECTA; el envío y
    el marcado como enviado los hace Lasso vía
    `/api/avisos-credito/marcar-enviados` -- cambio respecto del CTO
    66f52e78, ver DECISIONES.md) y devuelve los nuevos junto con el total.

    Nunca borra ni re-registra un umbral ya existente para ese mes, aunque
    el total baje y vuelva a subir (evita flapping, DECISIONES.md punto 8):
    un umbral solo se registra la primera vez que se detecta cruzado.

    La comparación contra los umbrales se hace en centavos enteros (ver
    `_total_credito_mes_centavos` y hallazgo 1 del revisor run 65c69e0c):
    comparar el total sumado como `REAL` directamente contra `100000` podía
    omitir un umbral alcanzado exactamente por error de coma flotante.
    `avisos_credito.umbral` sigue guardando pesos enteros, igual que antes.

    Devuelve `{'total': float, 'nuevos': [{'mes', 'umbral', 'total'}, ...]}`.
    """
    total_centavos = _total_credito_mes_centavos(conn, mes)
    total = round(total_centavos / 100, 2)
    base_centavos = UMBRAL_CREDITO_BASE * 100
    paso_centavos = UMBRAL_CREDITO_PASO * 100
    if total_centavos < base_centavos:
        return {"total": total, "nuevos": []}

    umbral_maximo_centavos = base_centavos + paso_centavos * int(
        (total_centavos - base_centavos) // paso_centavos
    )
    candidatos_centavos = range(base_centavos, umbral_maximo_centavos + 1, paso_centavos)

    existentes = {
        row["umbral"]
        for row in conn.execute(
            "SELECT umbral FROM avisos_credito WHERE mes = ?", (mes,)
        ).fetchall()
    }

    nuevos = []
    ahora = _now()
    for umbral_centavos in candidatos_centavos:
        umbral = umbral_centavos // 100
        if umbral in existentes:
            continue
        try:
            conn.execute(
                """
                INSERT INTO avisos_credito (mes, umbral, total_al_detectar, detectado_en, enviado_en)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (mes, umbral, total, ahora),
            )
        except sqlite3.IntegrityError:
            # Ya lo registró una corrida concurrente entre el SELECT de
            # `existentes` y este INSERT; no es un umbral nuevo para
            # nosotros, no se vuelve a contar ni se re-lanza el error.
            continue
        nuevos.append({"mes": mes, "umbral": umbral, "total": total})
    conn.commit()
    return {"total": total, "nuevos": nuevos}


def avisos_credito_pendientes(conn: sqlite3.Connection) -> list:
    """Avisos de crédito detectados y todavía no marcados como enviados
    (`enviado_en IS NULL`) -- los que Lasso tiene que mandar."""
    rows = conn.execute(
        "SELECT * FROM avisos_credito WHERE enviado_en IS NULL ORDER BY mes, umbral"
    ).fetchall()
    return [dict(row) for row in rows]


def marcar_avisos_credito_enviados(conn: sqlite3.Connection, items: list) -> list:
    """Marca `enviado_en` = ahora para cada `{'mes', 'umbral'}` de `items`
    que exista y todavía no esté marcado. Idempotente: un item ya marcado,
    o uno que no existe, simplemente no se cuenta entre los actualizados en
    esta llamada -- no levanta error, para que Lasso pueda reintentar un
    lote sin chequear primero cuáles ya mandó.

    Devuelve la lista de items efectivamente actualizados en esta llamada.
    """
    ahora = _now()
    actualizados = []
    for item in items:
        mes = item.get("mes")
        umbral = item.get("umbral")
        cursor = conn.execute(
            "UPDATE avisos_credito SET enviado_en = ? "
            "WHERE mes = ? AND umbral = ? AND enviado_en IS NULL",
            (ahora, mes, umbral),
        )
        if cursor.rowcount == 1:
            actualizados.append({"mes": mes, "umbral": umbral})
    conn.commit()
    return actualizados
