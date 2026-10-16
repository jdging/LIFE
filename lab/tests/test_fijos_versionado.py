"""Tests de versionado real de `gastos_fijos` (t_65096083 / t_85b8502b).

Cubre el bug reportado por CPO: `actualizar_monto_fijo` pisaba el histórico
de montos. Acá se verifica que `crear_version_fijo` preserva el histórico,
que `monto_fijo_vigente_en` devuelve el monto correcto para una fecha vieja
aun después de crear una versión más nueva, y que varias versiones con el
mismo `vigente_desde` (corregir un fijo más de una vez el mismo día) son un
caso válido: ninguna se pisa, y la vigente se resuelve de forma
determinística por `(vigente_desde, id)` (gana la de mayor `id`). También
cubre `get_fijos_vigentes`, que devuelve una fila por serie con la versión
vigente a una fecha dada.

Contra SQLite efímera (`:memory:`), nunca contra la base real.
"""

import sqlite3

import pytest

import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


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


def test_migracion_agrega_columna_vigente_desde(conn):
    columnas = db._column_names(conn, "gastos_fijos")
    assert "vigente_desde" in columnas
    assert "responsable" in columnas
    assert "fijo_grupo_id" in columnas


def test_insert_gasto_fijo_fija_fijo_grupo_id_a_si_mismo(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    fila = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila["fijo_grupo_id"] == id_v1


def test_crear_version_fijo_inserta_fila_nueva_sin_tocar_la_anterior(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(monto_estimado=100000.0))

    id_v2 = db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="2026-06-01")

    assert id_v2 != id_v1

    fila_v1 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_v1["monto_estimado"] == 100000.0  # la versión vieja no se tocó

    fila_v2 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v2,)).fetchone()
    assert fila_v2["fijo_grupo_id"] == id_v1  # misma serie que la v1, identidad estable

    todas = db.get_gastos_fijos(conn, solo_activos=False)
    assert len(todas) == 2


def test_monto_fijo_vigente_en_devuelve_monto_viejo_para_mes_viejo(conn):
    id_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(monto_estimado=100000.0, vigente_desde="2026-01-01")
    )
    db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="2026-06-01")

    vigente_mes_viejo = db.monto_fijo_vigente_en(conn, id_v1, "2026-03-15")
    assert vigente_mes_viejo["monto_estimado"] == 100000.0

    vigente_mes_nuevo = db.monto_fijo_vigente_en(conn, id_v1, "2026-07-01")
    assert vigente_mes_nuevo["monto_estimado"] == 120000.0


def test_monto_fijo_vigente_en_fecha_anterior_a_toda_version_da_none(conn):
    id_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(monto_estimado=100000.0, vigente_desde="2026-01-01")
    )
    db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="2026-06-01")

    assert db.monto_fijo_vigente_en(conn, id_v1, "2025-12-01") is None


def test_nombres_duplicados_no_mezclan_historial_via_fijo_grupo_id(conn):
    """Dos gastos fijos DISTINTOS con el mismo `nombre` (ej. dos "Internet",
    uno de casa y otro de la oficina) no deben mezclar su historial: cada
    serie tiene su propio `fijo_grupo_id`, independiente de `nombre`."""
    id_casa_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Internet", monto_estimado=10000.0)
    )
    id_oficina_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Internet", monto_estimado=25000.0)
    )
    assert id_casa_v1 != id_oficina_v1

    db.crear_version_fijo(conn, id_casa_v1, 11000.0, vigente_desde="2026-06-01")

    vigente_casa = db.monto_fijo_vigente_en(conn, id_casa_v1, "2026-07-01")
    vigente_oficina = db.monto_fijo_vigente_en(conn, id_oficina_v1, "2026-07-01")

    assert vigente_casa["monto_estimado"] == 11000.0
    assert vigente_oficina["monto_estimado"] == 25000.0  # no se vio afectada


