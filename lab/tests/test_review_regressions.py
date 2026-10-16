"""Regresiones adversariales exigidas tras el dictamen NO APTO del revisor
independiente (run `3b184396-54a5-49e2-8ff2-62c28c42f1d4`, t_65096083).

Cada test de este archivo está atado explícitamente a uno de los 7 hallazgos
del dictamen (ver `.lasso-runs/3b184396-.../report.md`) o a la "cobertura
faltante" que señaló. Los 67 tests previos validaban las funciones puras de
`validaciones.py` en aislamiento pero NO ejercían las mismas fallas a través
de la capa de `db.py` (que es donde vivían los bugs reales) — este archivo
cierra específicamente esa brecha.

Contra SQLite efímera (`:memory:` o un archivo temporal en `tmp_path`),
nunca contra la base real.
"""

import sqlite3

import pytest

import db
from validaciones import validar_expense, validar_gasto_fijo, validar_ingreso


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def _gasto_valido(**overrides):
    gasto = {
        "fecha": "2026-09-25",
        "monto": 15000.5,
        "moneda": "ARS",
        "categoria": "Comida",
        "subcategoria": "Supermercado",
        "medio_pago": "Crédito",
        "pagado_por": "JD",
        "descripcion_original": "Coto del mes",
        "tipo_proporcion": "dinamico",
        "cuotas_total": 1,
        "cuota_nro": 1,
        "confirmado": True,
    }
    gasto.update(overrides)
    return gasto


def _gasto_fijo_valido(**overrides):
    gasto_fijo = {
        "nombre": "Alquiler",
        "monto_estimado": 100000.0,
        "periodicidad": "mensual",
        "categoria": "Hogar",
        "subcategoria": "Alquiler",
        "responsable": "Común",
        "vigente_desde": "2026-01-01",
    }
    gasto_fijo.update(overrides)
    return gasto_fijo


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


# =============================================================================
# Hallazgo 1 — insert_gasto permitía eludir el contrato de validación
# =============================================================================


def test_insert_gasto_rechaza_monto_cero_via_llamada_directa(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(monto=0))
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


def test_insert_gasto_rechaza_monto_negativo_via_llamada_directa(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(monto=-500))


def test_insert_gasto_rechaza_categoria_vacia_via_llamada_directa(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(categoria=""))


def test_insert_gasto_rechaza_pagado_por_invalido_via_llamada_directa(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(pagado_por="Vecino"))
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


def test_insert_gasto_rechaza_cuotas_total_cero_sin_convertir_a_uno(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(cuotas_total=0))
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


def test_insert_gasto_con_cuotas_rechaza_cuotas_total_cero(conn):
    with pytest.raises(ValueError):
        db.insert_gasto_con_cuotas(conn, _gasto_valido(), cuotas_total=0)
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


def test_insert_gasto_con_cuotas_no_trunca_2_9_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=2900.0), cuotas_total=2.9)
    # Ninguna fila debe quedar persistida: 2.9 no se trunca a 2 cuotas.
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


# =============================================================================
# Hallazgo 2 — expansión de cuotas no atómica + truncamiento/cero
# =============================================================================


def test_insert_gasto_con_cuotas_rollback_total_si_falla_cuota_intermedia(conn, monkeypatch):
    """Fuerza un fallo al calcular la fecha de la 3ra cuota (de 5) y verifica
    que las 2 cuotas ya "insertadas" en la transacción en curso NO quedan
    persistidas: todo-o-nada, sin commits parciales."""
    original_sumar_meses = db._sumar_meses

    def fake_sumar_meses(fecha_str, meses):
        if meses == 2:  # dispara en la 3ra cuota (cuota_nro=3 -> meses=2)
            raise RuntimeError("fallo simulado en cuota intermedia")
        return original_sumar_meses(fecha_str, meses)

    monkeypatch.setattr(db, "_sumar_meses", fake_sumar_meses)

    with pytest.raises(RuntimeError):
        db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=5000.0), cuotas_total=5)

    monkeypatch.undo()

    gastos = conn.execute("SELECT * FROM gastos").fetchall()
    assert len(gastos) == 0  # rollback total: ni las 2 cuotas previas quedaron


