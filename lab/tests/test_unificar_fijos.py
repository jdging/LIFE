"""Unificación sobre ids sintéticos que imitan el mapping del lab."""

import sqlite3

import pytest

import db
import unificar_fijos


@pytest.fixture
def archivo_db(tmp_path):
    ruta = tmp_path / "fijos_sinteticos.sqlite"
    conn = db.get_connection(str(ruta))
    db.init_db(conn)
    mapping = unificar_fijos.cargar_mapping()
    for grupo in mapping["grupos"]:
        for indice, fijo_id in enumerate(grupo["ids"]):
            conn.execute(
                """INSERT INTO gastos_fijos
                (id, nombre, monto_estimado, periodicidad, activo, ultima_actualizacion,
                 vigente_desde, fijo_grupo_id)
                VALUES (?, ?, ?, 'mensual', 1, ?, ?, ?)""",
                (fijo_id, grupo["nombre"], 100 + indice,
                 f"2025-{indice + 1:02d}-01", f"2025-{indice + 1:02d}-01", fijo_id),
            )
    for item in mapping["a_confirmar"]:
        conn.execute(
            """INSERT INTO gastos_fijos
            (id, nombre, monto_estimado, periodicidad, activo, ultima_actualizacion,
             vigente_desde, fijo_grupo_id)
            VALUES (?, ?, 100, 'mensual', 1, '2025-01-01', '2025-01-01', ?)""",
            (item["id"], item["nombre"], item["id"]),
        )
    conn.commit()
    conn.close()
    return ruta


def test_dry_run_no_escribe_y_enumera_a_confirmar(archivo_db, capsys):
    conn = db.get_connection(str(archivo_db))
    antes = [tuple(fila) for fila in conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos ORDER BY id")]
    conn.close()
    assert unificar_fijos.main(["--db", str(archivo_db)]) == 0
    salida = capsys.readouterr().out
    assert "DRY-RUN" in salida
    assert "124 Agosto" in salida
    assert "antes:" in salida and "después:" in salida
    conn = db.get_connection(str(archivo_db))
    despues = [tuple(fila) for fila in conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos ORDER BY id")]
    assert despues == antes
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0
    conn.close()


def test_sin_db_no_abre_archivo(archivo_db, capsys):
    assert unificar_fijos.main([]) == 0
    assert "no se abrió ninguna base" in capsys.readouterr().out
    conn = db.get_connection(str(archivo_db))
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0
    conn.close()


def test_apply_idempotente_y_deja_pendientes_sin_unificar(archivo_db):
    assert unificar_fijos.main(["--apply", "--db", str(archivo_db), "--actor", "JD"]) == 0
    conn = db.get_connection(str(archivo_db))
    mapping = unificar_fijos.cargar_mapping()
    for grupo in mapping["grupos"]:
        destino = min(grupo["ids"])
        filas = conn.execute(
            f"SELECT fijo_grupo_id FROM gastos_fijos WHERE id IN ({','.join('?' for _ in grupo['ids'])})",
            grupo["ids"],
        ).fetchall()
        assert {fila["fijo_grupo_id"] for fila in filas} == {destino}
        assert len(db.historial_fijo(conn, destino)) == len(grupo["ids"])
    for item in mapping["a_confirmar"]:
        fila = conn.execute("SELECT fijo_grupo_id FROM gastos_fijos WHERE id = ?", (item["id"],)).fetchone()
        assert fila["fijo_grupo_id"] == item["id"]
    cantidad = conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]
    assert cantidad > 0
    assert {fila[0] for fila in conn.execute("SELECT DISTINCT accion FROM auditoria")} == {"unificar"}
    conn.close()
    assert unificar_fijos.main(["--apply", "--db", str(archivo_db)]) == 0
    conn = db.get_connection(str(archivo_db))
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == cantidad
    conn.close()


def test_unificacion_rechaza_id_faltante_sin_cambios(archivo_db):
    conn = db.get_connection(str(archivo_db))
    with pytest.raises(ValueError):
        db.unificar_series_fijos(conn, [94, 999], "JD")
    assert conn.execute("SELECT fijo_grupo_id FROM gastos_fijos WHERE id = 94").fetchone()[0] == 94
    conn.close()


def test_unificacion_revierte_todo_si_falla_auditoria(archivo_db):
    conn = db.get_connection(str(archivo_db))
    conn.execute("""CREATE TRIGGER falla_unificar BEFORE INSERT ON auditoria
                    WHEN NEW.accion = 'unificar' BEGIN SELECT RAISE(ABORT, 'fallo'); END""")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.unificar_series_fijos(conn, [94, 103], "JD")
    assert conn.execute("SELECT fijo_grupo_id FROM gastos_fijos WHERE id = 103").fetchone()[0] == 103
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0
    conn.close()


def test_apply_revierte_mapping_completo_si_falla_segundo_grupo(archivo_db):
    mapping = unificar_fijos.cargar_mapping()
    segundo = [grupo for grupo in mapping["grupos"]
               if grupo["confianza"] in ("alta", "media")][1]
    falla_id = max(segundo["ids"])
    conn = db.get_connection(str(archivo_db))
    antes = [tuple(fila) for fila in conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos ORDER BY id")]
    conn.execute(f"""CREATE TRIGGER falla_segundo_grupo BEFORE INSERT ON auditoria
                    WHEN NEW.accion = 'unificar' AND NEW.fila_id = {falla_id}
                    BEGIN SELECT RAISE(ABORT, 'fallo segundo grupo'); END""")
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="fallo segundo grupo"):
        unificar_fijos.main(["--apply", "--db", str(archivo_db), "--actor", "JD"])

    conn = db.get_connection(str(archivo_db))
    assert [tuple(fila) for fila in conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos ORDER BY id")] == antes
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0
    conn.close()