def test_crear_version_fijo_permite_renombrar_preservando_historial(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Cable"))
    id_v2 = db.crear_version_fijo(
        conn, id_v1, 150000.0, vigente_desde="2026-09-01", nombre="Streaming"
    )

    vigente_antes_del_rename = db.monto_fijo_vigente_en(conn, id_v1, "2026-03-01")
    vigente_despues_del_rename = db.monto_fijo_vigente_en(conn, id_v1, "2026-10-01")

    assert vigente_antes_del_rename["nombre"] == "Cable"
    assert vigente_despues_del_rename["nombre"] == "Streaming"
    assert vigente_despues_del_rename["id"] == id_v2
    # la fila vieja no se tocó: conserva su nombre original en el histórico
    fila_v1 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_v1["nombre"] == "Cable"


def test_crear_version_fijo_vigente_desde_no_iso_lanza_valueerror(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="2026-2-01")


def test_crear_version_fijo_monto_no_positivo_lanza_valueerror(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, 0, vigente_desde="2026-06-01")


def test_crear_version_fijo_monto_nan_lanza_valueerror(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, id_v1, float("nan"), vigente_desde="2026-06-01")


def test_insert_gasto_fijo_sin_responsable_queda_null_compat_legacy(conn):
    """Compatibilidad legacy con `reference/db.py` (corrección run 3e22f249,
    hallazgo 2): `responsable` siempre fue opcional ahí, default NULL. Un
    alta sin `responsable` NO debe rechazarse acá tampoco — la futura capa
    web sí lo exigirá (ver README), pero esta capa de dominio no le inventa
    un dueño a un gasto fijo legacy."""
    payload = _gasto_fijo_valido()
    del payload["responsable"]
    id_v1 = db.insert_gasto_fijo(conn, payload)
    fila = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila["responsable"] is None


def test_insert_gasto_fijo_responsable_invalido_si_viene_explicito_lanza_valueerror(conn):
    """`responsable` es opcional, pero si SE pasa, sigue validándose contra
    {"Común", "JD", "Pinki"} — la relajación no abre la puerta a cualquier
    valor arbitrario."""
    with pytest.raises(ValueError):
        db.insert_gasto_fijo(conn, _gasto_fijo_valido(responsable="Vecino"))


def test_crear_version_fijo_sobre_serie_con_responsable_null_conserva_null(conn):
    """`crear_version_fijo` / `actualizar_monto_fijo` sobre una serie
    heredada sin `responsable` (NULL) deben seguir funcionando y conservar
    NULL, sin inventar un dueño que nunca se especificó (run 3e22f249,
    hallazgo 2)."""
    payload = _gasto_fijo_valido()
    del payload["responsable"]
    id_v1 = db.insert_gasto_fijo(conn, payload)

    id_v2 = db.crear_version_fijo(conn, id_v1, 120000.0, vigente_desde="2026-06-01")
    fila_v2 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v2,)).fetchone()
    assert fila_v2["responsable"] is None

    id_v3 = db.actualizar_monto_fijo(conn, id_v2, 135000.0)
    fila_v3 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v3,)).fetchone()
    assert fila_v3["responsable"] is None


def test_insert_gasto_fijo_fecha_vigencia_invalida_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_gasto_fijo(conn, _gasto_fijo_valido(vigente_desde="31-01-2026"))


def test_migracion_backfill_fijo_grupo_id_no_consolida_nombres_duplicados_legacy(conn):
    """Dos filas legacy con el mismo `nombre` y `fijo_grupo_id IS NULL` (sin
    ninguna señal de que sean la misma serie) NO deben fusionarse en un
    único grupo al migrar (corrección run 3e22f249, hallazgo 3 — la versión
    anterior de esta migración las fusionaba por `MIN(id)` del mismo
    nombre, lo cual mezclaba silenciosamente el histórico de dos gastos
    fijos DISTINTOS que coinciden en nombre por casualidad). Cada fila
    conserva su propia identidad (`fijo_grupo_id = su propio id`); correr
    la migración 2 veces es idempotente."""
    conn.execute(
        """
        INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, activo, ultima_actualizacion,
             responsable, vigente_desde, fijo_grupo_id)
        VALUES ('Legacy', 1000.0, 'mensual', 1, '2025-01-01', 'Común', '2025-01-01', NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, activo, ultima_actualizacion,
             responsable, vigente_desde, fijo_grupo_id)
        VALUES ('Legacy', 1200.0, 'mensual', 1, '2025-06-01', 'Común', '2025-06-01', NULL)
        """
    )
    conn.commit()

    db._migrar_columnas_gastos_fijos(conn)  # primera corrida
    filas = conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos WHERE nombre = 'Legacy' ORDER BY id"
    ).fetchall()
    assert filas[0]["fijo_grupo_id"] == filas[0]["id"]
    assert filas[1]["fijo_grupo_id"] == filas[1]["id"]
    assert filas[0]["fijo_grupo_id"] != filas[1]["fijo_grupo_id"]

    db._migrar_columnas_gastos_fijos(conn)  # segunda corrida: idempotente
    filas_2 = conn.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos WHERE nombre = 'Legacy' ORDER BY id"
    ).fetchall()
    assert [dict(f) for f in filas] == [dict(f) for f in filas_2]


