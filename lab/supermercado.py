"""Stock de supermercado aislado del inventario y las recetas legacy."""
import json
import math
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

ACTOR = "sesion_compartida:no_verificado"
MAX_QUANTITY = Decimal("1000000000")
MAX_PRODUCTS = 1000
MAX_CATEGORIES = 100
HISTORY_PAGE_SIZE = 50


class VersionConflict(Exception):
    pass


class CapacityExceeded(Exception):
    pass


def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supermercado_categorias (
        id INTEGER PRIMARY KEY, nombre TEXT NOT NULL COLLATE NOCASE,
        orden INTEGER NOT NULL CHECK(orden >= 0), deleted_at TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS supermercado_categorias_nombre_activo ON supermercado_categorias(nombre COLLATE NOCASE) WHERE deleted_at IS NULL;
    CREATE TABLE IF NOT EXISTS supermercado_productos (
        id INTEGER PRIMARY KEY, categoria_id INTEGER REFERENCES supermercado_categorias(id),
        producto TEXT NOT NULL, unidad TEXT NOT NULL,
        stock_deseado TEXT NOT NULL, stock_actual TEXT NOT NULL,
        deleted_at TEXT, version INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS supermercado_auditoria (
        id INTEGER PRIMARY KEY, operacion TEXT NOT NULL, producto_id INTEGER NOT NULL,
        antes_json TEXT, despues_json TEXT, fecha_utc TEXT NOT NULL, actor TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS supermercado_auditoria_producto_id ON supermercado_auditoria(producto_id,id DESC);
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(supermercado_productos)")}
    if "version" not in columns:
        conn.execute("ALTER TABLE supermercado_productos ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    conn.commit()


def name(value, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError("texto inválido")
    result = value.strip()
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in result):
        raise ValueError("texto inválido")
    return result


def quantity(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cantidad inválida")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("cantidad inválida")
    number = Decimal(str(value))
    if number < 0 or number > MAX_QUANTITY or number.as_tuple().exponent < -6:
        raise ValueError("cantidad inválida")
    return str(number)


@contextmanager
def transaction(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch(conn, table, row_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id=? AND deleted_at IS NULL", (row_id,)).fetchone()
    if row is None:
        raise LookupError("registro inexistente")
    return dict(row)


def _fetch_product_for_write(conn, row_id):
    row = conn.execute("SELECT * FROM supermercado_productos WHERE id=?", (row_id,)).fetchone()
    if row is None:
        raise LookupError("registro inexistente")
    result = dict(row)
    if result["deleted_at"] is not None:
        raise VersionConflict("El producto cambió; recargá el stock antes de guardar.")
    return result


def categories(conn):
    return [dict(row) for row in conn.execute("SELECT id,nombre,orden FROM supermercado_categorias WHERE deleted_at IS NULL ORDER BY orden,id")]


def category_create(conn, data):
    label = name(data["nombre"])
    order = data["orden"]
    if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order <= 1000000:
        raise ValueError("orden inválido")
    with transaction(conn):
        if conn.execute("SELECT COUNT(*) FROM supermercado_categorias WHERE deleted_at IS NULL").fetchone()[0] >= MAX_CATEGORIES:
            raise CapacityExceeded("límite técnico de 100 categorías activas")
        cursor = conn.execute("INSERT INTO supermercado_categorias(nombre,orden) VALUES (?,?)", (label, order))
    return _fetch(conn, "supermercado_categorias", cursor.lastrowid)


def category_update(conn, row_id, data):
    with transaction(conn):
        before = _fetch(conn, "supermercado_categorias", row_id)
        label = name(data.get("nombre", before["nombre"]))
        order = data.get("orden", before["orden"])
        if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order <= 1000000:
            raise ValueError("orden inválido")
        conn.execute("UPDATE supermercado_categorias SET nombre=?,orden=? WHERE id=?", (label, order, row_id))
        after = _fetch(conn, "supermercado_categorias", row_id)
    return after


def category_delete(conn, row_id):
    with transaction(conn):
        _fetch(conn, "supermercado_categorias", row_id)
        affected = [dict(row) for row in conn.execute("SELECT * FROM supermercado_productos WHERE categoria_id=? AND deleted_at IS NULL", (row_id,))]
        conn.execute("UPDATE supermercado_productos SET categoria_id=NULL,version=version+1 WHERE categoria_id=? AND deleted_at IS NULL", (row_id,))
        for before in affected:
            after = _fetch(conn, "supermercado_productos", before["id"])
            _audit(conn, "categoria_baja", before["id"], before, after)
        conn.execute("UPDATE supermercado_categorias SET deleted_at=? WHERE id=?", (_utc(), row_id))


def _validate_product(conn, data):
    result = {"producto": name(data["producto"]), "unidad": name(data["unidad"], 24),
              "stock_deseado": quantity(data["stock_deseado"]), "stock_actual": quantity(data["stock_actual"])}
    cat = data.get("categoria_id")
    if cat is not None:
        if isinstance(cat, bool) or not isinstance(cat, int) or cat < 1:
            raise ValueError("categoría inválida")
        _fetch(conn, "supermercado_categorias", cat)
    result["categoria_id"] = cat
    return result


def _audit(conn, operation, row_id, before, after):
    conn.execute("INSERT INTO supermercado_auditoria(operacion,producto_id,antes_json,despues_json,fecha_utc,actor) VALUES (?,?,?,?,?,?)",
                 (operation, row_id, json.dumps(before, ensure_ascii=False) if before else None,
                  json.dumps(after, ensure_ascii=False) if after else None, _utc(), ACTOR))


def product_create(conn, data):
    with transaction(conn):
        if conn.execute("SELECT COUNT(*) FROM supermercado_productos WHERE deleted_at IS NULL").fetchone()[0] >= MAX_PRODUCTS:
            raise CapacityExceeded("límite técnico de 1000 productos activos")
        value = _validate_product(conn, data)
        cursor = conn.execute("INSERT INTO supermercado_productos(categoria_id,producto,unidad,stock_deseado,stock_actual) VALUES (:categoria_id,:producto,:unidad,:stock_deseado,:stock_actual)", value)
        row = _fetch(conn, "supermercado_productos", cursor.lastrowid)
        _audit(conn, "alta", row["id"], None, row)
    return row


def product_update(conn, row_id, data, stock_only=False):
    if stock_only and set(data) != {"stock_actual", "expected_version"}:
        raise ValueError("solo stock_actual permitido")
    with transaction(conn):
        before = _fetch_product_for_write(conn, row_id)
        if before["version"] != data["expected_version"]:
            raise VersionConflict("El producto cambió; recargá el stock antes de guardar.")
        base = {**before, "stock_deseado": float(Decimal(before["stock_deseado"])),
                "stock_actual": float(Decimal(before["stock_actual"]))}
        value = _validate_product(conn, {**base, **data})
        conn.execute("UPDATE supermercado_productos SET categoria_id=:categoria_id,producto=:producto,unidad=:unidad,stock_deseado=:stock_deseado,stock_actual=:stock_actual,version=version+1 WHERE id=:id", {**value, "id": row_id})
        after = _fetch(conn, "supermercado_productos", row_id)
        _audit(conn, "stock" if stock_only else "edicion", row_id, before, after)
    return after


def product_delete(conn, row_id, expected_version):
    with transaction(conn):
        before = _fetch_product_for_write(conn, row_id)
        if before["version"] != expected_version:
            raise VersionConflict("El producto cambió; recargá el stock antes de guardar.")
        conn.execute("UPDATE supermercado_productos SET deleted_at=?,version=version+1 WHERE id=?", (_utc(), row_id))
        after = dict(conn.execute("SELECT * FROM supermercado_productos WHERE id=?", (row_id,)).fetchone())
        _audit(conn, "baja", row_id, before, after)
    return after


def _sort_key(value):
    normalized = unicodedata.normalize("NFD", value.casefold())
    return ("".join(char for char in normalized if not unicodedata.combining(char)), value.casefold())


def products(conn, cat_rows=None):
    if cat_rows is None:
        cat_rows = categories(conn)
    cat_order = {row["id"]: (row["orden"], row["id"]) for row in cat_rows}
    cat_name = {row["id"]: row["nombre"] for row in cat_rows}
    result = []
    for raw in conn.execute("SELECT id,categoria_id,producto,unidad,stock_deseado,stock_actual,version FROM supermercado_productos WHERE deleted_at IS NULL"):
        row = dict(raw)
        desired, current = Decimal(row["stock_deseado"]), Decimal(row["stock_actual"])
        missing = max(Decimal(0), desired - current)
        row.update(stock_deseado=float(desired), stock_actual=float(current), a_comprar=float(missing),
                   porcentaje_faltante=float(missing / desired * 100) if desired else 0.0,
                   estado="Vacío" if current <= 0 else "Reponer" if current < desired else "OK",
                   categoria=cat_name.get(row["categoria_id"]))
        result.append(row)
    result.sort(key=lambda row: ((0, *cat_order[row["categoria_id"]]) if row["categoria_id"] in cat_order else (1, 0, 0),
                                 _sort_key(row["producto"]), row["id"]))
    return result


def summary(rows, cat_rows):
    def counts(group):
        total = len(group)
        empty = sum(row["estado"] == "Vacío" for row in group)
        return {"productos": total, "a_reponer": sum(row["a_comprar"] > 0 for row in group), "vacios": empty,
                "reponer": sum(row["estado"] == "Reponer" for row in group),
                "ok": sum(row["estado"] == "OK" for row in group),
                "porcentaje_vacio": 100 * empty / total if total else 0,
                "porcentaje_lleno": 100 * (total - empty) / total if total else 0}
    return {"global": counts(rows), "categorias": [{**cat, **counts([row for row in rows if row["categoria_id"] == cat["id"]])} for cat in cat_rows] +
            [{"id": None, "nombre": "Sin categoría", "orden": None, **counts([row for row in rows if row["categoria_id"] is None])}]}


def history(conn, product_id, cursor=None):
    if conn.execute("SELECT 1 FROM supermercado_productos WHERE id=?", (product_id,)).fetchone() is None:
        raise LookupError("registro inexistente")
    if cursor is not None and conn.execute("SELECT 1 FROM supermercado_auditoria WHERE id=? AND producto_id=?", (cursor, product_id)).fetchone() is None:
        raise ValueError("cursor inválido")
    if cursor is None:
        raw = conn.execute("SELECT * FROM supermercado_auditoria WHERE producto_id=? ORDER BY id DESC LIMIT ?",
                           (product_id, HISTORY_PAGE_SIZE + 1)).fetchall()
    else:
        raw = conn.execute("SELECT * FROM supermercado_auditoria WHERE producto_id=? AND id<? ORDER BY id DESC LIMIT ?",
                           (product_id, cursor, HISTORY_PAGE_SIZE + 1)).fetchall()
    has_more = len(raw) > HISTORY_PAGE_SIZE
    page = raw[:HISTORY_PAGE_SIZE]
    rows = [{**dict(row), "antes": json.loads(row["antes_json"]) if row["antes_json"] else None,
             "despues": json.loads(row["despues_json"]) if row["despues_json"] else None}
            for row in page]
    return {"historial": rows, "next_cursor": page[-1]["id"] if has_more else None, "has_more": has_more}
