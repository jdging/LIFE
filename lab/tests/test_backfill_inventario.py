"""Tests de `backfill_inventario_legacy` (t_0e38e74e, corrección del
hallazgo 1 del revisor 46d4f3d5): recupera en bases ya migradas con el
migrador VIEJO la paridad financiera que quedó solo en `notas`.

Dataset sintético, nunca contra `inventario_raw.json` real.
"""

import json
import sys

import pytest

import db
import migrar_datos_reales as migracion


def _fila_legacy():
    return {
        "id": "INV-00001", "descripcion": "Purificador de agua",
        "categoria": "Electrodomesticos", "fecha_compra": "2026-03-03",
        "precio_ars": 138000.0, "cotizacion_usd_compra": 1465.0,
        "precio_usd_compra": 94.2, "proporcion_jd": 50.0,
        "precio_venta_estimado_usd": None, "estado": "Activo",
        "notas": "Viene con filtro de repuesto", "borrado": None,
    }


def _insertar_bien_legacy(conn, fila, notas):
    """Simula una fila migrada con el código VIEJO: solo las columnas
    preexistentes antes de t_0e38e74e (sin los campos financieros nuevos,
    que quedan en NULL tal como los deja `_migrar_columnas_inventario_bienes`
    sobre una base ya poblada — ver test_migracion_columnas_financieras_
    idempotente_sobre_tabla_sin_esas_columnas en test_inventario.py).
    """
    cursor = conn.execute(
        "INSERT INTO inventario_bienes (nombre, categoria, valor_estimado, fecha_adquisicion, notas) "
        "VALUES (?, ?, ?, ?, ?)",
        (fila["descripcion"], fila["categoria"], fila["precio_ars"], fila["fecha_compra"], notas),
    )
    conn.commit()
    return cursor.lastrowid


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