def test_detectar_fijos_nombre_duplicado_lista_candidatos_pero_no_fusiona(conn):
    """`detectar_fijos_nombre_duplicado` lista los `nombre`s repartidos en
    más de una serie, pero no fusiona ni modifica nada — es diagnóstico
    para revisión manual (run 3e22f249, hallazgo 3)."""
    id_a = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Seguro", monto_estimado=5000.0))
    id_b = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Seguro", monto_estimado=8000.0))
    db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Alquiler"))  # sin duplicado

    candidatos = db.detectar_fijos_nombre_duplicado(conn)
    candidato_seguro = next(c for c in candidatos if c["nombre"] == "Seguro")
    assert sorted(candidato_seguro["fijo_grupo_ids"]) == sorted([id_a, id_b])
    assert "Alquiler" not in {c["nombre"] for c in candidatos}

    # Nada se tocó: cada "Seguro" sigue en su propia serie con su propio monto.
    assert db.monto_fijo_vigente_en(conn, id_a, "2026-01-15")["monto_estimado"] == 5000.0
    assert db.monto_fijo_vigente_en(conn, id_b, "2026-01-15")["monto_estimado"] == 8000.0


def test_migracion_real_desde_esquema_legacy_de_reference_db(tmp_path):
    """Migra REALMENTE una tabla `gastos_fijos` creada con el DDL legacy
    EXACTO de `reference/db.py` (sin `vigente_desde` ni `fijo_grupo_id`),
    con datos reales que incluyen un `nombre` duplicado (dos gastos fijos
    DISTINTOS que coinciden en "Internet" por casualidad — posible bajo
    ese esquema porque `actualizar_monto_fijo` legacy hacía UPDATE in-place,
    así que nunca había más de una fila por gasto fijo real). Corre
    `db.init_db` dos veces sobre el mismo archivo (run 3e22f249, hallazgo 3)."""
    db_path = str(tmp_path / "legacy_real.sqlite")

    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute(
        """
        CREATE TABLE gastos_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            monto_estimado REAL NOT NULL,
            periodicidad TEXT NOT NULL,
            dia_vencimiento INTEGER,
            categoria TEXT,
            subcategoria TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            ultima_actualizacion TEXT NOT NULL,
            responsable TEXT,
            tipo_proporcion TEXT,
            proporcion_jd REAL,
            medio_pago TEXT
        )
        """
    )
    legacy_conn.executemany(
        """
        INSERT INTO gastos_fijos
            (nombre, monto_estimado, periodicidad, activo, ultima_actualizacion, responsable)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        [
            ("Alquiler", 100000.0, "mensual", "2026-01-01T00:00:00+00:00", "Común"),
            ("Internet", 10000.0, "mensual", "2026-01-01T00:00:00+00:00", "Común"),
            ("Internet", 25000.0, "mensual", "2026-01-01T00:00:00+00:00", "JD"),
        ],
    )
    legacy_conn.commit()
    legacy_conn.close()

    conn1 = db.get_connection(db_path)
    db.init_db(conn1)  # primera corrida de la migración completa sobre datos legacy reales

    columnas = db._column_names(conn1, "gastos_fijos")
    assert "vigente_desde" in columnas
    assert "fijo_grupo_id" in columnas

    filas_internet = conn1.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos WHERE nombre = 'Internet' ORDER BY id"
    ).fetchall()
    assert len(filas_internet) == 2
    assert filas_internet[0]["fijo_grupo_id"] == filas_internet[0]["id"]
    assert filas_internet[1]["fijo_grupo_id"] == filas_internet[1]["id"]
    assert filas_internet[0]["fijo_grupo_id"] != filas_internet[1]["fijo_grupo_id"]

    candidatos = db.detectar_fijos_nombre_duplicado(conn1)
    assert "Internet" in {c["nombre"] for c in candidatos}
    assert "Alquiler" not in {c["nombre"] for c in candidatos}

    conn1.close()

    conn2 = db.get_connection(db_path)
    db.init_db(conn2)  # segunda corrida: no debe reasignar ni duplicar nada
    filas_internet_2 = conn2.execute(
        "SELECT id, fijo_grupo_id FROM gastos_fijos WHERE nombre = 'Internet' ORDER BY id"
    ).fetchall()
    assert [(f["id"], f["fijo_grupo_id"]) for f in filas_internet] == [
        (f["id"], f["fijo_grupo_id"]) for f in filas_internet_2
    ]
    conn2.close()


def test_crear_version_fijo_hereda_nombre_periodicidad_categoria(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido())
    id_v2 = db.crear_version_fijo(conn, id_v1, 150000.0, vigente_desde="2026-09-01")

    fila_v2 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v2,)).fetchone()
    assert fila_v2["nombre"] == "Alquiler"
    assert fila_v2["periodicidad"] == "mensual"
    assert fila_v2["categoria"] == "Hogar"
    assert fila_v2["subcategoria"] == "Alquiler"
    assert fila_v2["responsable"] == "Común"


def test_crear_version_fijo_permite_cambiar_responsable(conn):
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(responsable="Común"))
    id_v2 = db.crear_version_fijo(
        conn, id_v1, 150000.0, vigente_desde="2026-09-01", responsable="JD"
    )

    fila_v2 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v2,)).fetchone()
    assert fila_v2["responsable"] == "JD"


def test_crear_version_fijo_id_inexistente_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.crear_version_fijo(conn, 9999, 100.0, vigente_desde="2026-01-01")


def test_crear_version_fijo_via_id_viejo_parte_de_la_version_vigente_mas_reciente(conn):
    """V1 -> V2 (renombrada + responsable distinto) -> V3 pasando el `id`
    de V1 (histórico, no el de V2): V3 debe heredar nombre/responsable de
    V2 (la versión vigente más reciente de la serie), NO de la fila literal
    V1 que se pasó como `gasto_fijo_id` (run 3e22f249, hallazgo 1)."""
    id_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Cable", responsable="Común", vigente_desde="2026-01-01")
    )
    id_v2 = db.crear_version_fijo(
        conn, id_v1, 120000.0, vigente_desde="2026-06-01", nombre="Streaming", responsable="JD"
    )

    id_v3 = db.crear_version_fijo(conn, id_v1, 150000.0, vigente_desde="2026-09-01")

    assert id_v3 not in (id_v1, id_v2)
    fila_v3 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v3,)).fetchone()
    assert fila_v3["nombre"] == "Streaming"  # heredado de V2, no de V1
    assert fila_v3["responsable"] == "JD"
    assert fila_v3["fijo_grupo_id"] == id_v1

    # V1 y V2 siguen intactas, el histórico no se pisó.
    fila_v1 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_v1["nombre"] == "Cable"
    assert fila_v1["responsable"] == "Común"


def test_crear_version_fijo_permite_dos_versiones_el_mismo_vigente_desde(conn):
    """Corregir dos veces un gasto fijo el mismo día es un uso normal (ej.
    un error de tipeo detectado minutos después de la primera corrección) y
    NO debe fallar (decisión t_65096083, revirtiendo el rechazo de la ronda
    anterior) — pero tampoco se pisa la fila vieja, ambas versiones quedan
    en el histórico."""
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(monto_estimado=8000.0))

    id_v2 = db.crear_version_fijo(conn, id_v1, 9500.0, vigente_desde="2026-01-01")
    id_v3 = db.crear_version_fijo(conn, id_v1, 9600.0, vigente_desde="2026-01-01")

    assert len({id_v1, id_v2, id_v3}) == 3  # tres filas distintas, ninguna se pisó

    todas = db.get_gastos_fijos(conn, solo_activos=False)
    assert len(todas) == 3

    fila_v1 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_v1["monto_estimado"] == 8000.0  # la primera versión no se tocó


def test_dos_versiones_mismo_dia_gana_la_ultima_insertada(conn):
    """Orden determinístico por `(vigente_desde, id)`: entre dos versiones
    con igual `vigente_desde`, la vigente es la de mayor `id` (la insertada
    más recientemente), sin importar el orden de inserción más allá de eso."""
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(monto_estimado=8000.0))
    id_v2 = db.crear_version_fijo(conn, id_v1, 9500.0, vigente_desde="2026-01-01")
    id_v3 = db.crear_version_fijo(conn, id_v1, 9600.0, vigente_desde="2026-01-01")

    assert id_v3 > id_v2 > id_v1

    vigente = db.monto_fijo_vigente_en(conn, id_v1, "2026-01-01")
    assert vigente["id"] == id_v3
    assert vigente["monto_estimado"] == 9600.0


def test_actualizar_monto_fijo_deprecada_no_hace_update_in_place(conn):
    id_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(monto_estimado=100000.0, vigente_desde="2026-01-01")
    )

    id_v2 = db.actualizar_monto_fijo(conn, id_v1, 130000.0)

    assert id_v2 != id_v1
    fila_v1 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_v1["monto_estimado"] == 100000.0  # el histórico no se pisó
    fila_v2 = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v2,)).fetchone()
    assert fila_v2["monto_estimado"] == 130000.0


def test_actualizar_monto_fijo_dos_veces_el_mismo_dia_no_lanza_valueerror(conn):
    """Caso que motivó este ajuste (regresión del test legado
    `lab/tests/test_finanzas.py::test_actualizar_monto_fijo`): insertar un
    fijo hoy y corregirlo dos veces hoy (dos llamadas a
    `actualizar_monto_fijo`, ambas con `vigente_desde=hoy`) no debe fallar."""
    id_v1 = db.insert_gasto_fijo(conn, _gasto_fijo_valido(monto_estimado=8000.0))

    id_v2 = db.actualizar_monto_fijo(conn, id_v1, 9500.0)
    id_v3 = db.actualizar_monto_fijo(conn, id_v1, 9700.0)

    assert len({id_v1, id_v2, id_v3}) == 3
    todas = db.get_gastos_fijos(conn, solo_activos=False)
    assert len(todas) == 3


# --- get_fijos_vigentes -----------------------------------------------------


def test_get_fijos_vigentes_devuelve_una_fila_por_serie(conn):
    id_alquiler = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Alquiler", monto_estimado=100000.0, vigente_desde="2026-01-01")
    )
    db.crear_version_fijo(conn, id_alquiler, 120000.0, vigente_desde="2026-06-01")
    id_internet = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Internet", monto_estimado=10000.0, vigente_desde="2026-01-01")
    )

    vigentes = db.get_fijos_vigentes(conn, fecha="2026-07-01")

    assert len(vigentes) == 2
    por_grupo = {f["fijo_grupo_id"]: f for f in vigentes}
    assert por_grupo[id_alquiler]["monto_estimado"] == 120000.0  # la versión más nueva
    assert por_grupo[id_internet]["monto_estimado"] == 10000.0


def test_get_fijos_vigentes_default_usa_hoy(conn):
    """Sin `fecha`, usa la fecha de hoy — una versión vigente_desde=hoy debe
    aparecer sin pasar `fecha` explícitamente."""
    import datetime

    hoy = datetime.date.today().isoformat()
    db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Gimnasio", monto_estimado=20000.0, vigente_desde=hoy)
    )

    vigentes = db.get_fijos_vigentes(conn)
    assert any(f["nombre"] == "Gimnasio" for f in vigentes)


def test_get_fijos_vigentes_excluye_series_inactivas(conn):
    db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Activo"))
    id_inactivo = db.insert_gasto_fijo(conn, _gasto_fijo_valido(nombre="Inactivo"))
    conn.execute("UPDATE gastos_fijos SET activo = 0 WHERE id = ?", (id_inactivo,))
    conn.commit()

    vigentes = db.get_fijos_vigentes(conn, fecha="2026-12-01")

    nombres = {f["nombre"] for f in vigentes}
    assert "Activo" in nombres
    assert "Inactivo" not in nombres


def test_get_fijos_vigentes_excluye_serie_que_aun_no_empezo_a_la_fecha(conn):
    db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Futuro", vigente_desde="2027-01-01")
    )

    vigentes = db.get_fijos_vigentes(conn, fecha="2026-12-01")

    assert all(f["nombre"] != "Futuro" for f in vigentes)


def test_get_fijos_vigentes_con_dos_versiones_mismo_dia_devuelve_la_ultima_insertada(conn):
    """Mismo escenario que motivó este ajuste, visto a través de
    `get_fijos_vigentes`: fija hoy, corregida dos veces hoy ⇒ `9500` queda
    como vigente (la última insertada), sin pisar la fila original."""
    hoy = db._now()[:10]
    id_v1 = db.insert_gasto_fijo(
        conn, _gasto_fijo_valido(nombre="Internet", monto_estimado=8000.0, vigente_desde=hoy)
    )
    db.actualizar_monto_fijo(conn, id_v1, 9500.0)

    vigentes = db.get_fijos_vigentes(conn, fecha=hoy)

    fijo_internet = next(f for f in vigentes if f["fijo_grupo_id"] == id_v1)
    assert fijo_internet["monto_estimado"] == 9500.0

    fila_original = conn.execute("SELECT * FROM gastos_fijos WHERE id = ?", (id_v1,)).fetchone()
    assert fila_original["monto_estimado"] == 8000.0  # la fila original no se pisó
