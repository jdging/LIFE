-- =============================================================================
-- DISEÑO de migración — soft delete de `gastos` + tabla `auditoria`
-- =============================================================================
--
-- ESTADO: NO EJECUTADA. Este archivo es un documento de diseño para cuando
-- Juan/Viktor aprueben la ventana de aplicación sobre datos reales. No se
-- corrió contra ninguna base (ni la real ni una copia). No está referenciada
-- desde `db.py` (ni `SCHEMA` ni ninguna función `_migrar_columnas_*`).
--
-- Objetivo: soportar `DELETE /api/expenses/:id` como baja lógica (ver
-- `api-contract.md`) sin perder el registro físico, y dejar rastro de quién
-- hizo qué cambio (alta/baja/edición) para poder auditar y revertir.
--
-- Patrón seguido: el mismo que ya usa `db.py` en
-- `_migrar_columnas_gastos` / `_migrar_columnas_tarjetas` /
-- `_migrar_columnas_gastos_fijos` — `ALTER TABLE ... ADD COLUMN` envuelto en
-- un chequeo de `PRAGMA table_info` para que sea idempotente y no falle en
-- bases que ya tienen las columnas.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Columnas nuevas en `gastos`
-- -----------------------------------------------------------------------------
-- `deleted_at`: fecha ISO 8601 (mismo formato que usa `_now()` en db.py) en
--   la que el gasto fue borrado lógicamente, o NULL si sigue activo.
-- `deleted_by`: quién ejecutó el borrado ('JD' / 'Pinki' / identificador de
--   actor), o NULL si sigue activo. Alimenta también `auditoria.actor`.
--
-- Equivalente Python (agregar a `_migrar_columnas_gastos` en `db.py`,
-- SOLO cuando esta migración esté aprobada para aplicarse — no antes):
--
--   columnas_nuevas = (
--       ...  # columnas existentes sin tocar
--       ("deleted_at", "TEXT"),
--       ("deleted_by", "TEXT"),
--   )

ALTER TABLE gastos ADD COLUMN deleted_at TEXT;
ALTER TABLE gastos ADD COLUMN deleted_by TEXT;

-- -----------------------------------------------------------------------------
-- 2. Tabla `auditoria`
-- -----------------------------------------------------------------------------
-- Genérica por diseño (no una tabla por entidad) para poder auditar
-- `gastos`, `gastos_fijos`, y cualquier tabla futura con el mismo esquema,
-- igual que `categorias`/`tarjetas` sirven a múltiples consumidores en
-- `db.py` hoy.
--
-- `antes_json` / `despues_json`: snapshot completo de la fila (serializado
--   con `json.dumps(dict(row), ensure_ascii=False)`, mismo patrón que ya usa
--   `db.py` para `payload_parcial` en `estado_conversacional`) antes/después
--   del cambio. NULL en `antes_json` para altas, NULL en `despues_json` para
--   bajas.
-- `accion`: 'alta' | 'baja' | 'edicion'.

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

-- -----------------------------------------------------------------------------
-- 3. Por qué es reversible
-- -----------------------------------------------------------------------------
-- - `ALTER TABLE ... ADD COLUMN` en SQLite es no destructivo: agrega la
--   columna con valor NULL para todas las filas existentes, sin reescribir
--   ni perder datos. Revertir = `ALTER TABLE gastos DROP COLUMN deleted_at`
--   (soportado desde SQLite 3.35, 2021) o, si el runtime es más viejo,
--   simplemente dejar la columna sin usar (no rompe ningún query existente
--   porque `SELECT *` vía `sqlite3.Row` solo agrega claves al dict, no
--   cambia el comportamiento de código que no las referencia).
-- - `CREATE TABLE IF NOT EXISTS auditoria` no toca ninguna tabla existente.
--   Revertir = `DROP TABLE auditoria` (borra solo el rastro de auditoría,
--   nunca datos de negocio).
-- - El soft delete en sí es reversible por construcción: un "undelete" es
--   `UPDATE gastos SET deleted_at = NULL, deleted_by = NULL WHERE id = ?`,
--   sin necesidad de restaurar desde backup.
-- - Ningún `DELETE` físico ni `DROP` de datos existentes en ningún paso de
--   esta migración.
--
-- -----------------------------------------------------------------------------
-- 4. Cómo se aplicaría (cuando esté aprobado)
-- -----------------------------------------------------------------------------
-- 1. Backup de `data/lasso.sqlite` (copia de archivo, SQLite es un solo
--    archivo — trivial).
-- 2. Agregar las dos funciones de migración a `db.py` siguiendo el patrón
--    de `_migrar_columnas_gastos`:
--      - `_migrar_columnas_gastos`: sumar `deleted_at`/`deleted_by` a la
--        tupla `columnas_nuevas` ya existente (no crear una función nueva,
--        reusar la que ya migra `gastos`).
--      - `_crear_tabla_auditoria(conn)`: agregar el `CREATE TABLE IF NOT
--        EXISTS auditoria (...)` a `SCHEMA` (igual que las demás tablas) o
--        a una función `_migrar_tabla_auditoria` llamada desde `init_db`.
-- 3. Correr `init_db(conn)` una vez contra la base real (mismo mecanismo
--    que ya dispara las migraciones de columnas existentes en cada arranque
--    — no hace falta un paso manual nuevo).
-- 4. Verificar con `PRAGMA table_info(gastos)` y
--    `SELECT name FROM sqlite_master WHERE type='table'` que las columnas y
--    la tabla existen.
-- 5. Recién ahí, implementar el handler de `DELETE /api/expenses/:id` para
--    que escriba `deleted_at`/`deleted_by` + una fila en `auditoria` (dentro
--    de la misma transacción) en vez de hacer `DELETE FROM gastos`.
--
-- Ninguno de estos pasos se ejecuta desde este workdir ni desde `db.py` real.