class TestBackfillInventarioLegacy:
    def test_completa_columnas_null_y_recupera_nota_real(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        bien_id = _insertar_bien_legacy(conn, fila, bloque)

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["precio_ars"] == 138000.0
        assert actualizado["cotizacion_usd_compra"] == 1465.0
        assert actualizado["precio_usd_compra"] == 94.2
        assert actualizado["proporcion_jd"] == 50.0
        assert actualizado["estado"] == "Activo"
        assert actualizado["notas"] == "Viene con filtro de repuesto"

        assert resumen["bienes_actualizados"] == 1
        assert resumen["notas_limpiadas"] == 1
        assert resumen["campos_completados"]["precio_ars"] == 1
        assert resumen["campos_completados"]["estado"] == 1
        assert resumen["bienes_sin_match"] == 0
        assert resumen["bienes_con_match_ambiguo"] == 0

    def test_es_idempotente(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        _insertar_bien_legacy(conn, fila, bloque)

        migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        resumen_segunda = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        assert resumen_segunda["bienes_actualizados"] == 0
        assert resumen_segunda["notas_limpiadas"] == 0
        assert all(valor == 0 for valor in resumen_segunda["campos_completados"].values())

    def test_nunca_pisa_un_valor_ya_cargado_por_la_web(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        bien_id = _insertar_bien_legacy(conn, fila, bloque)
        conn.execute(
            "UPDATE inventario_bienes SET precio_usd_compra = ? WHERE id = ?",
            (999.99, bien_id),
        )
        conn.commit()

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["precio_usd_compra"] == 999.99  # no se pisó
        assert actualizado["precio_ars"] == 138000.0  # el resto sí se completó
        assert resumen["campos_completados"]["precio_usd_compra"] == 0

    def test_nota_editada_no_es_elegible(self, conn):
        """Hallazgo 1 del revisor fc195491: la nota editada no solo deja
        intacta la nota, deja de ser elegible para TODO el backfill —
        tampoco se completan las columnas, porque ya no hay procedencia
        legacy verificable."""
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        notas_editadas = bloque + " (actualizado desde la web)"
        bien_id = _insertar_bien_legacy(conn, fila, notas_editadas)

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["notas"] == notas_editadas  # intacta, no coincide exacto
        assert actualizado["precio_ars"] is None  # tampoco se completan las columnas
        assert resumen["notas_limpiadas"] == 0
        assert resumen["bienes_actualizados"] == 0
        assert resumen["bienes_sin_procedencia_legacy"] == 1

    def test_campo_vaciado_por_la_web_despues_del_backfill_no_se_repuebla(self, conn):
        """Hallazgo 2 del revisor fc195491: una vez aplicado el backfill
        (que limpia la nota legacy), si la web vacía después una de las
        columnas ya completadas, una segunda corrida no debe repoblarla —
        la nota ya no es el bloque legacy, así que el bien deja de ser
        elegible para siempre."""
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        bien_id = _insertar_bien_legacy(conn, fila, bloque)

        migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        # La web vacía precio_usd_compra después del backfill.
        conn.execute(
            "UPDATE inventario_bienes SET precio_usd_compra = NULL WHERE id = ?",
            (bien_id,),
        )
        conn.commit()

        resumen_segunda = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["precio_usd_compra"] is None  # no se repuebla
        assert resumen_segunda["bienes_actualizados"] == 0
        assert resumen_segunda["bienes_sin_procedencia_legacy"] == 1

    def test_mismo_nombre_y_fecha_con_otra_categoria_no_se_empareja(self, conn):
        """Hallazgo 1 del revisor fc195491: el emparejamiento exige también
        coincidencia de categoría, no solo nombre + fecha."""
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        _insertar_bien_legacy(conn, fila, bloque)  # categoria="Electrodomesticos"

        fila_otra_categoria = dict(fila, categoria="Otro")
        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila_otra_categoria]})

        assert resumen["bienes_sin_match"] == 1
        assert resumen["bienes_actualizados"] == 0
        filas = conn.execute("SELECT precio_ars FROM inventario_bienes").fetchall()
        assert all(f["precio_ars"] is None for f in filas)

    def test_valores_del_bloque_distintos_a_los_del_raw_se_omite(self, conn):
        """Hallazgo 1 del revisor fc195491: si el bloque legacy en `notas`
        encierra valores distintos a los del raw actual (p.ej. el raw se
        actualizó después de la migración vieja), el bloque ya no coincide
        exactamente con el que generaría `_armar_notas_inventario` para la
        fila actual, así que se omite en vez de completar con datos que no
        corresponden."""
        fila_vieja = _fila_legacy()
        bloque_viejo = migracion._armar_notas_inventario(fila_vieja)
        bien_id = _insertar_bien_legacy(conn, fila_vieja, bloque_viejo)

        fila_actual = dict(fila_vieja, precio_usd_compra=150.0, cotizacion_usd_compra=1500.0)
        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila_actual]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["precio_ars"] is None
        assert actualizado["notas"] == bloque_viejo  # intacta
        assert resumen["bienes_actualizados"] == 0
        assert resumen["bienes_sin_procedencia_legacy"] == 1

    def test_valor_estimado_editado_en_web_con_nota_intacta_no_es_elegible(self, conn):
        """Hallazgo 1 del revisor e54e9da9: editar solo `valor_estimado`
        desde la web deja la nota legacy intacta (el formulario la
        reenvía sin cambios), pero el bien no debe ser elegible porque
        ya no hay paridad financiera verificable."""
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        bien_id = _insertar_bien_legacy(conn, fila, bloque)
        conn.execute(
            "UPDATE inventario_bienes SET valor_estimado = ? WHERE id = ?",
            (150000.0, bien_id),
        )
        conn.commit()

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["valor_estimado"] == 150000.0  # intacto
        assert actualizado["notas"] == bloque  # intacta
        assert actualizado["cotizacion_usd_compra"] is None  # tampoco se completan
        assert resumen["bienes_actualizados"] == 0
        assert resumen["notas_limpiadas"] == 0
        assert resumen["bienes_editados_en_web"] == 1

    def test_valor_estimado_igual_al_raw_es_elegible(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        bien_id = _insertar_bien_legacy(conn, fila, bloque)

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})
        conn.commit()

        actualizado = conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert actualizado["cotizacion_usd_compra"] == 1465.0
        assert resumen["bienes_actualizados"] == 1
        assert resumen["bienes_editados_en_web"] == 0

    def test_sin_match_se_reporta_y_no_se_toca_nada(self, conn):
        fila = _fila_legacy()
        fila["descripcion"] = "Bien que no existe en la base"

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})

        assert resumen["bienes_sin_match"] == 1
        assert resumen["bienes_actualizados"] == 0

    def test_match_ambiguo_no_toca_ninguna_de_las_filas(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        _insertar_bien_legacy(conn, fila, bloque)
        _insertar_bien_legacy(conn, fila, bloque)  # misma clave natural, duplicada

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila]})

        assert resumen["bienes_con_match_ambiguo"] == 1
        assert resumen["bienes_actualizados"] == 0
        filas = conn.execute("SELECT precio_ars FROM inventario_bienes").fetchall()
        assert all(f["precio_ars"] is None for f in filas)

    def test_filas_borrado_en_el_raw_se_ignoran(self, conn):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)
        _insertar_bien_legacy(conn, fila, bloque)
        fila_borrada = dict(fila, borrado=True)

        resumen = migracion.backfill_inventario_legacy(conn, {"Inventario": [fila_borrada]})

        assert resumen["bienes_sin_match"] == 0
        assert resumen["bienes_actualizados"] == 0


