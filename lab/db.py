"""Capa de acceso a SQLite para el bot Lasso (Fases 1 y 3).

Tablas (esquema reconciliado con LIFE-lab-propuesta.md sección 3):
    - gastos: registros de gastos ("Log" en el documento aprobado). Extendido
      en esta tarea con `tarjeta_id`, `tipo_proporcion`, `proporcion_jd` y
      `proporcion_pinki` — ver README sección "Tarjetas y reparto".
    - tarjetas: catálogo de tarjetas (crédito/débito), portado de la hoja
      `Tarjetas` del sistema real (ver README).
    - estado_conversacional: estado del flujo multi-turno por chat_id.
    - recetas / receta_ingredientes: recetario de ejemplo (Fase 3).
    - inventario_bienes: bienes del hogar (Fase 3, sin lógica de negocio
      todavía — solo CRUD básico, ver README).
    - inventario_cocina: stock de ingredientes disponibles (Fase 3).
    - lista_compras: items pendientes de comprar (Fase 3).

Principio no negociable: `insert_gasto` rechaza cualquier intento de
insertar un registro que no venga marcado como `confirmado=True`. La
confirmación explícita del usuario se resuelve en `conversation.py`;
esta capa la vuelve a exigir como segunda barrera.
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
             proporcion_pinki)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
