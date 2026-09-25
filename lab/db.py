"""Capa de acceso a SQLite para el bot Lasso (Fases 1, 3 y Finanzas completo).

Tablas (esquema reconciliado con LIFE-lab-propuesta.md sección 3):
    - gastos: registros de gastos ("Log" en el documento aprobado). Extendido
      con `tarjeta_id`, `tipo_proporcion`, `proporcion_jd`, `proporcion_pinki`
      (tarjetas/reparto) y `cuotas_total`, `cuota_nro`, `cuota_ref` (cuotas,
      ver README sección "Cuotas").
    - tarjetas: catálogo de tarjetas (crédito/débito), portado de la hoja
      `Tarjetas` del sistema real (ver README).
    - categorias: catálogo dinámico de categorías/subcategorías (Gasto /
      Ingreso / Inversión), sembrado desde `seed_categorias.py` pero
      extensible en caliente vía `crear_categoria_si_no_existe` (ver README).
    - gastos_fijos: catálogo de gastos recurrentes (alquiler, expensas, etc.),
      portado de la hoja `GastosFijos` del sistema real.
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
from pathlib import Path
from typing import Optional

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
    """Agrega a `gastos` las columnas de tarjetas/reparto si faltan.

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
    """Agrega a `gastos_fijos` las columnas de responsable/reparto si faltan.

    Mismo patrón que `_migrar_columnas_gastos`: ALTER TABLE ADD COLUMN en
    vez de recrear la tabla, para no perder datos en bases ya inicializadas.
    """
    existentes = _column_names(conn, "gastos_fijos")
    columnas_nuevas = (
        ("responsable", "TEXT"),
        ("tipo_proporcion", "TEXT"),
        ("proporcion_jd", "REAL"),
        ("medio_pago", "TEXT"),
    )
    for columna, definicion in columnas_nuevas:
        if columna not in existentes:
            conn.execute(f"ALTER TABLE gastos_fijos ADD COLUMN {columna} {definicion}")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_gasto(conn: sqlite3.Connection, gasto: dict) -> int:
    """Inserta un gasto. Exige `gasto['confirmado'] is True`.

    Este chequeo es deliberado y redundante con la máquina de estados de
    `conversation.py`: el bot nunca debe escribir en la base sin
    confirmación explícita del usuario, sin excepciones.

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
        - cuotas_total: default 1.
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

    tipo_proporcion = gasto.get("tipo_proporcion") or "dinamico"
    proporcion_jd = gasto.get("proporcion_jd")
    proporcion_pinki = gasto.get("proporcion_pinki")

    if tipo_proporcion == "custom":
        if proporcion_jd is None or proporcion_pinki is None:
            raise ValueError(
                "tipo_proporcion='custom' requiere proporcion_jd y "
                "proporcion_pinki explícitas."
            )
        if abs((proporcion_jd + proporcion_pinki) - 100) > 0.01:
            raise ValueError(
                "proporcion_jd + proporcion_pinki debe sumar 100 "
                f"(recibido {proporcion_jd} + {proporcion_pinki})."
            )
    elif tipo_proporcion == "dinamico":
        if proporcion_jd is not None or proporcion_pinki is not None:
            raise ValueError(
                "tipo_proporcion='dinamico' no debe traer proporcion_jd/"
                "proporcion_pinki (el reparto se calcula por fuera)."
            )
    else:
        raise ValueError(
            f"tipo_proporcion inválido: {tipo_proporcion!r} "
            "(usar 'dinamico' o 'custom')."
        )

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
            gasto.get("cuotas_total") or 1,
            gasto.get("cuota_nro") or 1,
            gasto.get("cuota_ref"),
            gasto.get("saldado"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_gastos(conn: sqlite3.Connection, chat_id: Optional[str] = None) -> list:
    if chat_id is not None:
        rows = conn.execute(
            "SELECT * FROM gastos WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM gastos ORDER BY id").fetchall()
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

    - `cuotas_total <= 1`: idéntico a `insert_gasto` (devuelve un solo id).
    - `cuotas_total > 1`: inserta `cuotas_total` filas, una por mes
      consecutivo a partir de la fecha del gasto. Cada fila tiene
      `monto = monto_total / cuotas_total`, `cuota_nro` de 1 a N, y
      `cuota_ref` = id de la primera fila (incluida ella misma). El resto
      de los campos (categoría, tarjeta, tipo_proporcion, pagado_por, etc.)
      se hereda igual en todas las cuotas. Devuelve la lista de ids
      insertados, en orden.
    """
    cuotas_total = int(cuotas_total) if cuotas_total else 1
    if cuotas_total <= 1:
        return insert_gasto(conn, gasto)

    monto_total = gasto["monto"]
    monto_cuota = monto_total / cuotas_total
    fecha_base = (gasto.get("fecha") or _now())[:10]

    ids = []
    cuota_ref = None
    for numero in range(1, cuotas_total + 1):
        gasto_cuota = dict(gasto)
        gasto_cuota["monto"] = monto_cuota
        gasto_cuota["fecha"] = _sumar_meses(fecha_base, numero - 1)
        gasto_cuota["cuotas_total"] = cuotas_total
        gasto_cuota["cuota_nro"] = numero
        gasto_cuota["cuota_ref"] = cuota_ref
        nuevo_id = insert_gasto(conn, gasto_cuota)
        if cuota_ref is None:
            cuota_ref = nuevo_id
            conn.execute(
                "UPDATE gastos SET cuota_ref = ? WHERE id = ?", (cuota_ref, nuevo_id)
            )
            conn.commit()
        ids.append(nuevo_id)
    return ids


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
    """Inserta un gasto fijo.

    Campos de responsable/reparto (retrocompatibles — default NULL si no se
    pasan, igual que antes de esta extensión):
        - responsable: 'Común' / 'JD' / 'Pinki', tal cual viene del Excel.
        - tipo_proporcion: 'dinamica' / 'custom' / None; solo relevante si
          responsable='Común'.
        - proporcion_jd: solo si tipo_proporcion='custom'.
        - medio_pago: informativo.
    """
    cursor = conn.execute(
        """
        INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, dia_vencimiento, categoria,
             subcategoria, activo, ultima_actualizacion, responsable,
             tipo_proporcion, proporcion_jd, medio_pago)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gasto_fijo["nombre"],
            gasto_fijo["monto_estimado"],
            gasto_fijo["periodicidad"],
            gasto_fijo.get("dia_vencimiento"),
            gasto_fijo.get("categoria"),
            gasto_fijo.get("subcategoria"),
            1 if gasto_fijo.get("activo", True) else 0,
            gasto_fijo.get("ultima_actualizacion") or _now(),
            gasto_fijo.get("responsable"),
            gasto_fijo.get("tipo_proporcion"),
            gasto_fijo.get("proporcion_jd"),
            gasto_fijo.get("medio_pago"),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_gastos_fijos(conn: sqlite3.Connection, solo_activos: bool = True) -> list:
    if solo_activos:
        rows = conn.execute(
            "SELECT * FROM gastos_fijos WHERE activo = 1 ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM gastos_fijos ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def actualizar_monto_fijo(
    conn: sqlite3.Connection, gasto_fijo_id: int, monto_nuevo: float
) -> None:
    conn.execute(
        "UPDATE gastos_fijos SET monto_estimado = ?, ultima_actualizacion = ? "
        "WHERE id = ?",
        (monto_nuevo, _now(), gasto_fijo_id),
    )
    conn.commit()


# --- Ingresos ----------------------------------------------------------------


def insert_ingreso(conn: sqlite3.Connection, ingreso: dict) -> int:
    """Inserta un ingreso. Exige `ingreso['confirmado'] is True`.

    Mismo principio no negociable que `insert_gasto`.
    """
    if ingreso.get("confirmado") is not True:
        raise ValueError(
            "No se puede insertar un ingreso sin confirmación explícita "
            "(confirmado debe ser True)."
        )
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

    Es un cálculo derivado, no una tabla propia: recorre `gastos` del mes
    con `pagado_por` en ('JD', 'Pinki') (los pagados por 'Común' no generan
    deuda) y, para cada uno, determina cuánto le correspondía pagar al que
    NO puso la plata:
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
        "AND pagado_por IN ('JD', 'Pinki')",
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

    Se basa pura y exclusivamente en la columna `saldado` de los gastos que
    generan deuda ese mes (`pagado_por` en JD/Pinki) — no en si el saldo neto
    calculado da 0, que es un cálculo aparte (`calcular_deudas_mes`).

    Devuelve:
      - 'sin_deuda': no hubo gastos de JD/Pinki ese mes.
      - 'pendiente': ninguno de esos gastos está saldado.
      - 'saldado': todos están saldados.
      - 'parcial': mezcla de saldados y pendientes.
    """
    rows = conn.execute(
        "SELECT saldado FROM gastos WHERE substr(fecha, 1, 7) = ? "
        "AND pagado_por IN ('JD', 'Pinki')",
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
    puntual), esta función recorre TODOS los gastos con `pagado_por` en
    ('JD', 'Pinki') que tengan `saldado IS NULL` — sin importar de qué mes
    sean — porque a Juan solo le interesa la deuda pendiente real, no el
    histórico ya saldado (ver brief). `gastos` no tiene columna `borrado`
    (los borrados ya se excluyen en la migración), así que no hace falta
    filtrarlos acá.

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
            "AND saldado IS NULL AND fecha <= ?",
            (_ultimo_dia_mes(hasta_mes),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM gastos WHERE pagado_por IN ('JD', 'Pinki') "
            "AND saldado IS NULL"
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
