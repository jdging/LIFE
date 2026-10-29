"""QA browser harness for synthetic Supermercado data on IPv4 loopback only."""
import argparse
import base64
import binascii
import getpass
import hmac
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4
from wsgiref.simple_server import WSGIRequestHandler, make_server

from api import create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 8877
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
ROOT = Path(__file__).resolve().parent.parent / "src" / "lab-dashboard"
CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"


def validate_port(port):
    if isinstance(port, bool) or not isinstance(port, int) or port == 8765 or not 1 <= port <= 65535:
        raise ValueError("puerto QA inválido; 8765 está reservado")
    return port


def create_synthetic_db(directory):
    folder = Path(directory)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("--qa-dir debe indicar un directorio existente y real")
    folder = folder.resolve(strict=True)
    for _ in range(3):
        path = folder / f"supermercado-qa-{uuid4().hex}.sqlite"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        return path
    raise FileExistsError("no se pudo reservar una DB QA nueva")


def _html_without_remote_assets(source):
    lines = source.splitlines(keepends=True)
    return "".join(line for line in lines if not (
        '<link rel="manifest"' in line or '<link rel="apple-touch-icon"' in line or
        '<link rel="preconnect"' in line or '<link href="https://fonts.googleapis.com/' in line or
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@' in line))


def create_qa_app(directory, password, port=DEFAULT_PORT):
    validate_port(port)
    if not isinstance(password, str) or not password:
        raise ValueError("se requiere contraseña de prueba")
    db_path = create_synthetic_db(directory)
    internal_secret = secrets.token_urlsafe(32)
    api = create_app(str(db_path), internal_secret)
    expected_host = f"{HOST}:{port}"
    expected_origin = f"http://{expected_host}"

    def respond(start_response, status, body, content_type="text/plain; charset=utf-8", extra=()):
        headers = [("Content-Type", content_type), ("Content-Length", str(len(body))),
                   ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Content-Security-Policy", CSP), *extra]
        start_response(status, headers)
        return [body]

    def app(environ, start_response):
        if environ.get("HTTP_HOST") != expected_host or environ.get("REMOTE_ADDR") != HOST:
            return respond(start_response, "400 Bad Request", b"Host local invalido")
        auth = environ.get("HTTP_AUTHORIZATION", "")
        try:
            scheme, encoded = auth.split(" ", 1)
            credential = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, supplied = credential.split(":", 1)
        except (ValueError, UnicodeError, binascii.Error):
            username, supplied, scheme = "", "", ""
        allowed = (scheme == "Basic" and hmac.compare_digest(username.encode(), b"qa") and
                   hmac.compare_digest(supplied.encode(), password.encode()))
        if not allowed:
            return respond(start_response, "401 Unauthorized", b"Acceso QA requerido",
                           extra=(("WWW-Authenticate", 'Basic realm="LIFE QA local"'),))
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "")
        if method in {"POST", "PATCH", "DELETE", "PUT"} and environ.get("HTTP_ORIGIN") != expected_origin:
            return respond(start_response, "403 Forbidden", b"Origin invalido")
        if path in ASSETS and method == "GET" and not environ.get("QUERY_STRING"):
            filename, content_type = ASSETS[path]
            content = (ROOT / filename).read_bytes()
            if filename == "index.html":
                content = _html_without_remote_assets(content.decode("utf-8")).encode("utf-8")
            return respond(start_response, "200 OK", content, content_type)
        if not (path == "/api/supermercado" or path.startswith("/api/supermercado/")):
            return respond(start_response, "404 Not Found", b"Ruta QA no permitida")
        proxied = dict(environ)
        proxied.pop("HTTP_AUTHORIZATION", None)
        proxied.pop("HTTP_COOKIE", None)
        proxied.pop("HTTP_X_INTERNAL_PROXY_SECRET", None)
        proxied["HTTP_X_INTERNAL_PROXY_SECRET"] = internal_secret

        def secure_start(status, headers, exc_info=None):
            safe = [(key, value) for key, value in headers if key.lower() not in
                    {"cache-control", "x-content-type-options", "content-security-policy", "set-cookie"}
                    and not key.lower().startswith("access-control-")]
            safe += [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                     ("Content-Security-Policy", CSP)]
            return start_response(status, safe, exc_info)

        return api(proxied, secure_start)

    app.close = api.close
    app.db_path = db_path
    return app


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="QA local descartable de Supermercado; solo 127.0.0.1")
    parser.add_argument("--qa-dir", required=True, help="Directorio existente para crear una DB sintética NUEVA")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    try:
        validate_port(args.port)
        password = getpass.getpass("Contraseña de prueba QA (usuario qa): ")
        app = create_qa_app(args.qa_dir, password, args.port)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    server = make_server(HOST, args.port, app, handler_class=QuietHandler)
    print(f"QA local en http://{HOST}:{args.port}/; DB sintética: {app.db_path}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