def test_insert_gasto_con_cuotas_exito_total_persiste_todas(conn):
    """Contraparte del test anterior: si nada falla, las N cuotas quedan
    todas persistidas (la atomicidad no debe romper el caso feliz)."""
    ids = db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=5000.0), cuotas_total=5)
    assert len(ids) == 5
    gastos = conn.execute("SELECT * FROM gastos").fetchall()
    assert len(gastos) == 5


# =============================================================================
# Hallazgo 3 — baja lógica no atómica ni segura ante concurrencia
# =============================================================================


def test_eliminar_gasto_logico_rollback_si_falla_insert_auditoria(conn):
    """Fuerza el fallo del `INSERT INTO auditoria` con un trigger real de
    SQLite (`RAISE(ABORT, ...)`) en vez de parchear `sqlite3.Connection`
    (tipo built-in inmutable: `monkeypatch.setattr(sqlite3.Connection,
    'execute', ...)` lanza `TypeError`). El trigger solo dispara para este
    `gasto_id` específico, para no afectar otras filas de auditoría."""
    gasto_id = db.insert_gasto(conn, _gasto_valido())

    conn.execute(
        f"""
        CREATE TEMP TRIGGER fallar_auditoria_{int(gasto_id)}
        BEFORE INSERT ON auditoria
        WHEN NEW.fila_id = {int(gasto_id)}
        BEGIN
            SELECT RAISE(ABORT, 'fallo simulado de auditoría');
        END;
        """
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.eliminar_gasto_logico(conn, gasto_id, actor="JD")

    fila = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila["deleted_at"] is None  # el UPDATE se revirtió, no quedó a medias
    assert fila["deleted_by"] is None
    auditoria = conn.execute(
        "SELECT * FROM auditoria WHERE fila_id = ?", (gasto_id,)
    ).fetchall()
    assert auditoria == []


class _ConexionConCarrera(sqlite3.Connection):
    """Subclase real de `sqlite3.Connection` (NO un parche del tipo
    built-in: `monkeypatch.setattr(sqlite3.Connection, 'execute', ...)`
    lanza `TypeError` porque el tipo es inmutable).

    Intercepta únicamente el `UPDATE gastos SET deleted_at` para, justo
    antes de ejecutarlo, dejar que una conexión rival (`_conn_rival`) gane
    la carrera aplicando su propia baja primero sobre el mismo `gasto_id`
    (`_gasto_id_rival`) en la MISMA base en disco. Ambos atributos se setean
    después de construir la instancia, una vez conocido el `gasto_id`.
    """

    _conn_rival = None
    _gasto_id_rival = None

    def execute(self, sql, parameters=()):
        if self._conn_rival is not None and sql.strip().startswith(
            "UPDATE gastos SET deleted_at"
        ):
            self._conn_rival.execute(
                "UPDATE gastos SET deleted_at = ?, deleted_by = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                ("2026-01-01T00:00:00+00:00", "Pinki", self._gasto_id_rival),
            )
            self._conn_rival.commit()
        return super().execute(sql, parameters)


def test_eliminar_gasto_logico_doble_baja_concurrente_no_pisa_la_primera():
    """Simula dos conexiones a la MISMA base en disco intentando borrar el
    mismo gasto: la segunda debe fallar con `ValueError` (vía el chequeo de
    `rowcount` del `UPDATE ... WHERE deleted_at IS NULL`) en vez de pisar
    silenciosamente `deleted_by`/`deleted_at` de la primera."""
    import os
    import tempfile

    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        conn_a = sqlite3.connect(db_path, factory=_ConexionConCarrera)
        conn_a.row_factory = sqlite3.Row
        conn_a.execute("PRAGMA foreign_keys = ON")
        db.init_db(conn_a)
        gasto_id = db.insert_gasto(conn_a, _gasto_valido())

        conn_b = db.get_connection(db_path)

        # A partir de acá, el próximo UPDATE de baja de conn_a "cede el
        # paso" a conn_b, que gana la carrera y borra el gasto primero.
        conn_a._conn_rival = conn_b
        conn_a._gasto_id_rival = gasto_id

        with pytest.raises(ValueError):
            db.eliminar_gasto_logico(conn_a, gasto_id, actor="JD")

        fila = conn_a.execute(
            "SELECT * FROM gastos WHERE id = ?", (gasto_id,)
        ).fetchone()
        # Pinki (conn_b) ganó la carrera; JD (conn_a) no debe haber pisado
        # su baja ni su actor.
        assert fila["deleted_by"] == "Pinki"

        auditoria_jd = conn_a.execute(
            "SELECT * FROM auditoria WHERE fila_id = ? AND actor = 'JD'", (gasto_id,)
        ).fetchall()
        assert auditoria_jd == []  # JD nunca llegó a auditar una baja que no aplicó

        conn_a.close()
        conn_b.close()
    finally:
        if db_path and os.path.exists(db_path):
            os.remove(db_path)


def test_eliminar_gasto_logico_carrera_real_entre_dos_conexiones_a_archivo(tmp_path):
    """Carrera REAL (run 3e22f249, hallazgo 4): dos conexiones SQLite
    independientes a un archivo efímero en disco, cada una en su propio
    hilo de sistema, llaman a `eliminar_gasto_logico` sobre el MISMO gasto
    casi simultáneamente (sincronizadas con `threading.Barrier`), sin
    interceptar ni forzar el orden de ejecución con monkeypatching —a
    diferencia de `test_eliminar_gasto_logico_doble_baja_concurrente_no_pisa_la_primera`,
    que simula la carrera determinísticamente. Debe quedar EXACTAMENTE una
    baja aplicada y EXACTAMENTE una fila de auditoría; la otra conexión
    recibe `ValueError` (nunca una excepción de `sqlite3` sin manejar)."""
    import threading

    db_path = str(tmp_path / "carrera_real.sqlite")

    conn_setup = db.get_connection(db_path)
    db.init_db(conn_setup)
    gasto_id = db.insert_gasto(conn_setup, _gasto_valido())
    conn_setup.close()

    resultados: dict = {}
    barrera = threading.Barrier(2)

    def _intentar_baja(actor):
        conn_hilo = db.get_connection(db_path)
        try:
            barrera.wait(timeout=5)
            db.eliminar_gasto_logico(conn_hilo, gasto_id, actor=actor)
            resultados[actor] = "ok"
        except ValueError:
            resultados[actor] = "rechazado"
        finally:
            conn_hilo.close()

    hilo_jd = threading.Thread(target=_intentar_baja, args=("JD",))
    hilo_pinki = threading.Thread(target=_intentar_baja, args=("Pinki",))
    hilo_jd.start()
    hilo_pinki.start()
    hilo_jd.join()
    hilo_pinki.join()

    assert sorted(resultados.values()) == ["ok", "rechazado"]

    conn_check = db.get_connection(db_path)
    fila = conn_check.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila["deleted_at"] is not None  # exactamente una baja aplicada

    auditoria = conn_check.execute(
        "SELECT * FROM auditoria WHERE fila_id = ? AND accion = 'baja'", (gasto_id,)
    ).fetchall()
    assert len(auditoria) == 1  # exactamente una fila de auditoría, no dos ni cero

    # El actor que efectivamente aplicó la baja coincide con el que ganó.
    ganador = next(actor for actor, resultado in resultados.items() if resultado == "ok")
    assert fila["deleted_by"] == ganador
    assert auditoria[0]["actor"] == ganador

    conn_check.close()


def test_calcular_deudas_mes_excluye_gastos_borrados(conn):
    db.insert_gasto(
        conn,
        _gasto_valido(fecha="2026-05-10", monto=10000.0, pagado_por="JD", categoria="Hogar"),
    )
    borrado_id = db.insert_gasto(
        conn,
        _gasto_valido(fecha="2026-05-12", monto=999999.0, pagado_por="JD", categoria="Hogar"),
    )
    db.eliminar_gasto_logico(conn, borrado_id, actor="JD")

    deuda = db.calcular_deudas_mes(conn, "2026-05")
    # Si el gasto borrado se contara, la deuda sería enorme (999999 de por
    # medio); al excluirse, el monto queda acotado al gasto activo de 10000.
    assert deuda["monto"] < 10000.0


def test_calcular_deudas_pendientes_excluye_gastos_borrados(conn):
    db.insert_gasto(
        conn,
        _gasto_valido(fecha="2026-05-10", monto=10000.0, pagado_por="Pinki", categoria="Hogar"),
    )
    borrado_id = db.insert_gasto(
        conn,
        _gasto_valido(fecha="2026-05-12", monto=999999.0, pagado_por="Pinki", categoria="Hogar"),
    )
    db.eliminar_gasto_logico(conn, borrado_id, actor="Pinki")

    deuda = db.calcular_deudas_pendientes(conn)
    assert deuda["monto"] < 10000.0


def test_calcular_estado_saldado_mes_excluye_gastos_borrados(conn):
    borrado_id = db.insert_gasto(
        conn,
        _gasto_valido(fecha="2026-05-12", monto=1000.0, pagado_por="JD", categoria="Hogar"),
    )
    db.eliminar_gasto_logico(conn, borrado_id, actor="JD")

    # Sin ningún gasto ACTIVO de JD/Pinki ese mes, el estado debe ser
    # 'sin_deuda' — el borrado no debe contar como deuda pendiente.
    assert db.calcular_estado_saldado_mes(conn, "2026-05") == "sin_deuda"


# =============================================================================
# Hallazgo 4 y 5 — fijos: identidad estable, validación de monto/fecha/resp.
# =============================================================================


def test_migracion_gastos_fijos_ejecutada_dos_veces_sobre_base_con_filas_preexistentes(tmp_path):
    """Corre `init_db` dos veces sobre el MISMO archivo de SQLite (no
    `:memory:`) con filas ya cargadas entre medio, simulando un reinicio de
    la app contra una base ya poblada. No debe duplicar columnas, no debe
    fallar, y el backfill de `fijo_grupo_id` no debe reasignar nada en la
    segunda corrida."""
    db_path = str(tmp_path / "migracion_dos_veces.sqlite")

    conn1 = db.get_connection(db_path)
    db.init_db(conn1)
    id_v1 = db.insert_gasto_fijo(conn1, _gasto_fijo_valido(nombre="Expensas"))
    db.crear_version_fijo(conn1, id_v1, 90000.0, vigente_desde="2026-06-01")
    conn1.close()

    # Segunda "corrida" de la app contra el mismo archivo: init_db de nuevo.
    conn2 = db.get_connection(db_path)
    db.init_db(conn2)  # no debe lanzar, ni duplicar columnas/tablas

    columnas = db._column_names(conn2, "gastos_fijos")
    assert "fijo_grupo_id" in columnas

    filas = conn2.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos WHERE nombre = 'Expensas' ORDER BY id"
    ).fetchall()
    assert len(filas) == 2
    assert filas[0]["fijo_grupo_id"] == filas[1]["fijo_grupo_id"] == id_v1

    # El histórico sigue intacto tras la segunda corrida de migración.
    vigente_viejo = db.monto_fijo_vigente_en(conn2, id_v1, "2026-02-01")
    assert vigente_viejo["monto_estimado"] == 100000.0
    conn2.close()


