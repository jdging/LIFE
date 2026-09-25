"""Script aislado y de un solo propósito: retirar el gasto demo 'Cine con
Pinki' (id 21) sembrado por error en la base real.

USO EXCLUSIVO DEL COORDINADOR, sobre la base de datos real, ANTES de correr
`export_dashboard_real.py` en producción. No se ejecuta desde el candidato ni
sobre ningún dato real como parte de esta tarea — ver README.md.

Salvaguardas:
- Requiere `--db-path` explícito (no hay default: nunca corre "por accidente"
  contra la base equivocada).
- Requiere `--confirmar "SI, BORRAR CINE DEMO"` (la frase literal) para
  proceder; cualquier otro valor aborta sin tocar la base.
- Antes de borrar, verifica id, fecha, monto, moneda y descripción EXACTOS
  contra los valores confirmados por Juan. Si algo no coincide, aborta sin
  borrar nada (fail-closed: nunca borra "el gasto que más se parece").
- Crea SIEMPRE un backup consistente antes de borrar, usando
  `sqlite3.Connection.backup()` (no `shutil.copy2`): copia a través del
  pager de SQLite, así que incluye el contenido de un WAL activo (`-wal`)
  sin necesitar checkpoint previo. La conexión al origen es de solo lectura
  (`mode=ro`): el backup nunca escribe en la base real. No existe forma de
  saltear este paso (no hay flag `--sin-backup-automatico`: si el backup
  falla, el script aborta sin borrar nada y con exit code distinto de 0).
  El backup se guarda en `<carpeta de db_path>/lab/data/`.
- No imprime montos ni descripciones en los logs: solo confirma que la
  verificación pasó o falló, para no dejar datos financieros en la salida.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import db

GASTO_DEMO_ID = 21
GASTO_DEMO_FECHA = "2026-09-24"
GASTO_DEMO_MONTO = 17000
GASTO_DEMO_MONEDA = "ARS"
GASTO_DEMO_DESCRIPCION = "Cine con Pinki"

FRASE_CONFIRMACION = "SI, BORRAR CINE DEMO"


class VerificacionFallida(Exception):
    """El gasto en `gasto_id` no coincide exactamente con el ejemplo demo esperado."""


def _verificar_gasto(conn: sqlite3.Connection, gasto_id: int) -> None:
    row = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    if row is None:
        raise VerificacionFallida(f"No existe ningún gasto con id={gasto_id}.")

    gasto = dict(row)
    campos_esperados = {
        "monto": GASTO_DEMO_MONTO,
        "moneda": GASTO_DEMO_MONEDA,
        "descripcion_original": GASTO_DEMO_DESCRIPCION,
    }
    if (gasto.get("fecha") or "")[:10] != GASTO_DEMO_FECHA:
        raise VerificacionFallida(
            f"El campo 'fecha' del gasto id={gasto_id} no coincide con el "
            "ejemplo demo esperado. Abortando sin borrar nada."
        )
    for campo, esperado in campos_esperados.items():
        if gasto.get(campo) != esperado:
            raise VerificacionFallida(
                f"El campo '{campo}' del gasto id={gasto_id} no coincide con el "
                "ejemplo demo esperado. Abortando sin borrar nada."
            )


def retirar_gasto_demo(conn: sqlite3.Connection, gasto_id: int = GASTO_DEMO_ID) -> int:
    """Verifica y borra el gasto demo. Devuelve el id borrado.

    Lanza `VerificacionFallida` (sin borrar nada) si `gasto_id` no coincide
    exactamente con fecha/monto/moneda/descripción del ejemplo confirmado por
    Juan. No filtra por monto solo — dos gastos distintos pueden compartir
    importe, y eso NO alcanza para considerarlos el mismo ejemplo.
    """
    _verificar_gasto(conn, gasto_id)
    conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
    conn.commit()
    return gasto_id


def _crear_backup(db_path: str) -> str:
    """Crea un backup consistente de `db_path` con la API de backup de SQLite.

    A diferencia de copiar el archivo con `shutil.copy2`, `Connection.backup()`
    opera a través del pager de SQLite: incluye el contenido de un WAL activo
    (`-wal`) sin necesitar checkpoint previo y sin dejar el archivo a medio
    copiar si hay escrituras concurrentes. La conexión al origen es de solo
    lectura (`mode=ro`), así que esta función nunca modifica `db_path`.
    """
    origen = Path(db_path)
    if not origen.exists():
        raise FileNotFoundError(f"No existe el archivo de base de datos en {db_path}.")

    backup_dir = origen.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = backup_dir / f"{origen.name}.backup-{timestamp}.sqlite"

    origen_conn = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    try:
        destino_conn = sqlite3.connect(str(destino))
        try:
            origen_conn.backup(destino_conn)
        finally:
            destino_conn.close()
    finally:
        origen_conn.close()

    return str(destino)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retira el gasto demo 'Cine con Pinki' (id 21) de la base de "
            "datos real. Uso exclusivo del coordinador."
        )
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help="Ruta explícita a la base sqlite real (sin default deliberadamente).",
    )
    parser.add_argument(
        "--confirmar",
        metavar="FRASE",
        default="",
        help=f'Debe ser exactamente "{FRASE_CONFIRMACION}" para proceder.',
    )
    args = parser.parse_args()

    if args.confirmar != FRASE_CONFIRMACION:
        print(
            f'Abortado: falta la confirmación exacta (--confirmar "{FRASE_CONFIRMACION}"). '
            "No se modificó nada.",
            file=sys.stderr,
        )
        return 1

    if args.db_path != ":memory:":
        try:
            backup_path = _crear_backup(args.db_path)
        except Exception as exc:
            print(
                f"Abortado: no se pudo crear el backup ({exc.__class__.__name__}: {exc}). "
                "No se borró nada.",
                file=sys.stderr,
            )
            return 1
        print(f"Backup creado en: {backup_path}")

    conn = db.get_connection(args.db_path)
    try:
        gasto_id = retirar_gasto_demo(conn)
    except VerificacionFallida as exc:
        print(f"Abortado: {exc}", file=sys.stderr)
        conn.close()
        return 1

    print(f"Gasto demo id={gasto_id} verificado y eliminado correctamente.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
