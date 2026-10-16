"""Tests de alta/edición de ingresos y `validar_ingreso` (t_65096083, punto 3).

Contra SQLite efímera (`:memory:`), nunca contra la base real.
"""

import pytest

import db
from validaciones import validar_ingreso


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def _ingreso_valido(**overrides):
    ingreso = {
        "fecha": "2026-09-25",
        "monto": 500000.0,
        "moneda": "ARS",
        "categoria": "Salario",
        "persona": "JD",
        "descripcion_original": "Sueldo",
        "confirmado": True,
    }
    ingreso.update(overrides)
    return ingreso


# --- validar_ingreso: casos válidos -----------------------------------------


def test_ingreso_valido():
    assert validar_ingreso(_ingreso_valido()) == []


def test_ingreso_valido_persona_pinki():
    assert validar_ingreso(_ingreso_valido(persona="Pinki")) == []


# --- validar_ingreso: monto ---------------------------------------------------


def test_ingreso_monto_ausente():
    payload = _ingreso_valido()
    del payload["monto"]
    errores = validar_ingreso(payload)
    assert any("monto" in e for e in errores)


def test_ingreso_monto_cero():
    errores = validar_ingreso(_ingreso_valido(monto=0))
    assert any("monto" in e for e in errores)


def test_ingreso_monto_negativo():
    errores = validar_ingreso(_ingreso_valido(monto=-100))
    assert any("monto" in e for e in errores)


def test_ingreso_monto_no_numerico():
    errores = validar_ingreso(_ingreso_valido(monto="quinientos mil"))
    assert any("monto" in e for e in errores)


# --- validar_ingreso: persona --------------------------------------------------


def test_ingreso_persona_ausente():
    payload = _ingreso_valido()
    del payload["persona"]
    errores = validar_ingreso(payload)
    assert any("persona" in e for e in errores)


def test_ingreso_persona_comun_invalida():
    """A diferencia de gastos, un ingreso NO admite 'Común'."""
    errores = validar_ingreso(_ingreso_valido(persona="Común"))
    assert any("persona" in e for e in errores)


def test_ingreso_persona_invalida():
    errores = validar_ingreso(_ingreso_valido(persona="Vecino"))
    assert any("persona" in e for e in errores)


# --- validar_ingreso: categoria -------------------------------------------------


def test_ingreso_categoria_ausente():
    payload = _ingreso_valido()
    del payload["categoria"]
    errores = validar_ingreso(payload)
    assert any("categoria" in e for e in errores)


def test_ingreso_categoria_vacia():
    errores = validar_ingreso(_ingreso_valido(categoria=""))
    assert any("categoria" in e for e in errores)


# --- db.insert_ingreso ---------------------------------------------------------


def test_insert_ingreso_valido(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())
    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["monto"] == 500000.0
    assert fila["persona"] == "JD"


def test_insert_ingreso_sin_confirmado_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_ingreso(conn, _ingreso_valido(confirmado=False))


def test_insert_ingreso_persona_comun_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_ingreso(conn, _ingreso_valido(persona="Común"))


def test_insert_ingreso_monto_invalido_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_ingreso(conn, _ingreso_valido(monto=-1))


# --- db.actualizar_ingreso ------------------------------------------------------


def test_actualizar_ingreso_edicion_valida(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido(monto=500000.0))

    db.actualizar_ingreso(conn, ingreso_id, {"monto": 550000.0, "categoria": "Extra"})

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["monto"] == 550000.0
    assert fila["categoria"] == "Extra"
    assert fila["persona"] == "JD"  # no tocado, se mantiene


def test_actualizar_ingreso_monto_invalido_no_aplica_cambios(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido(monto=500000.0))

    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, ingreso_id, {"monto": -100})

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["monto"] == 500000.0  # no se aplicó el cambio inválido


def test_actualizar_ingreso_persona_invalida_no_aplica_cambios(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido(persona="JD"))

    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, ingreso_id, {"persona": "Común"})

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["persona"] == "JD"


def test_actualizar_ingreso_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, 9999, {"monto": 1000.0})


def test_actualizar_ingreso_campo_no_editable_lanza_valueerror(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())
    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, ingreso_id, {"origen": "manual"})
