"""Tests de soft delete de `gastos` (t_65096083, punto 2 del brief).

Contra SQLite efímera (`:memory:`), nunca contra la base real.
"""

import pytest

import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def _gasto_valido(**overrides):
    gasto = {
        "fecha": "2026-09-25",
        "monto": 1000.0,
        "categoria": "Comida",
        "pagado_por": "Común",
        "descripcion_original": "Supermercado",
        "confirmado": True,
    }
    gasto.update(overrides)
    return gasto


def test_migracion_agrega_columnas_soft_delete_y_tabla_auditoria(conn):
    columnas = db._column_names(conn, "gastos")
    assert "deleted_at" in columnas
    assert "deleted_by" in columnas

    tablas = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "auditoria" in tablas


def test_eliminar_gasto_logico_no_borra_fila_fisicamente(conn):
    gasto_id = db.insert_gasto(conn, _gasto_valido())

    db.eliminar_gasto_logico(conn, gasto_id, actor="JD")

    fila = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila is not None  # sigue existiendo físicamente
    assert fila["deleted_at"] is not None
    assert fila["deleted_by"] == "JD"


def test_eliminar_gasto_logico_inserta_auditoria(conn):
    gasto_id = db.insert_gasto(conn, _gasto_valido(descripcion_original="Cine"))

    db.eliminar_gasto_logico(conn, gasto_id, actor="Pinki")

    filas_auditoria = conn.execute(
        "SELECT * FROM auditoria WHERE tabla = 'gastos' AND fila_id = ?", (gasto_id,)
    ).fetchall()
    assert len(filas_auditoria) == 1
    auditoria = dict(filas_auditoria[0])
    assert auditoria["accion"] == "baja"
    assert auditoria["actor"] == "Pinki"
    assert auditoria["despues_json"] is None
    assert "Cine" in auditoria["antes_json"]


def test_get_gastos_excluye_borrados_por_default(conn):
    activo_id = db.insert_gasto(conn, _gasto_valido(descripcion_original="Activo"))
    borrado_id = db.insert_gasto(conn, _gasto_valido(descripcion_original="Borrado"))
    db.eliminar_gasto_logico(conn, borrado_id, actor="JD")

    gastos = db.get_gastos(conn)
    ids = [g["id"] for g in gastos]

    assert activo_id in ids
    assert borrado_id not in ids


def test_get_gastos_incluye_borrados_si_se_pide_explicitamente(conn):
    activo_id = db.insert_gasto(conn, _gasto_valido(descripcion_original="Activo"))
    borrado_id = db.insert_gasto(conn, _gasto_valido(descripcion_original="Borrado"))
    db.eliminar_gasto_logico(conn, borrado_id, actor="JD")

    gastos = db.get_gastos(conn, incluir_borrados=True)
    ids = [g["id"] for g in gastos]

    assert activo_id in ids
    assert borrado_id in ids
    assert len(gastos) == 2


def test_eliminar_gasto_logico_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.eliminar_gasto_logico(conn, 9999, actor="JD")


def test_eliminar_gasto_logico_ya_borrado_lanza_valueerror(conn):
    gasto_id = db.insert_gasto(conn, _gasto_valido())
    db.eliminar_gasto_logico(conn, gasto_id, actor="JD")

    with pytest.raises(ValueError):
        db.eliminar_gasto_logico(conn, gasto_id, actor="Pinki")
