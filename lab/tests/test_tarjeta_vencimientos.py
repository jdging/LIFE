"""Vencimientos de la única tarjeta de crédito en uso (mejora Juan
2026-11-05, #6 lista de mejoras; corrección de modelo el mismo día --
Juan: "la fecha que importa es el cierre... entre cierres es lo que entra
en la tarjeta del mes vigente"). `cierre` es la fecha real que agrupa los
gastos (agenda que usa el dashboard para armar ciclos); `vencimiento_pago`
es solo informativo/recordatorio de cuándo pagar, nunca agrupa. Contra
SQLite efímera (`:memory:`), nunca contra la base real.
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


def test_set_tarjeta_vencimiento_crea_fila_nueva_sin_vencimiento_pago(conn):
    fila = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    assert fila["mes"] == "2026-11"
    assert fila["cierre"] == "2026-11-10"
    assert fila["vencimiento_pago"] is None
    assert fila["id"] is not None
    assert [f["mes"] for f in db.get_tarjeta_vencimientos(conn)] == ["2026-11"]


def test_set_tarjeta_vencimiento_acepta_vencimiento_pago_opcional(conn):
    fila = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10", "2026-11-20")
    assert fila["cierre"] == "2026-11-10"
    assert fila["vencimiento_pago"] == "2026-11-20"


def test_set_tarjeta_vencimiento_upsert_reemplaza_sin_duplicar(conn):
    primera = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    segunda = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-12", "2026-11-22")
    assert segunda["id"] == primera["id"]
    assert segunda["cierre"] == "2026-11-12"
    assert segunda["vencimiento_pago"] == "2026-11-22"
    assert len(db.get_tarjeta_vencimientos(conn)) == 1


def test_upsert_puede_borrar_vencimiento_pago_pasando_none_de_nuevo(conn):
    db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10", "2026-11-20")
    actualizada = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    assert actualizada["vencimiento_pago"] is None


def test_get_tarjeta_vencimientos_ordenado_por_mes(conn):
    db.set_tarjeta_vencimiento(conn, "2026-12", "2026-12-10")
    db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    meses = [f["mes"] for f in db.get_tarjeta_vencimientos(conn)]
    assert meses == ["2026-11", "2026-12"]


def test_cargar_un_mes_atrasado_despues_de_uno_posterior_es_valido(conn):
    """Juan: '¿qué pasa si un mes me olvido de poner la fecha y vuelvo al
    próximo mes?' -- cargar 2026-10 DESPUÉS de ya haber cargado 2026-11
    tiene que funcionar sin restricción de orden; los ciclos se recalculan
    siempre ordenando por `cierre`, no por orden de inserción."""
    db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-24")
    db.set_tarjeta_vencimiento(conn, "2026-10", "2026-10-24")  # backfill atrasado
    meses = [f["mes"] for f in db.get_tarjeta_vencimientos(conn)]
    assert meses == ["2026-10", "2026-11"]


@pytest.mark.parametrize("mes", ["2026-13", "2026-00", "26-11", "noviembre", "", None, 202611])
def test_set_tarjeta_vencimiento_rechaza_mes_invalido(conn, mes):
    with pytest.raises(ValueError):
        db.set_tarjeta_vencimiento(conn, mes, "2026-11-10")


@pytest.mark.parametrize("cierre", ["2026-11-31", "11/10/2026", "", None, "2026-11-10T00:00:00"])
def test_set_tarjeta_vencimiento_rechaza_cierre_invalido(conn, cierre):
    with pytest.raises(ValueError):
        db.set_tarjeta_vencimiento(conn, "2026-11", cierre)


@pytest.mark.parametrize("vencimiento_pago", ["2026-11-31", "11/10/2026", "", "2026-11-10T00:00:00"])
def test_set_tarjeta_vencimiento_rechaza_vencimiento_pago_invalido_si_viene(conn, vencimiento_pago):
    with pytest.raises(ValueError):
        db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10", vencimiento_pago)


def test_eliminar_tarjeta_vencimiento_existente_e_inexistente(conn):
    fila = db.set_tarjeta_vencimiento(conn, "2026-11", "2026-11-10")
    assert db.eliminar_tarjeta_vencimiento(conn, fila["id"]) is True
    assert db.get_tarjeta_vencimientos(conn) == []
    # Idempotente: borrar de nuevo (o un id que nunca existió) no explota.
    assert db.eliminar_tarjeta_vencimiento(conn, fila["id"]) is False
    assert db.eliminar_tarjeta_vencimiento(conn, 999999) is False


def test_migracion_renombra_columna_vieja_vencimiento_a_cierre():
    """Simula una base ya inicializada con el esquema VIEJO (columna
    `vencimiento` en vez de `cierre`, sin `vencimiento_pago`) -- como
    estaba el backend real desplegado antes de esta corrección, aunque sin
    filas (verificado en producción: 0 vencimientos cargados). La
    migración debe dejarla usable con el esquema nuevo sin perder nada."""
    connection = db.get_connection(":memory:")
    connection.execute(
        "CREATE TABLE tarjeta_vencimientos (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " mes TEXT NOT NULL UNIQUE, vencimiento TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    connection.commit()
    db.init_db(connection)  # corre las migraciones, incluida la de esta tabla
    assert db.get_tarjeta_vencimientos(connection) == []
    fila = db.set_tarjeta_vencimiento(connection, "2026-11", "2026-11-24", "2026-12-04")
    assert fila["cierre"] == "2026-11-24"
    assert fila["vencimiento_pago"] == "2026-12-04"
    connection.close()


def test_nonempty_legacy_payment_is_preserved_but_not_invented_as_close():
    connection = db.get_connection(":memory:")
    connection.execute("CREATE TABLE tarjeta_vencimientos (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "mes TEXT NOT NULL UNIQUE, vencimiento TEXT NOT NULL, created_at TEXT NOT NULL)")
    connection.execute("INSERT INTO tarjeta_vencimientos VALUES (7, '2026-10', '2026-11-04', 'original')")
    connection.commit()
    db.init_db(connection)
    db.init_db(connection)
    row = db.get_tarjeta_vencimientos(connection)[0]
    assert row["id"] == 7
    assert row["created_at"] == "original"
    assert row["cierre"] is None
    assert row["vencimiento_pago"] == "2026-11-04"
    db.set_tarjeta_vencimiento(connection, "2026-11", "2026-11-24")
    confirmed = db.set_tarjeta_vencimiento(connection, "2026-10", "2026-10-24", "2026-11-04")
    assert confirmed["id"] == 7
    assert confirmed["cierre"] == "2026-10-24"
    connection.close()


def test_incomplete_migration_adds_missing_payment_column_idempotently():
    connection = db.get_connection(":memory:")
    connection.execute("CREATE TABLE tarjeta_vencimientos (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "mes TEXT NOT NULL UNIQUE, cierre TEXT NOT NULL, created_at TEXT NOT NULL)")
    connection.execute("INSERT INTO tarjeta_vencimientos VALUES (1, '2026-10', '2026-10-24', 'original')")
    connection.commit()
    db.init_db(connection)
    db.init_db(connection)
    row = db.get_tarjeta_vencimientos(connection)[0]
    assert row["cierre"] == "2026-10-24"
    assert row["vencimiento_pago"] is None
    db.set_tarjeta_vencimiento(connection, "2026-11", "2026-11-24")
    connection.close()
