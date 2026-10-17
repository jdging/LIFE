"""Tests de export_dashboard_real.py contra una DB :memory: sintética."""

import db
import export_dashboard_real as export_mod


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _gasto_base(**overrides):
    base = {
        "fecha": "2026-09-01",
        "monto": 1000,
        "categoria": "Hogar",
        "pagado_por": "Común",
        "descripcion_original": "gasto sintético",
        "origen": "texto",
        "confirmado": True,
    }
    base.update(overrides)
    return base


def test_es_gasto_real_incluye_migracion_sin_marcar():
    gasto = {"origen": "migracion", "es_real": 0}
    assert export_mod.es_gasto_real(gasto) is True


def test_es_gasto_real_excluye_no_migrado_sin_marcar():
    gasto = {"origen": "texto", "es_real": 0}
    assert export_mod.es_gasto_real(gasto) is False


def test_es_gasto_real_incluye_no_migrado_marcado_explicitamente():
    gasto = {"origen": "chat", "es_real": 1}
    assert export_mod.es_gasto_real(gasto) is True


def test_filtro_de_gastos_excluye_demo_sin_id_fijo():
    conn = _conn()
    id_migrado = db.insert_gasto(conn, _gasto_base(origen="migracion"))
    id_demo = db.insert_gasto(
        conn, _gasto_base(descripcion_original="Cine con Pinki", monto=17000, origen="texto")
    )
    id_validado = db.insert_gasto(conn, _gasto_base(descripcion_original="compra validada", origen="web"))
    conn.execute("UPDATE gastos SET es_real = 1 WHERE id = ?", (id_validado,))
    conn.commit()

    gastos_reales = [g for g in db.get_gastos(conn) if export_mod.es_gasto_real(g)]
    ids_incluidos = {g["id"] for g in gastos_reales}

    assert id_migrado in ids_incluidos
    assert id_validado in ids_incluidos
    assert id_demo not in ids_incluidos


def test_compras_solo_exporta_items_marcados_es_real():
    conn = _conn()
    id_real = db.insert_lista_compras(
        conn, {"item_nombre": "Puré de tomate 520g", "cantidad_deseada": 1, "unidad": "u"}
    )
    db.insert_lista_compras(conn, {"item_nombre": "Item demo", "cantidad_deseada": 3, "unidad": "u"})
    db.marcar_lista_compras_confirmada(conn, "Puré de tomate 520g", cantidad_deseada=1, unidad="u")

    compras_reales = [c for c in db.get_lista_compras(conn) if c.get("es_real")]

    assert len(compras_reales) == 1
    assert compras_reales[0]["id"] == id_real
    assert "es_real" not in export_mod._sin_marcador_interno(compras_reales[0])


def test_recetas_sin_marcar_quedan_fuera_por_defecto():
    conn = _conn()
    db.insert_receta(conn, {"nombre": "Receta sembrada", "porciones": 2})

    recetas_reales = [r for r in db.get_recetas(conn, activa=True) if r.get("es_real")]

    assert recetas_reales == []


def test_recetas_marcadas_incluyen_ingredientes():
    conn = _conn()
    receta_id = db.insert_receta(conn, {"nombre": "Receta real", "porciones": 2})
    db.insert_receta_ingrediente(
        conn, {"receta_id": receta_id, "ingrediente_nombre": "Tomate", "cantidad": 2, "unidad": "u"}
    )
    db.marcar_receta_real(conn, receta_id)

    recetas_reales = [r for r in db.get_recetas(conn, activa=True) if r.get("es_real")]
    assert len(recetas_reales) == 1
    ingredientes = db.get_receta_ingredientes(conn, receta_id)
    assert len(ingredientes) == 1
    assert ingredientes[0]["ingrediente_nombre"] == "Tomate"


def test_export_fijos_v2_campos_orden_null_y_baja(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(db, "_now", lambda: "2026-10-16T00:00:00+00:00")
    try:
        primero = db.insert_gasto_fijo(conn, {
            "nombre": "Cable", "monto_estimado": 100.01, "periodicidad": "bimestral",
            "vigente_desde": "2026-01-01", "ultima_actualizacion": "2026-01-01T00:00:00+00:00",
            "categoria": "Hogar", "subcategoria": "Internet", "dia_vencimiento": 8,
            "medio_pago": "Débito",
        })
        correccion = db.crear_version_fijo(conn, primero, 120.01, "2026-01-01", actor="JD")
        baja = db.dar_baja_fijo(conn, primero, "2026-03-01", "JD")
        segundo = db.insert_gasto_fijo(conn, {
            "nombre": "Luz", "monto_estimado": 42.0, "periodicidad": "mensual",
            "vigente_desde": "2025-12-01", "ultima_actualizacion": "2025-12-01T00:00:00+00:00",
            "responsable": "Común", "tipo_proporcion": "custom", "proporcion_jd": 60.0,
            "medio_pago": "Transferencia", "categoria": "Servicios",
        })

        campos = {"id", "fijo_grupo_id", "nombre", "monto_estimado", "monto_mensual",
                  "periodicidad", "vigente_desde", "activo", "responsable",
                  "tipo_proporcion", "proporcion_jd", "medio_pago", "categoria",
                  "subcategoria", "dia_vencimiento", "ultima_actualizacion"}
        filas = export_mod.exportar_gastos_fijos(conn)
        assert [set(fila) for fila in filas] == [campos] * 4
        primera_base = {
            "fijo_grupo_id": primero, "nombre": "Cable", "periodicidad": "bimestral",
            "responsable": None, "tipo_proporcion": None, "proporcion_jd": None,
            "medio_pago": "Débito", "categoria": "Hogar", "subcategoria": "Internet",
            "dia_vencimiento": 8,
        }
        assert filas == [
            {**primera_base, "id": primero, "monto_estimado": 100.01,
             "monto_mensual": 50.01, "vigente_desde": "2026-01-01", "activo": 1,
             "ultima_actualizacion": "2026-01-01T00:00:00+00:00"},
            {**primera_base, "id": correccion, "monto_estimado": 120.01,
             "monto_mensual": 60.01, "vigente_desde": "2026-01-01", "activo": 1,
             "ultima_actualizacion": "2026-10-16T00:00:00+00:00"},
            {**primera_base, "id": baja, "monto_estimado": 120.01,
             "monto_mensual": 60.01, "vigente_desde": "2026-03-01", "activo": 0,
             "ultima_actualizacion": "2026-10-16T00:00:00+00:00"},
            {"id": segundo, "fijo_grupo_id": segundo, "nombre": "Luz",
             "monto_estimado": 42.0, "monto_mensual": 42.0,
             "periodicidad": "mensual", "vigente_desde": "2025-12-01", "activo": 1,
             "responsable": "Común", "tipo_proporcion": "custom", "proporcion_jd": 60.0,
             "medio_pago": "Transferencia", "categoria": "Servicios",
             "subcategoria": None, "dia_vencimiento": None,
             "ultima_actualizacion": "2025-12-01T00:00:00+00:00"},
        ]
    finally:
        conn.close()
