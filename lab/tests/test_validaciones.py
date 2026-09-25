"""Tests unitarios de `validaciones.py`. Sin SQLite, sin I/O: fixtures en
memoria de Python puro (dicts)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validaciones import validar_expense, validar_fixed_update


def _expense_valido(**overrides) -> dict:
    payload = {
        "fecha": "2026-09-25",
        "monto": 15000.5,
        "moneda": "ARS",
        "categoria": "Comida",
        "subcategoria": "Supermercado",
        "medio_pago": "Crédito",
        "pagado_por": "JD",
        "tarjeta_id": "TC1",
        "tipo_proporcion": "dinamico",
        "cuotas_total": 1,
        "cuota_nro": 1,
    }
    payload.update(overrides)
    return payload


# --- validar_expense: casos válidos -----------------------------------------


def test_expense_valido_dinamico():
    assert validar_expense(_expense_valido()) == []


def test_expense_valido_custom_proporciones_exactas():
    payload = _expense_valido(
        tipo_proporcion="custom", proporcion_jd=57, proporcion_pinki=43
    )
    assert validar_expense(payload) == []


def test_expense_valido_custom_proporciones_dentro_de_tolerancia():
    payload = _expense_valido(
        tipo_proporcion="custom", proporcion_jd=57.005, proporcion_pinki=42.995
    )
    assert validar_expense(payload) == []


def test_expense_valido_con_cuotas():
    payload = _expense_valido(cuotas_total=6, cuota_nro=3)
    assert validar_expense(payload) == []


def test_expense_valido_sin_campos_opcionales():
    payload = {"monto": 100, "categoria": "Hogar"}
    assert validar_expense(payload) == []


# --- validar_expense: monto --------------------------------------------------


def test_expense_monto_negativo():
    payload = _expense_valido(monto=-500)
    errores = validar_expense(payload)
    assert any("monto" in e for e in errores)


def test_expense_monto_cero():
    payload = _expense_valido(monto=0)
    errores = validar_expense(payload)
    assert any("monto" in e for e in errores)


def test_expense_monto_no_numerico():
    payload = _expense_valido(monto="mil pesos")
    errores = validar_expense(payload)
    assert any("monto" in e for e in errores)


def test_expense_monto_ausente():
    payload = _expense_valido()
    del payload["monto"]
    errores = validar_expense(payload)
    assert any("monto" in e for e in errores)


# --- validar_expense: categoria ----------------------------------------------


def test_expense_categoria_vacia():
    payload = _expense_valido(categoria="")
    errores = validar_expense(payload)
    assert any("categoria" in e for e in errores)


def test_expense_categoria_ausente():
    payload = _expense_valido()
    del payload["categoria"]
    errores = validar_expense(payload)
    assert any("categoria" in e for e in errores)


# --- validar_expense: pagado_por ---------------------------------------------


def test_expense_pagado_por_invalido():
    payload = _expense_valido(pagado_por="Vecino")
    errores = validar_expense(payload)
    assert any("pagado_por" in e for e in errores)


# --- validar_expense: proporciones -------------------------------------------


def test_expense_proporciones_no_suman_100():
    payload = _expense_valido(
        tipo_proporcion="custom", proporcion_jd=60, proporcion_pinki=30
    )
    errores = validar_expense(payload)
    assert any("proporcion" in e for e in errores)


def test_expense_custom_sin_proporciones():
    payload = _expense_valido(tipo_proporcion="custom")
    errores = validar_expense(payload)
    assert any("proporcion" in e for e in errores)


def test_expense_dinamico_con_proporciones():
    payload = _expense_valido(
        tipo_proporcion="dinamico", proporcion_jd=50, proporcion_pinki=50
    )
    errores = validar_expense(payload)
    assert any("dinamico" in e for e in errores)


def test_expense_tipo_proporcion_invalido():
    payload = _expense_valido(tipo_proporcion="mitad_y_mitad")
    errores = validar_expense(payload)
    assert any("tipo_proporcion" in e for e in errores)


# --- validar_expense: cuotas --------------------------------------------------


def test_expense_cuota_nro_fuera_de_rango():
    payload = _expense_valido(cuotas_total=3, cuota_nro=5)
    errores = validar_expense(payload)
    assert any("cuota_nro" in e for e in errores)


def test_expense_cuota_nro_cero():
    payload = _expense_valido(cuota_nro=0)
    errores = validar_expense(payload)
    assert any("cuota_nro" in e for e in errores)


def test_expense_cuotas_total_cero():
    payload = _expense_valido(cuotas_total=0)
    errores = validar_expense(payload)
    assert any("cuotas_total" in e for e in errores)


def test_expense_cuota_nro_igual_a_cuotas_total_es_valido():
    payload = _expense_valido(cuotas_total=3, cuota_nro=3)
    assert validar_expense(payload) == []


# --- validar_fixed_update -----------------------------------------------------


def test_fixed_update_valido():
    assert validar_fixed_update({"monto_estimado": 85000.0}) == []


def test_fixed_update_monto_negativo():
    errores = validar_fixed_update({"monto_estimado": -1})
    assert any("monto_estimado" in e for e in errores)


def test_fixed_update_monto_cero():
    errores = validar_fixed_update({"monto_estimado": 0})
    assert any("monto_estimado" in e for e in errores)


def test_fixed_update_monto_ausente():
    errores = validar_fixed_update({})
    assert any("monto_estimado" in e for e in errores)


def test_fixed_update_monto_no_numerico():
    errores = validar_fixed_update({"monto_estimado": "ochenta mil"})
    assert any("monto_estimado" in e for e in errores)
