"""Registro y limpieza local de adjuntos Telegram; dry-run salvo --apply."""

import argparse
import json
import os
import sqlite3
import stat
import tempfile
from uuid import uuid4
from contextlib import contextmanager
import fcntl
from datetime import datetime, timedelta, timezone
from pathlib import Path


RETENTION_DAYS = 40
ROOT_MARKER = ".telegram-adjuntos-root"
MANIFEST_NAME = "manifest.json"
ALLOWED_ORIGINAL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def _regular_file_without_symlink(path):
    try:
        return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
    except FileNotFoundError:
        return False


def _dedicated_root(root):
    root = Path(root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("--root debe ser un directorio absoluto existente")
    if root.resolve() == REPO_ROOT or REPO_ROOT in root.resolve().parents:
        raise ValueError("la raíz gestionada debe estar fuera del repositorio")
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise ValueError("--root no puede contener symlinks")
    marker = root / ROOT_MARKER
    if not _regular_file_without_symlink(marker) or marker.read_text(encoding="utf-8") != "telegram-adjuntos-v1\n":
        raise ValueError("--root no es una raíz dedicada de adjuntos Telegram")
    return root


def crear_raiz(root):
    """Marca un directorio vacío fuera del repo; no adopta archivos existentes."""
    root = Path(root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or any(root.iterdir()):
        raise ValueError("--root debe ser un directorio absoluto, vacío y sin symlink")
    if root.resolve() == REPO_ROOT or REPO_ROOT in root.resolve().parents:
        raise ValueError("la raíz gestionada debe estar fuera del repositorio")
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise ValueError("--root no puede contener symlinks")
    root.chmod(0o700)
    (root / "adjuntos").mkdir(mode=0o700)
    (root / "incoming").mkdir(mode=0o700)
    (root / ROOT_MARKER).write_text("telegram-adjuntos-v1\n", encoding="utf-8")
    (root / MANIFEST_NAME).write_text("[]\n", encoding="utf-8")
    (root / ".manifest.lock").touch(mode=0o600)
    return root


@contextmanager
def _locked_manifest(root):
    root = _dedicated_root(root)
    lock_path = root / ".manifest.lock"
    if not _regular_file_without_symlink(lock_path):
        raise ValueError("falta el archivo de bloqueo de la raíz gestionada")
    with lock_path.open("r+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read_manifest(root):
    manifest = root / MANIFEST_NAME
    if not _regular_file_without_symlink(manifest) or manifest.stat().st_size > 2_000_000:
        raise ValueError("manifest.json debe ser regular, sin symlink y medir <=2 MB")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or len(entries) > 10_000:
        raise ValueError("manifest.json debe ser una lista de hasta 10.000 adjuntos")
    seen = set()
    for item in entries:
        path = _managed_path(root, item)
        _received_at(item["received_at"])
        if path in seen:
            raise ValueError("manifest.json contiene un adjunto duplicado")
        seen.add(path)
    return entries


def _write_manifest(root, entries):
    if len(entries) > 10_000 or len(json.dumps(entries, ensure_ascii=False).encode("utf-8")) > 2_000_000:
        raise ValueError("manifest.json excede los límites de entradas o tamaño")
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(entries, output, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, root / MANIFEST_NAME)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def registrar_original(root, source, *, received_at=None):
    """Mueve un original desde incoming/ y registra su recepción atómicamente."""
    source = Path(source)
    if not _regular_file_without_symlink(source) or source.suffix.lower() not in ALLOWED_ORIGINAL_SUFFIXES:
        raise ValueError("el original debe ser un archivo regular admitido, sin symlink")
    received = _received_at(received_at or datetime.now(timezone.utc).isoformat())
    if received > datetime.now(timezone.utc):
        raise ValueError("received_at no puede estar en el futuro")
    with _locked_manifest(root) as root:
        if source.parent != root / "incoming" or not (root / "incoming").is_dir() or (root / "incoming").is_symlink():
            raise ValueError("el original debe estar en incoming/ de la raíz gestionada")
        entries = _read_manifest(root)
        if len(entries) >= 10_000:
            raise ValueError("manifest.json alcanzó el límite de entradas")
        target = root / "adjuntos" / f"{uuid4().hex}{source.suffix.lower()}"
        if not (root / "adjuntos").is_dir() or (root / "adjuntos").is_symlink():
            raise ValueError("adjuntos/ debe ser un directorio regular")
        try:
            os.replace(source, target)
            entry = {"path": str(target.relative_to(root)), "kind": "original", "received_at": received.isoformat()}
            _write_manifest(root, entries + [entry])
        except Exception:
            if target.exists():
                os.replace(target, source)
            raise
        return target


def registrar_derivado(root, original, temporary_png):
    """Publica un PNG generado dentro de la raíz con la fecha del original."""
    with _locked_manifest(root) as root:
        entries = _read_manifest(root)
        original = Path(original)
        source_entry = next((item for item in entries if item["kind"] == "original" and root / item["path"] == original), None)
        if source_entry is None or not _regular_file_without_symlink(original):
            raise ValueError("el PDF debe ser un original registrado y existente")
        temporary_png = Path(temporary_png)
        if temporary_png.parent != root / "adjuntos" or not _regular_file_without_symlink(temporary_png):
            raise ValueError("el PNG temporal debe estar dentro de adjuntos/")
        target = root / "adjuntos" / f"{uuid4().hex}.png"
        try:
            os.replace(temporary_png, target)
            entry = {"path": str(target.relative_to(root)), "kind": "rendered_png", "received_at": source_entry["received_at"]}
            _write_manifest(root, entries + [entry])
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target


def exigir_original_y_salida(root, original, out_dir):
    root = _dedicated_root(root)
    if Path(out_dir) != root / "adjuntos":
        raise ValueError("--out-dir debe ser adjuntos/ de la raíz gestionada")
    entries = _read_manifest(root)
    if not any(item["kind"] == "original" and root / item["path"] == Path(original) for item in entries):
        raise ValueError("el PDF debe ser un original registrado")
    return root


def received_at_para_original(original):
    original = Path(original).absolute()
    root = _dedicated_root(original.parent.parent)
    entries = _read_manifest(root)
    item = next((item for item in entries if item["kind"] == "original" and root / item["path"] == original), None)
    if item is None or not _regular_file_without_symlink(original):
        raise ValueError("el original no figura en el manifiesto gestionado")
    return item["received_at"]


def _received_at(value):
    if not isinstance(value, str):
        raise ValueError("received_at debe ser una fecha/hora ISO con zona horaria")
    try:
        received = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("received_at debe ser una fecha/hora ISO válida") from exc
    if received.tzinfo is None or received.utcoffset() is None:
        raise ValueError("received_at debe incluir zona horaria")
    return received.astimezone(timezone.utc)


def _managed_path(root, item):
    if not isinstance(item, dict) or set(item) != {"path", "received_at", "kind"}:
        raise ValueError("cada entrada debe contener path, received_at y kind")
    raw = item["path"]
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ValueError("path de adjunto inválido")
    parts = raw.split("/")
    if len(parts) < 2 or parts[0] != "adjuntos" or any(part in ("", ".", "..") for part in parts):
        raise ValueError("los adjuntos deben estar bajo adjuntos/ sin rutas relativas externas")
    path = root.joinpath(*parts)
    kind = item["kind"]
    if kind == "original":
        suffixes = ALLOWED_ORIGINAL_SUFFIXES
    elif kind == "rendered_png":
        suffixes = {".png"}
    else:
        raise ValueError("kind debe ser original o rendered_png")
    if path.suffix.lower() not in suffixes:
        raise ValueError("extensión incompatible con kind")
    for component in (root.joinpath(*parts[:index]) for index in range(1, len(parts) + 1)):
        if component.is_symlink():
            raise ValueError("no se aceptan symlinks en rutas de adjuntos")
    if path.exists() and not _regular_file_without_symlink(path):
        raise ValueError("el adjunto gestionado debe ser un archivo regular")
    return path


def _limpiar_adjuntos_locked(root, *, apply=False, ahora=None):
    """Prevalida todo el manifiesto; borra solo candidatos >=40 días al aplicar."""
    root = _dedicated_root(root)
    entries = _read_manifest(root)
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        raise ValueError("ahora debe incluir zona horaria")
    cutoff = ahora.astimezone(timezone.utc) - timedelta(days=RETENTION_DAYS)
    seen = set()
    candidates = []
    for item in entries:
        path = _managed_path(root, item)
        received = _received_at(item["received_at"])
        if path in seen:
            raise ValueError("manifest.json contiene un adjunto duplicado")
        seen.add(path)
        if received <= cutoff and path.exists():
            candidates.append((path, item))
    if apply:
        for path, item in candidates:
            # Segunda comprobación al momento de borrar; unlink jamás sigue
            # un symlink de archivo, y se rechaza antes si aparece uno.
            _managed_path(root, item)
            path.unlink()
        remaining = [item for item in entries if _received_at(item["received_at"]) > cutoff]
        if len(remaining) != len(entries):
            _write_manifest(root, remaining)
    return {
        "aplicado": bool(apply), "dias_retencion": RETENTION_DAYS,
        "candidatos": [str(path.relative_to(root)) for path, _ in candidates],
        "cantidad": len(candidates),
    }


def limpiar_adjuntos(root, *, apply=False, ahora=None):
    """Planifica o borra bajo el mismo bloqueo usado para registrar adjuntos."""
    with _locked_manifest(root) as locked_root:
        return _limpiar_adjuntos_locked(locked_root, apply=apply, ahora=ahora)


def limpiar_coordinado(root, db_path, *, apply=False, ahora=None):
    """Prevalida archivos y texto; aplica archivos primero y después texto.

    Si SQLite falla después del borrado, reintentar es seguro: la limpieza
    de archivos y la de texto son idempotentes.
    """
    import db
    db_path = Path(db_path)
    if not _regular_file_without_symlink(db_path):
        raise ValueError("--db debe apuntar a una base SQLite existente y regular")
    ahora = ahora or datetime.now(timezone.utc)
    archivos = limpiar_adjuntos(root, ahora=ahora)
    conn = db.get_connection(str(db_path))
    try:
        texto = db.limpiar_texto_comprobantes_vencidos(conn, ahora=ahora)
        if apply:
            archivos = limpiar_adjuntos(root, apply=True, ahora=ahora)
            texto = db.limpiar_texto_comprobantes_vencidos(conn, ahora=ahora, apply=True)
    finally:
        conn.close()
    return {"aplicado": bool(apply), "archivos": archivos, "texto": texto}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="raíz dedicada de adjuntos Telegram")
    parser.add_argument("--init", action="store_true", help="marca un directorio vacío como raíz gestionada")
    parser.add_argument("--receive", help="archivo recibido en incoming/ de la raíz")
    parser.add_argument("--received-at", help="instante original de recepción ISO con zona")
    parser.add_argument("--db", help="base SQLite local; coordina borrado de archivos y texto")
    parser.add_argument("--apply", action="store_true", help="borra candidatos; sin esto solo informa")
    args = parser.parse_args(argv)
    try:
        if args.init:
            if args.receive or args.db or args.apply:
                raise ValueError("--init no admite --receive, --db ni --apply")
            crear_raiz(args.root)
            result = {"raiz_gestionada": str(args.root)}
        elif args.receive:
            if args.db or args.apply:
                raise ValueError("--receive no admite --db ni --apply")
            path = registrar_original(args.root, args.receive, received_at=args.received_at)
            result = {"original": str(path)}
        else:
            if args.received_at:
                raise ValueError("--received-at requiere --receive")
            if not args.db:
                raise ValueError("la limpieza coordinada requiere --db")
            result = limpiar_coordinado(args.root, args.db, apply=args.apply)
    except (ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
