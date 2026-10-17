"""Contrato de dominio de la pestaña de fijos, solo con SQLite efímera."""

import json
import sqlite3

import pytest

import db
import export_dashboard_real


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


def alta(conn, **cambios):
    datos = {"nombre": "Alquiler", "monto_estimado": 100.0,
             "periodicidad": "mensual", "responsable": "Común",
             "vigente_desde": "2026-01-01"}
    datos.update(cambios)
    return db.insert_gasto_fijo(conn, datos, actor="JD")


def auditorias(conn):
    return [dict(fila) for fila in conn.execute(
        "SELECT * FROM auditoria WHERE tabla = 'gastos_fijos' ORDER BY id"
    )]


def test_ediciones_parciales_conservan_identidad_e_historial(conn):
    primero = alta(conn)
    segundo = db.crear_version_fijo(conn, primero, vigente_desde="2026-02-01",
                                    nombre="Alquiler casa", actor="JD")
    tercero = db.crear_version_fijo(conn, primero, 125.0, vigente_desde="2026-03-01",
                                    actor="Pinki")
    historia = db.historial_fijo(conn, primero)
    assert [fila["id"] for fila in historia] == [primero, segundo, tercero]
    assert {fila["fijo_grupo_id"] for fila in historia} == {primero}
    assert historia[1]["monto_estimado"] == 100.0
    assert historia[2]["nombre"] == "Alquiler casa"
    assert historia[0]["vigente_hasta"] == "2026-01-31"
    assert historia[-1]["vigente_hasta"] is None
    assert [fila["accion"] for fila in auditorias(conn)] == ["alta", "version", "version"]
    assert json.loads(auditorias(conn)[1]["antes_json"])["id"] == primero
    assert json.loads(auditorias(conn)[1]["despues_json"])["id"] == segundo


def test_editar_periodicidad_responsable_y_rechazar_sin_cambio(conn):
    fijo = alta(conn)
    version = db.crear_version_fijo(conn, fijo, vigente_desde="2026-04-01",
                                    periodicidad="bimestral", responsable="JD", actor="JD")
    assert db.monto_mensual(dict(conn.execute(
        "SELECT * FROM gastos_fijos WHERE id = ?", (version,)).fetchone())) == 50.0
    with pytest.raises(ValueError, match="no tiene cambios reales"):
        db.crear_version_fijo(conn, fijo, vigente_desde="2026-05-01", actor="JD")
    assert len(db.historial_fijo(conn, fijo)) == 2
    assert len(auditorias(conn)) == 2


def test_edicion_retroactiva_hereda_version_vigente_y_conserva_futuro(conn):
    primero = alta(conn, nombre="Cable", categoria="Hogar", subcategoria="Internet",
                   medio_pago="Débito", dia_vencimiento=5)
    futuro = db.crear_version_fijo(conn, primero, 200.0, "2026-06-01",
                                   nombre="Streaming", responsable="JD", actor="JD")
    retro = db.crear_version_fijo(conn, primero, 150.0, "2026-03-01", actor="JD")
    marzo = db.get_fijos_vigentes(conn, "2026-03-01")[0]
    mayo = db.get_fijos_vigentes(conn, "2026-05-31")[0]
    junio = db.get_fijos_vigentes(conn, "2026-06-01")[0]
    assert [marzo["id"], mayo["id"], junio["id"]] == [retro, retro, futuro]
    assert (marzo["nombre"], marzo["responsable"], marzo["monto_estimado"]) == (
        "Cable", "Común", 150.0)
    assert (marzo["categoria"], marzo["subcategoria"], marzo["medio_pago"],
            marzo["dia_vencimiento"]) == ("Hogar", "Internet", "Débito", 5)
    assert (junio["nombre"], junio["responsable"], junio["monto_estimado"]) == (
        "Streaming", "JD", 200.0)
    assert [fila["id"] for fila in db.historial_fijo(conn, primero)] == [primero, retro, futuro]
    assert json.loads(auditorias(conn)[-1]["antes_json"])["id"] == primero
    with pytest.raises(ValueError, match="inicio de la serie"):
        db.crear_version_fijo(conn, primero, 120.0, "2025-12-31", actor="JD")


def test_edicion_retroactiva_compara_cambios_con_base_de_esa_fecha(conn):
    primero = alta(conn, nombre="Cable")
    futuro = db.crear_version_fijo(conn, primero, 200.0, "2026-06-01",
                                   nombre="Streaming", responsable="JD", actor="JD")
    retro = db.crear_version_fijo(conn, futuro, 200.0, "2026-03-01", actor="JD")
    assert (db.monto_fijo_vigente_en(conn, primero, "2026-03-01")["id"],
            db.monto_fijo_vigente_en(conn, primero, "2026-03-01")["nombre"]) == (
        retro, "Cable")
    with pytest.raises(ValueError, match="no tiene cambios reales"):
        db.crear_version_fijo(conn, primero, 200.0, "2026-04-01", actor="JD")
    assert db.monto_fijo_vigente_en(conn, primero, "2026-06-01")["id"] == futuro


