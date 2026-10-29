"""Offline checks for the disposable QA gate; every DB is synthetic and new."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_supermercado import create_qa_app, validate_port


class SupermercadoQaGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.password = "synthetic-qa-password"
        self.app = create_qa_app(self.tmp.name, self.password)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def request(self, method="GET", path="/", auth=True, host="127.0.0.1:8877", origin=None,
                body=None, extra=None):
        content = json.dumps(body).encode() if body is not None else b""
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "HTTP_HOST": host,
                   "REMOTE_ADDR": "127.0.0.1", "QUERY_STRING": "", "CONTENT_LENGTH": str(len(content)),
                   "CONTENT_TYPE": "application/json" if content else "", "wsgi.input": io.BytesIO(content)}
        if auth:
            token = base64.b64encode(f"qa:{self.password}".encode()).decode()
            environ["HTTP_AUTHORIZATION"] = f"Basic {token}"
        if origin is not None:
            environ["HTTP_ORIGIN"] = origin
        environ.update(extra or {})
        result = {}

        def start(status, headers, _exc_info=None):
            result["status"] = int(status.split()[0])
            result["headers"] = dict(headers)

        result["body"] = b"".join(self.app(environ, start))
        return result

    def test_auth_and_headers(self):
        denied = self.request(auth=False)
        self.assertEqual(denied["status"], 401)
        self.assertIn("Basic", denied["headers"]["WWW-Authenticate"])
        self.assertEqual(denied["headers"]["Cache-Control"], "no-store")
        self.assertEqual(denied["headers"]["X-Content-Type-Options"], "nosniff")
        page = self.request()
        self.assertEqual(page["status"], 200)
        self.assertIn(b'id="tab-supermercado"', page["body"])
        self.assertNotIn(b"https://cdn.jsdelivr.net", page["body"])
        self.assertNotIn(b"https://fonts.googleapis.com", page["body"])

    def test_host_origin_and_static_allowlist(self):
        self.assertEqual(self.request(host="evil.example")["status"], 400)
        self.assertEqual(self.request(extra={"REMOTE_ADDR": "192.0.2.1"})["status"], 400)
        for path in ["/.env", "/.git/config", "/docs/CONTEXTO.md", "/data/recetas.json",
                     "/../lab/db.py", "/supermercado-qa.sqlite", "/manifest.webmanifest"]:
            self.assertEqual(self.request(path=path)["status"], 404, path)
        product = {"producto": "Sintético", "unidad": "u", "stock_actual": 0, "stock_deseado": 1}
        self.assertEqual(self.request("POST", "/api/supermercado/productos", body=product)["status"], 403)
        self.assertEqual(self.request("POST", "/api/supermercado/productos", origin="http://evil.example", body=product)["status"], 403)
        self.assertEqual(self.request("POST", "/api/supermercado/productos", origin="http://127.0.0.1:8877", body=product)["status"], 201)

    def test_internal_secret_never_exposed_or_accepted_from_browser(self):
        forged = self.request(extra={"HTTP_X_INTERNAL_PROXY_SECRET": "synthetic-browser-secret"})
        self.assertEqual(forged["status"], 200)
        for response in [forged, self.request(path="/api/supermercado"), self.request(path="/api/unknown")]:
            self.assertNotIn(b"synthetic-browser-secret", response["body"])
            self.assertNotIn("X-Internal-Proxy-Secret", response["headers"])
            self.assertNotIn("Set-Cookie", response["headers"])
        self.assertEqual(self.request(path="/api/unknown")["status"], 404)
        self.assertTrue(json.loads(self.request(path="/api/supermercado")["body"])["resumen"])
        with patch("qa_supermercado.secrets.token_urlsafe", return_value="synthetic-opaque-internal"):
            isolated = create_qa_app(self.tmp.name, self.password)
        try:
            original = self.app
            self.app = isolated
            for path in ["/", "/api/supermercado", "/api/supermercado/lista.pdf"]:
                response = self.request(path=path)
                self.assertNotIn(b"synthetic-opaque-internal", response["body"])
                self.assertNotIn("X-Internal-Proxy-Secret", response["headers"])
            self.app = original
        finally:
            self.app = original
            isolated.close()

    def test_db_is_new_and_restricted_port(self):
        self.assertTrue(Path(self.app.db_path).is_file())
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.sqlite"))), 1)
        second = create_qa_app(self.tmp.name, self.password)
        try:
            self.assertNotEqual(self.app.db_path, second.db_path)
            self.assertEqual(len(list(Path(self.tmp.name).glob("*.sqlite"))), 2)
        finally:
            second.close()
        with self.assertRaises(ValueError):
            validate_port(8765)
        with self.assertRaises(ValueError):
            create_qa_app(self.tmp.name, self.password, 8765)
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.sqlite"))), 2)
        existing = Path(self.tmp.name) / "existing.sqlite"
        existing.write_bytes(b"synthetic untouched marker")
        with self.assertRaises(ValueError):
            create_qa_app(existing, self.password)
        self.assertEqual(existing.read_bytes(), b"synthetic untouched marker")


if __name__ == "__main__":
    unittest.main()
