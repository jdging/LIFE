"""Tests de los marcadores de procedencia y utilidades nuevas en db.py.

Todo contra DB :memory: sintética. No usan ningún dataset real. No se
ejecutaron en este entorno (rol sin shell) — ver README.md.
"""

import pytest

import db


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def test_gastos_es_real_default_cero():
    conn = _conn()
    gasto_id = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-01",
            "monto": 100,
            "categoria": "Hogar",
            "pagado_por": "Común",
            "confirmado": True,
        },
    )
    fila = conn.execute("SELECT es_real FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila["es_real"] == 0


def test_marcar_lista_compras_confirmada_por_nombre_y_cantidad():
    conn = _conn()
    item_id = db.insert_lista_compras(
        conn, {"item_nombre": "Puré de tomate 520g", "cantidad_deseada": 1, "unidad": "u"}
    )
    db.insert_lista_compras(conn, {"item_nombre": "Puré de tomate 520g", "cantidad_deseada": 3, "unidad": "u"})

    marcado_id = db.marcar_lista_compras_confirmada(
        conn, "Puré de tomate 520g", cantidad_deseada=1, unidad="u"
    )

    assert marcado_id == item_id
    fila = conn.execute("SELECT es_real FROM lista_compras WHERE id = ?", (item_id,)).fetchone()
    assert fila["es_real"] == 1


def test_marcar_lista_compras_confirmada_falla_si_no_hay_match():
    conn = _conn()
    with pytest.raises(ValueError):
        db.marcar_lista_compras_confirmada(conn, "Item que no existe")


def test_marcar_lista_compras_confirmada_falla_si_es_ambiguo():
    conn = _conn()
    db.insert_lista_compras(conn, {"item_nombre": "Leche", "cantidad_deseada": 1, "unidad": "l"})
    db.insert_lista_compras(conn, {"item_nombre": "Leche", "cantidad_deseada": 1, "unidad": "l"})

    with pytest.raises(ValueError):
        db.marcar_lista_compras_confirmada(conn, "Leche", cantidad_deseada=1, unidad="l")


def test_marcar_receta_real_valida_id_existente():
    conn = _conn()
    with pytest.raises(ValueError):
        db.marcar_receta_real(conn, 999)


def test_marcar_receta_real_marca_correctamente():
    conn = _conn()
    receta_id = db.insert_receta(conn, {"nombre": "Receta X"})
    db.marcar_receta_real(conn, receta_id)
    fila = conn.execute("SELECT es_real FROM recetas WHERE id = ?", (receta_id,)).fetchone()
    assert fila["es_real"] == 1


def test_calcular_estado_saldado_mes_sin_deuda():
    conn = _conn()
    assert db.calcular_estado_saldado_mes(conn, "2026-09") == "sin_deuda"


def test_calcular_estado_saldado_mes_pendiente():
    conn = _conn()
    db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-05",
            "monto": 1000,
            "categoria": "Hogar",
            "pagado_por": "JD",
            "confirmado": True,
        },
    )
    assert db.calcular_estado_saldado_mes(conn, "2026-09") == "pendiente"


def test_calcular_estado_saldado_mes_saldado():
    conn = _conn()
    gasto_id = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-05",
            "monto": 1000,
            "categoria": "Hogar",
            "pagado_por": "JD",
            "confirmado": True,
        },
    )
    conn.execute("UPDATE gastos SET saldado = ? WHERE id = ?", ("2026-09-10", gasto_id))
    conn.commit()
    assert db.calcular_estado_saldado_mes(conn, "2026-09") == "saldado"


def test_calcular_estado_saldado_mes_parcial():
    conn = _conn()
    id_saldado = db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-05",
            "monto": 1000,
            "categoria": "Hogar",
            "pagado_por": "JD",
            "confirmado": True,
        },
    )
    db.insert_gasto(
        conn,
        {
            "fecha": "2026-09-10",
            "monto": 500,
            "categoria": "Hogar",
            "pagado_por": "Pinki",
            "confirmado": True,
        },
    )
    conn.execute("UPDATE gastos SET saldado = ? WHERE id = ?", ("2026-09-15", id_saldado))
    conn.commit()
    assert db.calcular_estado_saldado_mes(conn, "2026-09") == "parcial"
