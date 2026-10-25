"""Pruebas sintéticas de retención; ningún archivo ni dato real."""

import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import db
import telegram_retencion
import telegram_ingesta


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def _root(tmp_path):
    root = tmp_path / "telegram-dedicado"
    (root / "adjuntos").mkdir(parents=True)
    (root / telegram_retencion.ROOT_MARKER).write_text("telegram-adjuntos-v1\n", encoding="utf-8")
    (root / ".manifest.lock").touch()
    return root


def _entry(name, days, kind="original"):
    return {
        "path": f"adjuntos/{name}",
        "received_at": (NOW - timedelta(days=days)).isoformat(),
        "kind": kind,
    }


def _manifest(root, entries):
    (root / telegram_retencion.MANIFEST_NAME).write_text(json.dumps(entries), encoding="utf-8")


def test_dry_run_39_40_41_dias_y_archivo_ajeno(tmp_path):
    root = _root(tmp_path)
    entries = [_entry("joven.pdf", 39), _entry("limite.pdf", 40),
               _entry("viejo.png", 41, "rendered_png")]
    for entry in entries:
        (root / entry["path"]).write_bytes(b"sintetico")
    outsider = root / "adjuntos" / "ajeno.pdf"
    outsider.write_bytes(b"ajeno")
    _manifest(root, entries)

    plan = telegram_retencion.limpiar_adjuntos(root, ahora=NOW)
    assert plan["aplicado"] is False
    assert plan["candidatos"] == ["adjuntos/limite.pdf", "adjuntos/viejo.png"]
    assert all((root / entry["path"]).exists() for entry in entries)
    assert outsider.exists()

    result = telegram_retencion.limpiar_adjuntos(root, apply=True, ahora=NOW)
    assert result["cantidad"] == 2
    assert (root / "adjuntos/joven.pdf").exists()
    assert not (root / "adjuntos/limite.pdf").exists()
    assert not (root / "adjuntos/viejo.png").exists()
    assert outsider.exists()


@pytest.mark.parametrize("bad_path", ["../fuera.pdf", "/tmp/fuera.pdf", "adjuntos/../fuera.pdf"])
def test_rechaza_rutas_fuera_de_raiz(tmp_path, bad_path):
    root = _root(tmp_path)
    _manifest(root, [{"path": bad_path, "received_at": NOW.isoformat(), "kind": "original"}])
    with pytest.raises(ValueError):
        telegram_retencion.limpiar_adjuntos(root, ahora=NOW)


def test_rechaza_symlink_y_no_borra_destino(tmp_path):
    root = _root(tmp_path)
    target = tmp_path / "externo.pdf"
    target.write_bytes(b"ajeno")
    (root / "adjuntos/enlace.pdf").symlink_to(target)
    _manifest(root, [_entry("enlace.pdf", 41)])
    with pytest.raises(ValueError, match="symlinks"):
        telegram_retencion.limpiar_adjuntos(root, apply=True, ahora=NOW)
    assert target.exists()


def test_exige_raiz_dedicada(tmp_path):
    root = tmp_path / "sin-marca"
    root.mkdir()
    with pytest.raises(ValueError, match="dedicada"):
        telegram_retencion.limpiar_adjuntos(root, ahora=NOW)


def test_recepcion_rechaza_archivo_fuera_de_incoming(tmp_path):
    root = tmp_path / "gestionada"
    root.mkdir()
    telegram_retencion.crear_raiz(root)
    outsider = tmp_path / "outsider.pdf"
    outsider.write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="incoming"):
        telegram_retencion.registrar_original(root, outsider, received_at=NOW.isoformat())
    assert outsider.exists()
    assert json.loads((root / telegram_retencion.MANIFEST_NAME).read_text(encoding="utf-8")) == []