def test_fijos_nombres_duplicados_no_mezclan_vigencia(conn):
    id_a = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Seguro", monto_estimado=5000.0))
    id_b = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Seguro", monto_estimado=8000.0))

    assert db.monto_fijo_vigente_en(conn, id_a, "2026-01-15")["monto_estimado"] == 5000.0
    assert db.monto_fijo_vigente_en(conn, id_b, "2026-01-15")["monto_estimado"] == 8000.0


def test_crear_version_fijo_fecha_vigencia_no_iso_rechazada(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="01/06/2026")


def test_crear_version_fijo_monto_infinito_rechazado(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, float("inf"), vigente_desde="2026-06-01")


def test_validar_gasto_fijo_responsable_invalido():
    errores = validar_gasto_fijo(
        {"monto_estimado": 1000.0, "vigente_desde": "2026-01-01", "responsable": "Vecino"}
    )
    assert any("responsable" in e for e in errores)


# =============================================================================
# Hallazgo 6 — NaN/infinito colaban las validaciones de monto/proporciones
# =============================================================================


def test_validar_expense_rechaza_monto_nan():
    errores = validar_expense({"monto": float("nan"), "categoria": "Hogar"})
    assert any("monto" in e for e in errores)


def test_validar_expense_rechaza_monto_infinito():
    errores = validar_expense({"monto": float("inf"), "categoria": "Hogar"})
    assert any("monto" in e for e in errores)


