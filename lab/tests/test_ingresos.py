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


# --- Soft delete de ingresos + auditoría (baja lógica, t_ce790609) ---------


def test_migracion_agrega_columnas_soft_delete_ingresos(conn):
    columnas = db._column_names(conn, "ingresos")
    assert "deleted_at" in columnas
    assert "deleted_by" in columnas


def test_eliminar_ingreso_logico_no_borra_fila_fisicamente(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())

    db.eliminar_ingreso_logico(conn, ingreso_id, actor="JD")

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila is not None  # sigue existiendo físicamente
    assert fila["deleted_at"] is not None
    assert fila["deleted_by"] == "JD"


def test_eliminar_ingreso_logico_inserta_auditoria(conn):
    ingreso_id = db.insert_ingreso(
        conn, _ingreso_valido(descripcion_original="Sueldo septiembre")
    )

    db.eliminar_ingreso_logico(conn, ingreso_id, actor="Pinki")

    filas_auditoria = conn.execute(
        "SELECT * FROM auditoria WHERE tabla = 'ingresos' AND fila_id = ?", (ingreso_id,)
    ).fetchall()
    assert len(filas_auditoria) == 1
    auditoria = dict(filas_auditoria[0])
    assert auditoria["accion"] == "baja"
    assert auditoria["actor"] == "Pinki"
    assert auditoria["despues_json"] is None
    assert "Sueldo septiembre" in auditoria["antes_json"]


def test_eliminar_ingreso_logico_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.eliminar_ingreso_logico(conn, 9999, actor="JD")


def test_eliminar_ingreso_logico_ya_borrado_lanza_valueerror(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())
    db.eliminar_ingreso_logico(conn, ingreso_id, actor="JD")

    with pytest.raises(ValueError):
        db.eliminar_ingreso_logico(conn, ingreso_id, actor="Pinki")


def test_get_ingresos_excluye_borrados_por_default(conn):
    activo_id = db.insert_ingreso(conn, _ingreso_valido(descripcion_original="Activo"))
    borrado_id = db.insert_ingreso(conn, _ingreso_valido(descripcion_original="Borrado"))
    db.eliminar_ingreso_logico(conn, borrado_id, actor="JD")

    ingresos = db.get_ingresos(conn)
    ids = [i["id"] for i in ingresos]

    assert activo_id in ids
    assert borrado_id not in ids


def test_get_ingresos_incluye_borrados_si_se_pide_explicitamente(conn):
    activo_id = db.insert_ingreso(conn, _ingreso_valido(descripcion_original="Activo"))
    borrado_id = db.insert_ingreso(conn, _ingreso_valido(descripcion_original="Borrado"))
    db.eliminar_ingreso_logico(conn, borrado_id, actor="JD")

    ingresos = db.get_ingresos(conn, incluir_borrados=True)
    ids = [i["id"] for i in ingresos]

    assert activo_id in ids
    assert borrado_id in ids
    assert len(ingresos) == 2


def test_actualizar_ingreso_sobre_borrado_lanza_valueerror(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido(monto=500000.0))
    db.eliminar_ingreso_logico(conn, ingreso_id, actor="JD")

    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, ingreso_id, {"monto": 1000.0})

    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["monto"] == 500000.0  # no se aplicó el cambio sobre un borrado


# --- calcular_proporcion_mes excluye ingresos borrados ----------------------


def test_calcular_proporcion_mes_recalcula_sin_el_ingreso_borrado(conn):
    jd_id = db.insert_ingreso(
        conn, _ingreso_valido(persona="JD", monto=750000.0, fecha="2026-09-05")
    )
    db.insert_ingreso(
        conn, _ingreso_valido(persona="Pinki", monto=250000.0, fecha="2026-09-10")
    )

    assert db.calcular_proporcion_mes(conn, "2026-09") == {"JD": 75.0, "Pinki": 25.0}

    db.eliminar_ingreso_logico(conn, jd_id, actor="JD")

    assert db.calcular_proporcion_mes(conn, "2026-09") == {"JD": 0.0, "Pinki": 100.0}


def test_calcular_proporcion_mes_fallback_no_usa_salario_borrado(conn):
    """Si el único salario "fuerte" de un mes anterior queda borrado, el
    fallback a ese mes no debe contarlo — septiembre sin salarios propios
    debe heredar la proporción de agosto SIN el ingreso borrado de JD."""
    agosto_jd_id = db.insert_ingreso(
        conn, _ingreso_valido(persona="JD", monto=900000.0, fecha="2026-08-05")
    )
    db.insert_ingreso(
        conn, _ingreso_valido(persona="Pinki", monto=100000.0, fecha="2026-08-05")
    )
    db.eliminar_ingreso_logico(conn, agosto_jd_id, actor="JD")

    assert db.calcular_proporcion_mes(conn, "2026-09") == {"JD": 0.0, "Pinki": 100.0}


def test_migracion_columnas_ingresos_idempotente_sobre_base_vieja():
    """Simula una base vieja sin `deleted_at`/`deleted_by` en `ingresos`
    (esquema previo a t_ce790609): crea la tabla a mano sin esas columnas,
    inserta una fila, y verifica que `_migrar_columnas_ingresos` las agregue
    sin tocar los datos existentes, y que correrla dos veces sea un no-op.
    """
    vieja = db.get_connection(":memory:")
    try:
        vieja.execute(
            """
            CREATE TABLE ingresos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                monto REAL NOT NULL,
                moneda TEXT NOT NULL DEFAULT 'ARS',
                categoria TEXT NOT NULL,
                persona TEXT NOT NULL,
                descripcion_original TEXT,
                origen TEXT NOT NULL DEFAULT 'texto',
                confirmado INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        vieja.execute(
            """
            INSERT INTO ingresos
                (fecha, monto, moneda, categoria, persona, descripcion_original,
                 origen, confirmado, created_at)
            VALUES ('2026-01-01', 123456.0, 'ARS', 'Salario', 'JD', 'Legacy',
                    'migracion', 1, '2026-01-01T00:00:00')
            """
        )
        vieja.commit()

        columnas_antes = db._column_names(vieja, "ingresos")
        assert "deleted_at" not in columnas_antes
        assert "deleted_by" not in columnas_antes

        db._migrar_columnas_ingresos(vieja)  # primera corrida

        columnas_despues = db._column_names(vieja, "ingresos")
        assert "deleted_at" in columnas_despues
        assert "deleted_by" in columnas_despues

        fila = vieja.execute(
            "SELECT * FROM ingresos WHERE descripcion_original = 'Legacy'"
        ).fetchone()
        assert fila["monto"] == 123456.0
        assert fila["deleted_at"] is None

        db._migrar_columnas_ingresos(vieja)  # segunda corrida: idempotente
        filas = vieja.execute("SELECT * FROM ingresos").fetchall()
        assert len(filas) == 1
    finally:
        vieja.close()
