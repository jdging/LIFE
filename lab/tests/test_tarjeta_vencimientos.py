"""Vencimientos de la única tarjeta de crédito en uso (mejora Juan
2026-11-05, #6 lista de mejoras): agenda mínima que usa el dashboard para
agrupar la carga de crédito por ciclo (entre vencimientos) en vez de por
mes calendario. Contra SQLite efímera (`:memory:`), nunca contra la base
real.
"""

import pytest

import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def test_get_tarjeta_vencimientos_vacio_al_inicio(conn):
    assert db.get_tarjeta_vencimientos(conn) == []


def test_set_tarjeta_vencimiento_crea_fila_nueva(conn):
    fila = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    assert fila["mes"] == "2026-11"
    assert fila["vencimiento"] == "2026-11-10"
    assert fila["id"] is not None
    assert [f["mes"] for f in db.get_tarjeta_vencimientos(conn)] == ["2026-11"]


def test_set_tarjeta_vencimiento_upsert_reemplaza_sin_duplicar(conn):
    primera = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    segunda = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-12")
    assert segunda["id"] == primera["id"]
    assert segunda["vencimiento"] == "2026-11-12"
    assert len(db.get_tarjeta_vencimientos(conn)) == 1


def test_get_tarjeta_vencimientos_ordenado_por_mes(conn):
    db.set_tarjeta_vencimiento(conn, "2026-12", "2026-12-10")
    db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    meses = [f["mes"] for f in db.get_tarjeta_vencimientos(conn)]
    assert meses == ["2026-11", "2026-12"]


@pytest.mark.parametrize("mes", ["2026-13", "2026-00", "26-11", "noviembre", "", None, 202611])
def test_set_tarjeta_vencimiento_rechaza_mes_invalido(conn, mes):
    with pytest.raises(ValueError):
        db.set_tarjeta_vencimiento(conn, mes, "2026-11-10")


@pytest.mark.parametrize("vencimiento", ["2026-11-31", "11/10/2026", "", None, "2026-11-10T00:00:00"])
def test_set_tarjeta_vencimiento_rechaza_fecha_invalida(conn, vencimiento):
    with pytest.raises(ValueError):
        db.set_tarjeta_vencimiento(conn, "2026-11", vencimiento)


def test_eliminar_tarjeta_vencimiento_existente_e_inexistente(conn):
    fila = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    assert db.eliminar_tarjeta_vencimiento(conn, fila["id"]) is True
    assert db.get_tarjeta_vencimientos(conn) == []
    # Idempotente: borrar de nuevo (o un id que nunca existió) no explota.
    assert db.eliminar_tarjeta_vencimiento(conn, fila["id"]) is False
    assert db.eliminar_tarjeta_vencimiento(conn, 999999) is False