def test_validar_expense_rechaza_proporciones_nan():
    payload = {
        "monto": 100,
        "categoria": "Hogar",
        "tipo_proporcion": "custom",
        "proporcion_jd": float("nan"),
        "proporcion_pinki": 50,
    }
    errores = validar_expense(payload)
    assert any("proporcion" in e for e in errores)


def test_validar_ingreso_rechaza_monto_nan():
    errores = validar_ingreso({"monto": float("nan"), "persona": "JD", "categoria": "Salario"})
    assert any("monto" in e for e in errores)


def test_insert_gasto_rechaza_monto_nan_via_llamada_directa(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(monto=float("nan")))
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0


def test_insert_ingreso_rechaza_monto_infinito(conn):
    with pytest.raises(ValueError):
        db.insert_ingreso(conn, _ingreso_valido(monto=float("inf")))


def test_crear_version_fijo_rechaza_monto_nan_integral(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, float("nan"), vigente_desde="2026-06-01")
    # El histórico no se tocó: solo existe la versión original.
    todas = db.get_gastos_fijos(conn, solo_activos=False)
    assert len(todas) == 1


# =============================================================================
# Hallazgo 7 — actualizar_ingreso con cambios={} generaba SQL inválido
# =============================================================================


def test_actualizar_ingreso_cambios_vacios_rechazado_explicitamente(conn):
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())
    with pytest.raises(ValueError):
        db.actualizar_ingreso(conn, ingreso_id, {})

    # La fila no debe haberse tocado.
    fila = conn.execute("SELECT * FROM ingresos WHERE id = ?", (ingreso_id,)).fetchone()
    assert fila["monto"] == 500000.0