@pytest.mark.parametrize("fecha", ["2026-1-1", "2026-01-1", "2026-13-01",
                                 "2026-02-29", "texto", "2026-W01-1", ""])
def test_get_fijos_vigentes_rechaza_fechas_invalidas(conn, fecha):
    alta(conn)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        db.get_fijos_vigentes(conn, fecha)


def test_get_fijos_vigentes_acepta_dia_bisiesto(conn):
    fijo = alta(conn, vigente_desde="2024-02-29")
    assert db.get_fijos_vigentes(conn, "2024-02-29")[0]["id"] == fijo


def test_baja_conserva_versiones_y_excluye_desde_fecha(conn):
    fijo = alta(conn)
    baja = db.dar_baja_fijo(conn, fijo, "2026-06-15", "JD")
    assert db.get_fijos_vigentes(conn, "2026-06-14")[0]["id"] == fijo
    assert db.get_fijos_vigentes(conn, "2026-06-15") == []
    assert len(db.historial_fijo(conn, fijo)) == 2
    assert db.historial_fijo(conn, fijo)[-1]["id"] == baja
    assert auditorias(conn)[-1]["accion"] == "baja"
    with pytest.raises(ValueError):
        db.dar_baja_fijo(conn, fijo, "2026-06-16", "JD")


def test_edicion_historica_antes_de_baja_no_reactiva(conn):
    primero = alta(conn)
    baja = db.dar_baja_fijo(conn, primero, "2026-06-15", "JD")
    retro = db.crear_version_fijo(conn, baja, 150.0, "2026-03-01", actor="JD")
    assert db.get_fijos_vigentes(conn, "2026-06-14")[0]["id"] == retro
    assert db.get_fijos_vigentes(conn, "2026-06-15") == []
    with pytest.raises(ValueError, match="fuera de alcance"):
        db.crear_version_fijo(conn, primero, 200.0, "2026-06-15", actor="JD")


def test_rango_dos_versiones_dos_tramos_recortados(conn):
    fijo = alta(conn)
    db.crear_version_fijo(conn, fijo, 130.0, vigente_desde="2026-03-01", actor="JD")
    tramos = db.fijos_por_rango(conn, "2026-02-10", "2026-04-20")[0]["tramos"]
    assert [(tramo["desde"], tramo["hasta"]) for tramo in tramos] == [
        ("2026-02-10", "2026-02-28"), ("2026-03-01", "2026-04-20")
    ]
    assert [tramo["monto_estimado"] for tramo in tramos] == [100.0, 130.0]


def test_rango_un_dia_con_variantes_de_la_misma_fecha(conn):
    primero = alta(conn)
    intermedio = db.crear_version_fijo(conn, primero, 120.0, "2026-03-01", actor="JD")
    ultimo = db.crear_version_fijo(conn, primero, 140.0, "2026-03-01", actor="JD")
    tramos = db.fijos_por_rango(conn, "2026-03-01", "2026-03-01")[0]["tramos"]
    assert [(tramo["id"], tramo["desde"], tramo["hasta"], tramo["monto_estimado"])
            for tramo in tramos] == [(ultimo, "2026-03-01", "2026-03-01", 140.0)]
    assert [fila["id"] for fila in db.historial_fijo(conn, primero)] == [primero, intermedio, ultimo]


def test_export_v2_incluye_historico_y_baja(conn):
    fijo = alta(conn, monto_estimado=100.01, periodicidad="bimestral")
    db.crear_version_fijo(conn, fijo, nombre="Nuevo nombre",
                          vigente_desde="2026-02-01", actor="JD")
    db.dar_baja_fijo(conn, fijo, "2026-03-01", "JD")
    filas = export_dashboard_real.exportar_gastos_fijos(conn)
    assert len(filas) == 3
    assert [fila["activo"] for fila in filas] == [1, 1, 0]
    assert [fila["fijo_grupo_id"] for fila in filas] == [fijo] * 3
    assert filas[0]["monto_mensual"] == 50.01
    assert filas[1]["nombre"] == "Nuevo nombre"
    assert set(("id", "vigente_desde", "responsable", "tipo_proporcion",
                "medio_pago", "monto_mensual")) <= set(filas[0])


def test_auditoria_fallida_revierte_alta_version_y_baja(conn):
    fijo = alta(conn)
    conn.execute("""CREATE TRIGGER falla_auditoria BEFORE INSERT ON auditoria
                    WHEN NEW.tabla = 'gastos_fijos' BEGIN SELECT RAISE(ABORT, 'fallo'); END""")
    conn.commit()
    for operacion in (
        lambda: alta(conn, nombre="Otro"),
        lambda: db.crear_version_fijo(conn, fijo, 200, "2026-02-01", actor="JD"),
        lambda: db.dar_baja_fijo(conn, fijo, "2026-02-01", "JD"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            operacion()
    assert len(db.historial_fijo(conn, fijo)) == 1
    assert conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0] == 1
    assert len(auditorias(conn)) == 1
