"""Tests de alta de gastos (`insert_gasto` / `insert_gasto_con_cuotas`) contra
`reference/api-contract.md` (t_65096083, punto 1).

Contra SQLite efímera (`:memory:`), nunca contra la base real.
"""

import pytest

import db


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
        "tarjeta_id": None,
        "tipo_proporcion": "dinamico",
        "cuotas_total": 1,
        "cuota_nro": 1,
        "confirmado": True,
    }
    gasto.update(overrides)
    return gasto


def test_insert_gasto_basico(conn):
    gasto_id = db.insert_gasto(conn, _gasto_valido())
    fila = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila["monto"] == 15000.5
    assert fila["pagado_por"] == "JD"
    assert fila["deleted_at"] is None


def test_insert_gasto_sin_confirmado_lanza_valueerror(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(confirmado=False))


def test_insert_gasto_custom_requiere_proporciones(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(conn, _gasto_valido(tipo_proporcion="custom"))


def test_insert_gasto_custom_debe_sumar_100(conn):
    with pytest.raises(ValueError):
        db.insert_gasto(
            conn,
            _gasto_valido(
                tipo_proporcion="custom", proporcion_jd=60, proporcion_pinki=30
            ),
        )


def test_insert_gasto_custom_valido(conn):
    gasto_id = db.insert_gasto(
        conn,
        _gasto_valido(
            tipo_proporcion="custom", proporcion_jd=57, proporcion_pinki=43
        ),
    )
    fila = conn.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    assert fila["proporcion_jd"] == 57
    assert fila["proporcion_pinki"] == 43


def test_insert_gasto_con_cuotas_expande_n_filas(conn):
    ids = db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=3000.0), cuotas_total=3)
    assert isinstance(ids, list)
    assert len(ids) == 3

    gastos = db.get_gastos(conn)
    cuotas = [g for g in gastos if g["id"] in ids]
    assert len(cuotas) == 3
    for cuota in cuotas:
        assert cuota["monto"] == 1000.0
        assert cuota["cuotas_total"] == 3
        assert cuota["cuota_ref"] == ids[0]


def test_insert_gasto_con_cuotas_total_uno_devuelve_un_solo_id(conn):
    resultado = db.insert_gasto_con_cuotas(conn, _gasto_valido(), cuotas_total=1)
    assert isinstance(resultado, int)


def test_insert_gasto_con_cuotas_redondeo_100_dividido_3(conn):
    """100 / 3 no es divisible exacto: las 2 primeras cuotas quedan en
    33.33 (ROUND_HALF_UP a centavos) y la última absorbe la diferencia en
    33.34, para que la suma sea exactamente el monto_total (ver README)."""
    ids = db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=100.0), cuotas_total=3)
    gastos = db.get_gastos(conn)
    cuotas = [g for g in gastos if g["id"] in ids]
    assert len(cuotas) == 3
    montos = [cuotas[0]["monto"], cuotas[1]["monto"], cuotas[2]["monto"]]
    assert montos == [33.33, 33.33, 33.34]
    assert round(sum(montos), 2) == 100.00


def test_insert_gasto_con_cuotas_redondeo_1000_dividido_7(conn):
    """1000 / 7 tampoco es divisible exacto: las 6 primeras cuotas quedan
    redondeadas a centavos y la última absorbe la diferencia, sin perder
    ni un centavo del monto_total."""
    ids = db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=1000.0), cuotas_total=7)
    gastos = db.get_gastos(conn)
    cuotas = [g for g in gastos if g["id"] in ids]
    assert len(cuotas) == 7
    montos = [c["monto"] for c in cuotas]
    assert montos[:6] == [142.86] * 6
    assert montos[6] == 142.84
    assert round(sum(montos), 2) == 1000.00


def test_insert_gasto_con_cuotas_monto_exacto_no_cambia_por_el_redondeo(conn):
    """Si monto_total es divisible exacto por cuotas_total, la última
    cuota sigue coincidiendo con las demás (el ajuste de redondeo no
    introduce diferencias donde no las hay)."""
    ids = db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=3000.0), cuotas_total=3)
    gastos = db.get_gastos(conn)
    cuotas = [g for g in gastos if g["id"] in ids]
    montos = [c["monto"] for c in cuotas]
    assert montos == [1000.0, 1000.0, 1000.0]
    assert round(sum(montos), 2) == 3000.00


def test_insert_gasto_con_cuotas_redondeo_no_rompe_atomicidad(conn, monkeypatch):
    """La atomicidad (todo-o-nada) sigue intacta con el cálculo de montos
    por Decimal: si falla una cuota intermedia, ninguna fila queda
    persistida, incluidas las cuotas con monto ya redondeado."""
    original_sumar_meses = db._sumar_meses

    def fake_sumar_meses(fecha_str, meses):
        if meses == 1:  # dispara en la 2da cuota (cuota_nro=2 -> meses=1)
            raise RuntimeError("fallo simulado en cuota intermedia")
        return original_sumar_meses(fecha_str, meses)

    monkeypatch.setattr(db, "_sumar_meses", fake_sumar_meses)

    with pytest.raises(RuntimeError):
        db.insert_gasto_con_cuotas(conn, _gasto_valido(monto=100.0), cuotas_total=3)

    monkeypatch.undo()

    gastos = conn.execute("SELECT * FROM gastos").fetchall()
    assert len(gastos) == 0