def test_actualizar_ingreso_cambios_vacios_no_ejecuta_sql_invalido(conn):
    """Verifica explícitamente que el rechazo ocurre ANTES de construir
    cualquier sentencia SQL (no se filtra una excepción de sqlite3 por SQL
    malformado, sino un `ValueError` de validación propio)."""
    ingreso_id = db.insert_ingreso(conn, _ingreso_valido())
    try:
        db.actualizar_ingreso(conn, ingreso_id, {})
    except ValueError:
        pass
    except sqlite3.Error:
        pytest.fail(
            "actualizar_ingreso con cambios={} filtró un error de sqlite3 "
            "(SQL inválido) en vez de rechazar explícitamente con ValueError."
        )


# =============================================================================
# Cobertura faltante adicional señalada por el revisor
# =============================================================================


def test_insert_gasto_con_cuotas_valida_cada_cuota_individualmente(conn):
    """`insert_gasto_con_cuotas` no debe saltarse `validar_expense` para las
    filas generadas: un `pagado_por` inválido en el gasto base debe
    rechazar TODA la expansión, no solo la primera cuota."""
    with pytest.raises(ValueError):
        db.insert_gasto_con_cuotas(
            conn, _gasto_valido(pagado_por="Vecino", monto=3000.0), cuotas_total=3
        )
    assert conn.execute("SELECT COUNT(*) AS n FROM gastos").fetchone()["n"] == 0