class TestBackfillCLI:
    """CLI de `migrar_datos_reales.py --backfill-legacy` (dry-run por
    default, `--apply` explícito para escribir de verdad)."""

    def test_apply_sin_backfill_legacy_falla(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["migrar_datos_reales.py", "--apply"])
        with pytest.raises(SystemExit):
            migracion.main()

    def test_dry_run_no_escribe_y_apply_si(self, monkeypatch, tmp_path, capsys):
        fila = _fila_legacy()
        bloque = migracion._armar_notas_inventario(fila)

        db_path = str(tmp_path / "test.sqlite")
        setup_conn = db.get_connection(db_path)
        db.init_db(setup_conn)
        bien_id = _insertar_bien_legacy(setup_conn, fila, bloque)
        setup_conn.close()

        inventario_path = tmp_path / "inventario_raw.json"
        inventario_path.write_text(json.dumps({"Inventario": [fila]}), encoding="utf-8")
        monkeypatch.setattr(migracion, "INVENTARIO_PATH", inventario_path)

        # `db.get_connection` default (`DEFAULT_DB_PATH`) queda fijado en el
        # momento en que se definió la función: parchear el atributo del
        # módulo no alcanza para redirigirlo. Se reemplaza la función
        # entera para que, sin path explícito, apunte al sqlite de prueba.
        original_get_connection = db.get_connection
        monkeypatch.setattr(db, "get_connection", lambda path=db_path: original_get_connection(path))

        monkeypatch.setattr(sys, "argv", ["migrar_datos_reales.py", "--backfill-legacy"])
        migracion.main()
        assert "DRY-RUN" in capsys.readouterr().out

        verif_conn = original_get_connection(db_path)
        fila_db = verif_conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert fila_db["precio_ars"] is None  # dry-run: no se aplicó nada
        verif_conn.close()

        monkeypatch.setattr(sys, "argv", ["migrar_datos_reales.py", "--backfill-legacy", "--apply"])
        migracion.main()

        verif_conn = original_get_connection(db_path)
        fila_db = verif_conn.execute(
            "SELECT * FROM inventario_bienes WHERE id = ?", (bien_id,)
        ).fetchone()
        assert fila_db["precio_ars"] == 138000.0  # con --apply sí se aplicó
        verif_conn.close()