def test_limpieza_texto_acotada_solo_al_comprobante(tmp_path):
    path = tmp_path / "test.sqlite"
    conn = db.get_connection(str(path))
    try:
        db.init_db(conn)
        for days, hash_file in [(39, "hash-39"), (40, "hash-40"), (41, "hash-41")]:
            conn.execute(
                "INSERT INTO comprobantes_telegram "
                "(hash_archivo, nro_operacion, texto_extraido, fecha_detectada, creado_en) "
                "VALUES (?, ?, ?, ?, ?)",
                (hash_file, str(days), "texto sintetico",
                 "2020-01-01" if days == 39 else "2030-01-01",
                 (NOW - timedelta(days=days)).isoformat()),
            )
        conn.commit()
        before = conn.execute("SELECT hash_archivo, nro_operacion, texto_extraido "
                              "FROM comprobantes_telegram ORDER BY id").fetchall()
        plan = db.limpiar_texto_comprobantes_vencidos(conn, ahora=NOW)
        assert plan["candidatos"] == 2
        assert [tuple(row) for row in conn.execute(
            "SELECT hash_archivo, nro_operacion, texto_extraido "
            "FROM comprobantes_telegram ORDER BY id")] == [tuple(row) for row in before]

        db.limpiar_texto_comprobantes_vencidos(conn, ahora=NOW, apply=True)
        rows = conn.execute("SELECT hash_archivo, nro_operacion, texto_extraido "
                            "FROM comprobantes_telegram ORDER BY id").fetchall()
        assert [row["texto_extraido"] for row in rows] == ["texto sintetico", None, None]
        assert [(row["hash_archivo"], row["nro_operacion"]) for row in rows] == [
            ("hash-39", "39"), ("hash-40", "40"), ("hash-41", "41")]
    finally:
        conn.close()


def test_e2e_local_recepcion_derivados_y_retencion_39_40_41(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    root = tmp_path / "gestionada"
    root.mkdir()
    telegram_retencion.crear_raiz(root)
    db_path = tmp_path / "synthetic.sqlite"
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    originals = []
    derivatives = []
    for days in (39, 40, 41):
        staged = root / "incoming" / f"synthetic-{days}.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(staged)
        doc.close()
        received_at = (NOW - timedelta(days=days)).isoformat()
        original = telegram_retencion.registrar_original(root, staged, received_at=received_at)
        assert not staged.exists()
        result = telegram_ingesta.cmd_extraer_pdf(argparse.Namespace(ruta=str(original), out_dir=str(root / "adjuntos")))
        assert result["fuente"] == "sin_texto" and len(result["imagenes"]) == 1
        originals.append(original)
        derivatives.append(Path(result["imagenes"][0]))
        conn.execute(
            "INSERT INTO comprobantes_telegram (hash_archivo, texto_extraido, creado_en) VALUES (?, ?, ?)",
            (f"synthetic-{days}", "texto sintetico", received_at),
        )
    conn.commit()
    outsider = root / "adjuntos" / "outsider.pdf"
    outsider.write_bytes(b"ajeno")
    entries = json.loads((root / telegram_retencion.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert len(entries) == 6
    for days, original, derivative in zip((39, 40, 41), originals, derivatives):
        expected = (NOW - timedelta(days=days)).isoformat()
        assert {entry["received_at"] for entry in entries if entry["path"] in
                (str(original.relative_to(root)), str(derivative.relative_to(root)))} == {expected}

    plan = telegram_retencion.limpiar_coordinado(root, db_path, ahora=NOW)
    assert plan["archivos"]["cantidad"] == 4
    assert plan["texto"]["candidatos"] == 2
    assert all(path.exists() for path in originals + derivatives)
    applied = telegram_retencion.limpiar_coordinado(root, db_path, ahora=NOW, apply=True)
    assert applied["aplicado"] is True
    assert originals[0].exists() and derivatives[0].exists()
    assert all(not path.exists() for path in originals[1:] + derivatives[1:])
    assert outsider.exists()
    texts = conn.execute("SELECT texto_extraido FROM comprobantes_telegram ORDER BY id").fetchall()
    assert [row[0] for row in texts] == ["texto sintetico", None, None]
    conn.close()
