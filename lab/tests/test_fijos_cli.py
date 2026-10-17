"""CLI local, exclusivamente contra archivos temporales."""

import json

import pytest

import db
import fijos_cli


def test_cli_sin_confirmar_no_escribe(tmp_path, capsys):
    ruta = tmp_path / "fijos_cli.sqlite"
    conn = db.get_connection(str(ruta))
    db.init_db(conn)
    conn.close()
    alta = ["--db", str(ruta), "alta", "--nombre", "Luz", "--monto", "100",
            "--periodicidad", "mensual", "--responsable", "Común",
            "--desde", "2026-01-01", "--actor", "JD"]
    assert fijos_cli.main(alta + ["--json"]) == 2
    assert json.loads(capsys.readouterr().out)["requiere_confirmacion"] is True
    conn = db.get_connection(str(ruta))
    assert conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0] == 0
    conn.close()
    assert fijos_cli.main(alta + ["--confirmar"]) == 0
    capsys.readouterr()
    conn = db.get_connection(str(ruta))
    assert conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0] == 1
    conn.close()
    editar = ["--db", str(ruta), "editar", "1", "--nombre", "Electricidad",
              "--desde", "2026-02-01", "--actor", "Pinki"]
    assert fijos_cli.main(editar) == 2
    capsys.readouterr()
    baja = ["--db", str(ruta), "baja", "1", "--desde", "2026-02-01", "--actor", "JD"]
    assert fijos_cli.main(baja) == 2
    conn = db.get_connection(str(ruta))
    assert conn.execute("SELECT COUNT(*) FROM gastos_fijos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("fecha", ["2026-1-1", "2026-01-1", "2026-02-29",
                                 "2026-13-01", "2026-W01-1", "texto"])
def test_cli_listar_rechaza_fecha_invalida(tmp_path, capsys, fecha):
    ruta = tmp_path / "fijos_cli.sqlite"
    conn = db.get_connection(str(ruta))
    db.init_db(conn)
    db.insert_gasto_fijo(conn, {"nombre": "Luz", "monto_estimado": 100,
                                 "periodicidad": "mensual", "vigente_desde": "2024-02-29"})
    conn.close()

    assert fijos_cli.main(["--db", str(ruta), "listar", "--fecha", fecha]) == 1
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_cli_listar_acepta_fecha_bisiesta(tmp_path, capsys):
    ruta = tmp_path / "fijos_cli.sqlite"
    conn = db.get_connection(str(ruta))
    db.init_db(conn)
    db.insert_gasto_fijo(conn, {"nombre": "Luz", "monto_estimado": 100,
                                 "periodicidad": "mensual", "vigente_desde": "2024-02-29"})
    conn.close()

    assert fijos_cli.main(["--db", str(ruta), "listar", "--fecha", "2024-02-29",
                           "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["nombre"] == "Luz"
