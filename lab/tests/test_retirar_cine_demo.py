"""Tests de retirar_cine_demo.py contra una DB :memory: sintética.

No usan ningún dataset real. No se ejecutaron en este entorno (rol sin
shell) — ver README.md.
"""

import sqlite3

import pytest

import db
import retirar_cine_demo as rcd


def _conn_con_gastos() -> sqlite3.Connection:
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _insertar_gasto_demo(conn: sqlite3.Connection) -> int:
    return db.insert_gasto(
        conn,
        {
            "fecha": rcd.GASTO_DEMO_FECHA,
            "monto": rcd.GASTO_DEMO_MONTO,
            "moneda": rcd.GASTO_DEMO_MONEDA,
            "categoria": "Entretenimiento",
            "subcategoria": "Cine/Teatro",
            "pagado_por": "Común",
            "descripcion_original": rcd.GASTO_DEMO_DESCRIPCION,
            "origen": "texto",
            "confirmado": True,
        },
    )


def _insertar_gasto_demo_en_id_21(conn: sqlite3.Connection) -> int:
    """Inserta el gasto demo con id=21 EXACTO, como está en la base real.

    `id` es INTEGER PRIMARY KEY AUTOINCREMENT: nunca se reutiliza un id ya
    usado, así que en vez de sembrar 20 filas de relleno para "llegar" al id
    21 (lo que además contaminaría el test con datos que no vienen al caso),
    lo insertamos con ese id explícito. Es fiel al estado real que
    `retirar_cine_demo.main()` espera encontrar (usa `GASTO_DEMO_ID=21` por
    default) sin tocar ninguna validación de producción del script.
    """
    conn.execute(
        """
        INSERT INTO gastos
            (id, fecha, monto, moneda, categoria, subcategoria, pagado_por,
             descripcion_original, origen, confirmado, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            rcd.GASTO_DEMO_ID,
            rcd.GASTO_DEMO_FECHA,
            rcd.GASTO_DEMO_MONTO,
            rcd.GASTO_DEMO_MONEDA,
            "Entretenimiento",
            "Cine/Teatro",
            "Común",
            rcd.GASTO_DEMO_DESCRIPCION,
            "texto",
            db._now(),
        ),
    )
    conn.commit()
    return rcd.GASTO_DEMO_ID


def test_borra_solo_el_gasto_demo_exacto():
    conn = _conn_con_gastos()
    id_demo = _insertar_gasto_demo(conn)
    id_otro = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-24",
            "monto": 17000,  # mismo importe, gasto distinto real
            "categoria": "Hogar",
            "pagado_por": "Común",
            "descripcion_original": "Expensas septiembre",
            "origen": "migracion",
            "confirmado": True,
        },
    )

    borrado_id = rcd.retirar_gasto_demo(conn, gasto_id=id_demo)

    assert borrado_id == id_demo
    assert conn.execute("SELECT id FROM gastos WHERE id = ?", (id_demo,)).fetchone() is None
    restante = conn.execute("SELECT id FROM gastos WHERE id = ?", (id_otro,)).fetchone()
    assert restante is not None


def test_aborta_si_monto_no_coincide():
    conn = _conn_con_gastos()
    id_gasto = db.insert_gasto(
        conn,
        {
            "fecha": rcd.GASTO_DEMO_FECHA,
            "monto": 5000,  # no coincide con el ejemplo
            "categoria": "Entretenimiento",
            "pagado_por": "Común",
            "descripcion_original": rcd.GASTO_DEMO_DESCRIPCION,
            "origen": "texto",
            "confirmado": True,
        },
    )

    with pytest.raises(rcd.VerificacionFallida):
        rcd.retirar_gasto_demo(conn, gasto_id=id_gasto)

    assert conn.execute("SELECT id FROM gastos WHERE id = ?", (id_gasto,)).fetchone() is not None


def test_aborta_si_descripcion_no_coincide():
    conn = _conn_con_gastos()
    id_gasto = db.insert_gasto(
        conn,
        {
            "fecha": rcd.GASTO_DEMO_FECHA,
            "monto": rcd.GASTO_DEMO_MONTO,
            "categoria": "Entretenimiento",
            "pagado_por": "Común",
            "descripcion_original": "Cine solo",
            "origen": "texto",
            "confirmado": True,
        },
    )

    with pytest.raises(rcd.VerificacionFallida):
        rcd.retirar_gasto_demo(conn, gasto_id=id_gasto)

    assert conn.execute("SELECT id FROM gastos WHERE id = ?", (id_gasto,)).fetchone() is not None


def test_aborta_si_fecha_no_coincide():
    conn = _conn_con_gastos()
    id_gasto = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-25",
            "monto": rcd.GASTO_DEMO_MONTO,
            "categoria": "Entretenimiento",
            "pagado_por": "Común",
            "descripcion_original": rcd.GASTO_DEMO_DESCRIPCION,
            "origen": "texto",
            "confirmado": True,
        },
    )

    with pytest.raises(rcd.VerificacionFallida):
        rcd.retirar_gasto_demo(conn, gasto_id=id_gasto)

    assert conn.execute("SELECT id FROM gastos WHERE id = ?", (id_gasto,)).fetchone() is not None


def test_aborta_si_id_no_existe():
    conn = _conn_con_gastos()
    with pytest.raises(rcd.VerificacionFallida):
        rcd.retirar_gasto_demo(conn, gasto_id=999)


def test_cli_aborta_sin_frase_de_confirmacion_exacta(tmp_path, capsys):
    db_path = tmp_path / "lasso_test.sqlite"
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    _insertar_gasto_demo(conn)
    conn.close()

    # main() usa argparse sobre sys.argv; lo probamos invocándolo con argv controlado.
    import sys

    argv_original = sys.argv
    try:
        sys.argv = ["retirar_cine_demo.py", "--db-path", str(db_path), "--confirmar", "no"]
        codigo = rcd.main()
    finally:
        sys.argv = argv_original

    assert codigo == 1
    salida = capsys.readouterr()
    assert "Abortado" in salida.err

    conn = db.get_connection(str(db_path))
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 1
    conn.close()


def test_cli_borra_y_crea_backup_con_confirmacion_exacta(tmp_path):
    db_path = tmp_path / "lasso_test.sqlite"
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    # Un gasto real, ajeno al demo, para comprobar que el script no lo toca.
    id_otro = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-10",
            "monto": 55000,
            "categoria": "Hogar",
            "subcategoria": "Expensas",
            "pagado_por": "Común",
            "descripcion_original": "Expensas septiembre",
            "origen": "migracion",
            "confirmado": True,
        },
    )
    _insertar_gasto_demo_en_id_21(conn)
    total_antes = conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"]
    assert total_antes == 2
    conn.close()

    import sys

    argv_original = sys.argv
    try:
        sys.argv = [
            "retirar_cine_demo.py",
            "--db-path",
            str(db_path),
            "--confirmar",
            rcd.FRASE_CONFIRMACION,
        ]
        codigo = rcd.main()
    finally:
        sys.argv = argv_original

    assert codigo == 0

    backups = list(tmp_path.glob("lasso_test.sqlite.backup-*.sqlite"))
    assert len(backups) == 1

    # El backup se toma ANTES de borrar: debe incluir todavía la fila 21.
    backup_conn = sqlite3.connect(str(backups[0]))
    backup_conn.row_factory = sqlite3.Row
    fila_backup = backup_conn.execute(
        "SELECT * FROM gastos WHERE id = ?", (rcd.GASTO_DEMO_ID,)
    ).fetchone()
    backup_conn.close()
    assert fila_backup is not None
    assert fila_backup["descripcion_original"] == rcd.GASTO_DEMO_DESCRIPCION

    conn = db.get_connection(str(db_path))
    assert (
        conn.execute(
            "SELECT id FROM gastos WHERE id = ?", (rcd.GASTO_DEMO_ID,)
        ).fetchone()
        is None
    )
    otro = conn.execute("SELECT * FROM gastos WHERE id = ?", (id_otro,)).fetchone()
    assert otro is not None
    assert otro["descripcion_original"] == "Expensas septiembre"
    assert otro["monto"] == 55000
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 1
    conn.close()


def test_crear_backup_incluye_fila_21_con_wal_activo(tmp_path):
    """El backup vía Connection.backup() incluye datos que siguen en el -wal.

    A diferencia de `shutil.copy2` (que solo copia el archivo principal y
    puede dejar afuera transacciones aún no checkpointeadas), la API de
    backup de SQLite lee a través del pager y por lo tanto ve el contenido
    combinado de `<db>` + `<db>-wal`.
    """
    db_path = tmp_path / "lasso_wal.sqlite"
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    _insertar_gasto_demo_en_id_21(conn)

    # Conexión adicional para que SQLite no haga un checkpoint automático al
    # cerrar `conn` (solo checkpointea al cerrar la ÚLTIMA conexión abierta).
    holder = sqlite3.connect(str(db_path))

    wal_path = db_path.with_name(db_path.name + "-wal")
    assert wal_path.exists()
    assert wal_path.stat().st_size > 0

    destino = rcd._crear_backup(str(db_path))

    conn.close()
    holder.close()

    backup_conn = sqlite3.connect(destino)
    backup_conn.row_factory = sqlite3.Row
    fila = backup_conn.execute(
        "SELECT * FROM gastos WHERE id = ?", (rcd.GASTO_DEMO_ID,)
    ).fetchone()
    backup_conn.close()

    assert fila is not None
    assert fila["descripcion_original"] == rcd.GASTO_DEMO_DESCRIPCION
    assert fila["monto"] == rcd.GASTO_DEMO_MONTO

    # El backup no debe haber modificado el origen.
    origen_conn = db.get_connection(str(db_path))
    fila_origen = origen_conn.execute(
        "SELECT id FROM gastos WHERE id = ?", (rcd.GASTO_DEMO_ID,)
    ).fetchone()
    origen_conn.close()
    assert fila_origen is not None


def test_cli_aborta_sin_borrar_si_falla_el_backup(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "lasso_test.sqlite"
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    _insertar_gasto_demo_en_id_21(conn)
    conn.close()

    def _backup_que_falla(_db_path):
        raise sqlite3.OperationalError("simulado: no se pudo abrir destino")

    monkeypatch.setattr(rcd, "_crear_backup", _backup_que_falla)

    import sys

    argv_original = sys.argv
    try:
        sys.argv = [
            "retirar_cine_demo.py",
            "--db-path",
            str(db_path),
            "--confirmar",
            rcd.FRASE_CONFIRMACION,
        ]
        codigo = rcd.main()
    finally:
        sys.argv = argv_original

    assert codigo != 0

    salida = capsys.readouterr()
    assert "Abortado" in salida.err
    assert str(rcd.GASTO_DEMO_MONTO) not in salida.err
    assert rcd.GASTO_DEMO_DESCRIPCION not in salida.err

    conn = db.get_connection(str(db_path))
    fila = conn.execute(
        "SELECT id FROM gastos WHERE id = ?", (rcd.GASTO_DEMO_ID,)
    ).fetchone()
    conn.close()
    assert fila is not None  # el backup falló: no se borró nada
