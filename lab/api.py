"""API HTTP local (WSGI, stdlib) para LIFE — scope candidato gastos/ingresos/fijos.

Expone sobre SQLite (vía `db.py`, con ajuste puntual del historial) los endpoints
descritos en el brief t_ce790609. `create_app(db_path, internal_secret)` es la
única forma de obtener la app: ambos parámetros son explícitos y obligatorios
(falla cerrado si faltan, nunca usa `db.DEFAULT_DB_PATH`). Importar este
módulo no abre sockets ni escucha nada — eso solo ocurre si se ejecuta como
script (`python api.py ...`), siempre en host fijo 127.0.0.1.

No hay autenticación de usuario real: todas las rutas `/api/*` exigen el
header `X-Internal-Proxy-Secret` (comparación constant-time). El "actor" de
toda escritura queda fijo en `SERVER_ACTOR` — esta capa nunca confía en una
identidad JD/Pinki declarada por el cliente.
"""

import argparse
import hmac
import json
import math
import re
import sqlite3
import sys
from datetime import date
from decimal import Decimal, DecimalException
from urllib.parse import parse_qs
from uuid import uuid4
from wsgiref.simple_server import make_server

import db
import validaciones

MAX_BODY_BYTES = 64 * 1024
MAX_MONEY = Decimal("1000000000000")
MAX_INSTALLMENTS = 120
MAX_SQLITE_ID = 9223372036854775807
SERVER_ACTOR = "sesion_compartida:no_verificado"
HOST = "127.0.0.1"

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_money(value, *, positive=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    amount = Decimal(str(value))
    return (not positive or amount > 0) and abs(amount) <= MAX_MONEY and amount * 100 == (amount * 100).to_integral_value()


def _stored_money(value):
    if not _valid_money(value):
        raise ValueError("monto almacenado inválido")
    return Decimal(str(value))


def _bounded_sum(values):
    total = sum(values, Decimal(0))
    if abs(total) > MAX_MONEY:
        raise ValueError("acumulado fuera de rango")
    return total

ALLOWED_EXPENSE_FIELDS = {
    "fecha", "monto", "moneda", "categoria", "subcategoria", "medio_pago",
    "pagado_por", "descripcion_original", "tarjeta_id", "tipo_proporcion",
    "proporcion_jd", "proporcion_pinki", "cuotas_total",
}
ALLOWED_INCOME_CREATE_FIELDS = {
    "fecha", "monto", "moneda", "categoria", "persona", "descripcion_original",
}
INCOME_EDITABLE_FIELDS = {
    "fecha", "monto", "moneda", "categoria", "persona", "descripcion_original",
}
ALLOWED_FIXED_CREATE_FIELDS = {
    "nombre", "monto_estimado", "periodicidad", "vigente_desde", "responsable",
    "tipo_proporcion", "proporcion_jd",
}
ALLOWED_FIXED_PATCH_FIELDS = {
    "nombre", "monto_estimado", "periodicidad", "responsable", "vigente_desde",
    "tipo_proporcion", "proporcion_jd",
}

_STATUS_TEXT = {
    200: "OK", 201: "Created",
    400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
    405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large",
    422: "Unprocessable Content",
    500: "Internal Server Error",
}


def _is_iso_month(value):
    if not isinstance(value, str) or not _MONTH_RE.match(value):
        return False
    try:
        date.fromisoformat(f"{value}-01")
    except ValueError:
        return False
    return True


def _is_iso_date(value):
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _reject_json_constant(token):
    raise ValueError(f"constante JSON no permitida: {token}")


def _parse_json_int(token):
    # math.isfinite() in the domain converts ints to float; cap before that conversion.
    if len(token.lstrip("-")) > 308:
        raise ValueError("entero JSON fuera de rango")
    return int(token)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("clave JSON duplicada")
        result[key] = value
    return result


def _valid_optional_strings(data, fields):
    return all(
        data[field] is None or isinstance(data[field], str)
        for field in fields if field in data
    )


class _RequestContext:
    def __init__(self, method, path, query, path_params, body, headers):
        self.method = method
        self.path = path
        self.query = query
        self.path_params = path_params
        self.body = body
        self.headers = headers

    def query_param(self, name):
        values = self.query.get(name)
        return values[0] if values else None


class _App:
    ROUTES = (
        ("GET", re.compile(r"^/api/health$"), "health"),
        ("GET", re.compile(r"^/api/expenses$"), "list_expenses"),
        ("POST", re.compile(r"^/api/expenses$"), "create_expense"),
        ("DELETE", re.compile(r"^/api/expenses/(?P<id>\d+)$"), "delete_expense"),
        ("GET", re.compile(r"^/api/income$"), "list_income"),
        ("POST", re.compile(r"^/api/income$"), "create_income"),
        ("PATCH", re.compile(r"^/api/income/(?P<id>\d+)$"), "update_income"),
        ("DELETE", re.compile(r"^/api/income/(?P<id>\d+)$"), "delete_income"),
        ("GET", re.compile(r"^/api/fixed/versions$"), "list_fixed_versions"),
        ("GET", re.compile(r"^/api/fixed/range$"), "fixed_range"),
        ("GET", re.compile(r"^/api/fixed/(?P<id>\d+)/historial$"), "fixed_historial"),
        ("GET", re.compile(r"^/api/fixed$"), "list_fixed"),
        ("POST", re.compile(r"^/api/fixed$"), "create_fixed"),
        ("PATCH", re.compile(r"^/api/fixed/(?P<id>\d+)$"), "update_fixed"),
        ("DELETE", re.compile(r"^/api/fixed/(?P<id>\d+)$"), "delete_fixed"),
        ("GET", re.compile(r"^/api/summary$"), "summary"),
    )
    QUERY_FIELDS = {
        "list_expenses": {"month"}, "list_fixed": {"dateISO"},
        "fixed_range": {"fromISO", "toISO"}, "summary": {"month"},
    }

    def __init__(self, db_path, internal_secret):
        self.db_path = db_path
        self.internal_secret = internal_secret
        self._memory_conn = None
        if db_path == ":memory:":
            self._memory_uri = f"file:life-api-{uuid4().hex}?mode=memory&cache=shared"
            self._memory_conn = self._open_memory_connection()
            db.init_db(self._memory_conn)
        else:
            bootstrap = db.get_connection(db_path)
            try:
                db.init_db(bootstrap)
            finally:
                bootstrap.close()

    # --- infraestructura WSGI -------------------------------------------

    def __call__(self, environ, start_response):
        try:
            return self._handle(environ, start_response)
        except (ValueError, OverflowError, DecimalException):
            return self._error(start_response, 422, "datos almacenados o acumulados inválidos.")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                return self._error(start_response, 409, "base de datos ocupada; reintentar.")
            return self._json(start_response, 500, {"error": "internal_error"})
        except Exception:
            return self._json(start_response, 500, {"error": "internal_error"})

    def _open_memory_connection(self):
        conn = sqlite3.connect(self._memory_uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _get_connection(self):
        if self._memory_conn is not None:
            return self._open_memory_connection()
        return db.get_connection(self.db_path)

    def _release_connection(self, conn):
        conn.close()

    def close(self):
        """Release the anchor for a shared in-memory database."""
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None

    @staticmethod
    def _extract_headers(environ):
        headers = {}
        if environ.get("CONTENT_TYPE"):
            headers["CONTENT-TYPE"] = environ["CONTENT_TYPE"]
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                headers[key[5:].replace("_", "-")] = value
        return headers

    def _check_secret(self, headers):
        provided = headers.get("X-INTERNAL-PROXY-SECRET")
        if not isinstance(provided, str) or not provided:
            return False
        return hmac.compare_digest(provided.encode("utf-8"), self.internal_secret.encode("utf-8"))

    def _match_route(self, method, path):
        allowed_methods = set()
        for route_method, pattern, handler_name in self.ROUTES:
            match = pattern.match(path)
            if match is None:
                continue
            allowed_methods.add(route_method)
            if route_method == method:
                return (handler_name, match.groupdict()), None
        return None, (allowed_methods or None)

    def _handle(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO") or "/"
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        headers = self._extract_headers(environ)

        if not self._check_secret(headers):
            return self._error(start_response, 401, "falta o es inválido el header X-Internal-Proxy-Secret.")
        if any(len(values) != 1 for values in query.values()):
            return self._error(start_response, 400, "parámetro de query repetido.")

        raw_length = environ.get("CONTENT_LENGTH") or "0"
        try:
            content_length = int(raw_length)
        except (TypeError, ValueError):
            return self._error(start_response, 400, "Content-Length inválido.")
        if content_length < 0:
            return self._error(start_response, 400, "Content-Length inválido.")
        if content_length > MAX_BODY_BYTES:
            return self._error(start_response, 413, "el cuerpo excede el límite de 64KiB.")

        result, allowed_methods = self._match_route(method, path)
        if result is None:
            if allowed_methods:
                return self._error(
                    start_response, 405, "método no permitido para esta ruta.",
                    extra_headers=[("Allow", ", ".join(sorted(allowed_methods)))],
                )
            return self._error(start_response, 404, "ruta no encontrada.")

        handler_name, path_params = result
        if set(query) - self.QUERY_FIELDS.get(handler_name, set()):
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        if "id" in path_params:
            raw_id = path_params["id"]
            if len(raw_id) > 19 or not 1 <= int(raw_id) <= MAX_SQLITE_ID:
                return self._error(start_response, 400, "id fuera de rango.")
        if method in {"GET", "DELETE"} and handler_name != "delete_fixed" and content_length:
            return self._error(start_response, 400, "esta ruta no acepta un cuerpo.")
        body = environ["wsgi.input"].read(content_length) if content_length > 0 else b""
        if len(body) != content_length:
            return self._error(start_response, 400, "cuerpo incompleto.")
        ctx = _RequestContext(method, path, query, path_params, body, headers)

        conn = self._get_connection()
        try:
            return getattr(self, handler_name)(ctx, conn, start_response)
        finally:
            self._release_connection(conn)

    # --- helpers de request/response ------------------------------------

    def _json(self, start_response, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ]
        start_response(f"{status} {_STATUS_TEXT.get(status, '')}", headers)
        return [body]

    def _error(self, start_response, status, message, errors=None, extra_headers=None):
        payload = {"error": message}
        if errors:
            payload["errors"] = errors
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        start_response(f"{status} {_STATUS_TEXT.get(status, '')}", headers)
        return [body]

    def _parse_json(self, ctx, start_response):
        content_type = (ctx.headers.get("CONTENT-TYPE") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            return None, self._error(start_response, 400, "Content-Type debe ser application/json.")
        if not ctx.body:
            return None, self._error(start_response, 400, "se requiere un cuerpo JSON.")
        try:
            parsed = json.loads(
                ctx.body.decode("utf-8"), parse_constant=_reject_json_constant,
                parse_int=_parse_json_int, object_pairs_hook=_unique_json_object,
            )
        except (ValueError, UnicodeDecodeError):
            return None, self._error(start_response, 400, "JSON inválido.")
        if not isinstance(parsed, dict):
            return None, self._error(start_response, 400, "el cuerpo debe ser un objeto JSON.")
        return parsed, None

    def _unknown_fields(self, keys, allowed):
        extra = sorted(set(keys) - allowed)
        return extra or None

    # --- health ----------------------------------------------------------

    def health(self, ctx, conn, start_response):
        return self._json(start_response, 200, {
            "ok": True,
            "capabilities": ["expenses", "income", "fixed"],
            "mode": "live",
        })

    # --- expenses ----------------------------------------------------------

    def list_expenses(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), {"month"})
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        month = ctx.query_param("month")
        if month is not None and not _is_iso_month(month):
            return self._error(start_response, 400, "month debe ser 'YYYY-MM' válido.")
        rows = db.get_gastos(conn)
        if month is not None:
            rows = [row for row in rows if (row.get("fecha") or "")[:7] == month]
        for row in rows:
            _stored_money(row["monto"])
        return self._json(start_response, 200, {"expenses": rows})

    def create_expense(self, ctx, conn, start_response):
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), ALLOWED_EXPENSE_FIELDS)
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")
        if "fecha" in data and not _is_iso_date(data["fecha"]):
            return self._error(start_response, 400, "fecha debe ser 'YYYY-MM-DD' válida.")
        if not _valid_optional_strings(data, {
            "moneda", "subcategoria", "medio_pago", "descripcion_original", "tarjeta_id",
        }):
            return self._error(start_response, 400, "campos de texto inválidos.")
        errores = validaciones.validar_expense(data)
        if errores:
            return self._error(start_response, 400, "payload de gasto inválido.")
        if not _valid_money(data.get("monto")):
            return self._error(start_response, 400, "monto fuera de rango o con más de dos decimales.")

        cuotas_total = data.get("cuotas_total")
        if cuotas_total is None:
            cuotas_total = 1
        if cuotas_total > MAX_INSTALLMENTS or Decimal(str(data["monto"])) * 100 < cuotas_total:
            return self._error(start_response, 400, "cuotas_total fuera de rango para el monto.")

        gasto = dict(data)
        gasto["confirmado"] = True
        gasto["origen"] = "api"
        gasto["chat_id"] = None

        try:
            resultado = db.insert_gasto_con_cuotas(conn, gasto, cuotas_total)
        except OverflowError:
            return self._error(start_response, 400, "monto fuera de rango.")
        except (ValueError, sqlite3.IntegrityError):
            return self._error(start_response, 409, "no se pudo crear el gasto.")

        ids = resultado if isinstance(resultado, list) else [resultado]
        creados = [row for row in db.get_gastos(conn) if row["id"] in ids]
        return self._json(start_response, 201, {"expenses": creados})

    def delete_expense(self, ctx, conn, start_response):
        gasto_id = int(ctx.path_params["id"])
        # Reservar el escritor antes de leer evita una promoción de snapshot
        # obsoleto si dos conexiones intentan borrar la misma fila a la vez.
        conn.execute("BEGIN IMMEDIATE")
        fila = conn.execute("SELECT deleted_at, monto FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
        if fila is None:
            conn.rollback()
            return self._error(start_response, 404, f"no existe gasto id={gasto_id}.")
        if fila["deleted_at"] is not None:
            conn.rollback()
            return self._error(start_response, 404, f"no existe gasto id={gasto_id}.")
        if not _valid_money(fila["monto"]):
            conn.rollback()
            return self._error(start_response, 422, "datos almacenados inválidos.")
        try:
            db.eliminar_gasto_logico(conn, gasto_id, SERVER_ACTOR)
        except ValueError:
            return self._error(start_response, 409, "no se pudo borrar el gasto.")
        return self._json(start_response, 200, {"deleted": True, "id": gasto_id})

    # --- income ----------------------------------------------------------

    def list_income(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), set())
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        rows = db.get_ingresos(conn)
        for row in rows:
            _stored_money(row["monto"])
        return self._json(start_response, 200, {"income": rows})

    def create_income(self, ctx, conn, start_response):
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), ALLOWED_INCOME_CREATE_FIELDS)
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")
        if "fecha" in data and not _is_iso_date(data["fecha"]):
            return self._error(start_response, 400, "fecha debe ser 'YYYY-MM-DD' válida.")
        if not _valid_optional_strings(data, {"moneda", "descripcion_original"}):
            return self._error(start_response, 400, "campos de texto inválidos.")
        errores = validaciones.validar_ingreso(data)
        if errores:
            return self._error(start_response, 400, "payload de ingreso inválido.")
        if not _valid_money(data.get("monto")):
            return self._error(start_response, 400, "monto fuera de rango o con más de dos decimales.")

        ingreso = dict(data)
        ingreso["confirmado"] = True
        ingreso["origen"] = "api"

        try:
            nuevo_id = db.insert_ingreso(conn, ingreso)
        except OverflowError:
            return self._error(start_response, 400, "monto fuera de rango.")
        except ValueError:
            return self._error(start_response, 409, "no se pudo crear el ingreso.")

        creado = next(row for row in db.get_ingresos(conn) if row["id"] == nuevo_id)
        return self._json(start_response, 201, {"income": creado})

    def update_income(self, ctx, conn, start_response):
        income_id = int(ctx.path_params["id"])
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), INCOME_EDITABLE_FIELDS)
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")
        if not data:
            return self._error(start_response, 400, "se requiere al menos un campo para editar.")
        if "fecha" in data and not _is_iso_date(data["fecha"]):
            return self._error(start_response, 400, "fecha debe ser 'YYYY-MM-DD' válida.")
        if not _valid_optional_strings(data, {"moneda", "descripcion_original"}):
            return self._error(start_response, 400, "campos de texto inválidos.")

        existentes = db.get_ingresos(conn)
        fila = next((row for row in existentes if row["id"] == income_id), None)
        if fila is None:
            return self._error(start_response, 404, f"no existe ingreso id={income_id}.")

        resultante = {**fila, **data}
        errores = validaciones.validar_ingreso(resultante)
        if errores:
            return self._error(start_response, 400, "edición de ingreso inválida.")
        if not _valid_money(resultante.get("monto")):
            return self._error(start_response, 400, "monto fuera de rango o con más de dos decimales.")

        try:
            db.actualizar_ingreso(conn, income_id, data)
        except OverflowError:
            return self._error(start_response, 400, "monto fuera de rango.")
        except ValueError:
            return self._error(start_response, 409, "no se pudo editar el ingreso.")

        actualizado = next(row for row in db.get_ingresos(conn) if row["id"] == income_id)
        return self._json(start_response, 200, {"income": actualizado})

    def delete_income(self, ctx, conn, start_response):
        income_id = int(ctx.path_params["id"])
        # Mismo patrón que delete_expense: reservar el escritor antes de leer
        # evita una promoción de snapshot obsoleto si dos conexiones intentan
        # borrar la misma fila a la vez.
        conn.execute("BEGIN IMMEDIATE")
        fila = conn.execute("SELECT deleted_at, monto FROM ingresos WHERE id = ?", (income_id,)).fetchone()
        if fila is None:
            conn.rollback()
            return self._error(start_response, 404, f"no existe ingreso id={income_id}.")
        if fila["deleted_at"] is not None:
            conn.rollback()
            return self._error(start_response, 404, f"no existe ingreso id={income_id}.")
        if not _valid_money(fila["monto"]):
            conn.rollback()
            return self._error(start_response, 422, "datos almacenados inválidos.")
        try:
            db.eliminar_ingreso_logico(conn, income_id, SERVER_ACTOR)
        except ValueError:
            return self._error(start_response, 409, "no se pudo borrar el ingreso.")
        return self._json(start_response, 200, {"deleted": True, "id": income_id})

    # --- fixed ----------------------------------------------------------

    def list_fixed(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), {"dateISO"})
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        date_iso = ctx.query_param("dateISO")
        if date_iso is not None and not _is_iso_date(date_iso):
            return self._error(start_response, 400, "dateISO debe ser 'YYYY-MM-DD' válida.")
        vigentes = db.get_fijos_vigentes(conn, fecha=date_iso)
        for version in vigentes:
            _stored_money(version["monto_estimado"])
        resultado = [{**v, "monto_mensual": db.monto_mensual(v)} for v in vigentes]
        return self._json(start_response, 200, {"fixed": resultado})

    def list_fixed_versions(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), set())
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        todas = db.get_gastos_fijos(conn, solo_activos=False)
        for version in todas:
            _stored_money(version["monto_estimado"])
        resultado = [{**v, "monto_mensual": db.monto_mensual(v)} for v in todas]
        return self._json(start_response, 200, {"versions": resultado})

    def fixed_range(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), {"fromISO", "toISO"})
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        from_iso = ctx.query_param("fromISO")
        to_iso = ctx.query_param("toISO")
        if from_iso is None or to_iso is None:
            return self._error(start_response, 400, "fromISO y toISO son obligatorios.")
        if not _is_iso_date(from_iso) or not _is_iso_date(to_iso):
            return self._error(start_response, 400, "fromISO y toISO deben ser fechas 'YYYY-MM-DD' válidas.")
        for version in db.get_gastos_fijos(conn, solo_activos=False):
            _stored_money(version["monto_estimado"])
        try:
            resultado = db.fijos_por_rango(conn, from_iso, to_iso)
        except ValueError as exc:
            return self._error(start_response, 400, str(exc))
        return self._json(start_response, 200, {"range": resultado})

    def fixed_historial(self, ctx, conn, start_response):
        version_id = int(ctx.path_params["id"])
        todas = db.get_gastos_fijos(conn, solo_activos=False)
        fila = next((row for row in todas if row["id"] == version_id), None)
        if fila is None:
            return self._error(start_response, 404, f"no existe versión de gasto fijo id={version_id}.")
        grupo = fila["fijo_grupo_id"] or fila["id"]
        for version in todas:
            if (version["fijo_grupo_id"] or version["id"]) == grupo:
                _stored_money(version["monto_estimado"])
        return self._json(start_response, 200, {"historial": db.historial_fijo(conn, grupo)})

    def create_fixed(self, ctx, conn, start_response):
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), ALLOWED_FIXED_CREATE_FIELDS)
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")

        responsable = data.get("responsable")
        if not isinstance(responsable, str) or not responsable.strip():
            return self._error(start_response, 400, "responsable es obligatorio.")
        if responsable not in validaciones.PAGADO_POR_VALIDOS:
            return self._error(start_response, 400, "responsable inválido.")

        errores = validaciones.validar_gasto_fijo(data)
        if errores:
            return self._error(start_response, 400, "payload de gasto fijo inválido.")
        if not _valid_money(data.get("monto_estimado")):
            return self._error(start_response, 400, "monto_estimado fuera de rango o con más de dos decimales.")
        try:
            db.resolve_fixed_split(
                responsable, data.get("tipo_proporcion", db._FIXED_UNSET),
                data.get("proporcion_jd", db._FIXED_UNSET),
            )
        except db.FixedSplitError:
            return self._error(start_response, 400, "reparto de gasto fijo inválido.")

        try:
            nuevo_id = db.insert_gasto_fijo(conn, dict(data), actor=SERVER_ACTOR)
        except OverflowError:
            return self._error(start_response, 400, "monto fuera de rango.")
        except ValueError:
            return self._error(start_response, 409, "no se pudo crear el gasto fijo.")

        creado = next(row for row in db.get_gastos_fijos(conn, solo_activos=False) if row["id"] == nuevo_id)
        creado = {**creado, "monto_mensual": db.monto_mensual(creado)}
        return self._json(start_response, 201, {"fixed": creado})

    def update_fixed(self, ctx, conn, start_response):
        fijo_id = int(ctx.path_params["id"])
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), ALLOWED_FIXED_PATCH_FIELDS)
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")
        if not data:
            return self._error(start_response, 400, "se requiere al menos un campo para editar.")

        vigente_desde = data.get("vigente_desde")
        if vigente_desde is None:
            return self._error(start_response, 400, "vigente_desde es obligatorio para crear una nueva versión.")
        if not _is_iso_date(vigente_desde):
            return self._error(start_response, 400, "vigente_desde debe ser 'YYYY-MM-DD' válida.")

        periodicidad = data.get("periodicidad")
        if periodicidad is not None and periodicidad not in ("mensual", "bimestral"):
            return self._error(start_response, 400, "periodicidad debe ser mensual o bimestral.")

        responsable = data.get("responsable")
        if "responsable" in data and responsable not in validaciones.PAGADO_POR_VALIDOS:
            return self._error(start_response, 400, "responsable inválido.")

        nombre = data.get("nombre")
        if nombre is not None and (not isinstance(nombre, str) or not nombre.strip()):
            return self._error(start_response, 400, "nombre, si se especifica, no puede estar vacío.")

        monto_estimado = data.get("monto_estimado")
        if monto_estimado is not None:
            errores = validaciones.validar_fixed_update({"monto_estimado": monto_estimado})
            if errores:
                return self._error(start_response, 400, "monto_estimado inválido.")

        todas = db.get_gastos_fijos(conn, solo_activos=False)
        fila = next((row for row in todas if row["id"] == fijo_id), None)
        if fila is None:
            return self._error(start_response, 404, f"no existe gasto fijo id={fijo_id}.")
        grupo = fila["fijo_grupo_id"] or fijo_id
        anterior = db._version_vigente_en(conn, grupo, vigente_desde)
        if anterior is not None and not _valid_money(monto_estimado if monto_estimado is not None else anterior["monto_estimado"]):
            return self._error(start_response, 400, "monto_estimado fuera de rango o con más de dos decimales.")
        if anterior is not None:
            json.dumps(anterior, allow_nan=False)
            nuevo_responsable = responsable if responsable is not None else anterior["responsable"]
            if nuevo_responsable not in validaciones.PAGADO_POR_VALIDOS:
                return self._error(start_response, 400, "responsable válido es obligatorio al editar.")
            try:
                db.resolve_fixed_split(
                    nuevo_responsable, data.get("tipo_proporcion", db._FIXED_UNSET),
                    data.get("proporcion_jd", db._FIXED_UNSET), anterior,
                )
            except db.FixedSplitError:
                return self._error(start_response, 400, "reparto de gasto fijo inválido.")

        try:
            nuevo_id = db.crear_version_fijo(
                conn, fijo_id,
                monto_nuevo=monto_estimado,
                vigente_desde=vigente_desde,
                responsable=responsable,
                nombre=nombre,
                periodicidad=periodicidad,
                actor=SERVER_ACTOR,
                **{key: data[key] for key in ("tipo_proporcion", "proporcion_jd") if key in data},
            )
        except db.FixedNoChangeError:
            return self._error(start_response, 400, "la edición no tiene cambios reales.")
        except db.FixedSplitError:
            return self._error(start_response, 400, "reparto de gasto fijo inválido.")
        except OverflowError:
            return self._error(start_response, 400, "monto fuera de rango.")
        except ValueError:
            return self._error(start_response, 409, "no se pudo crear la versión.")

        nueva = next(row for row in db.get_gastos_fijos(conn, solo_activos=False) if row["id"] == nuevo_id)
        nueva = {**nueva, "monto_mensual": db.monto_mensual(nueva)}
        return self._json(start_response, 200, {"fixed": nueva})

    def delete_fixed(self, ctx, conn, start_response):
        fijo_id = int(ctx.path_params["id"])
        data, err = self._parse_json(ctx, start_response)
        if err is not None:
            return err
        unknown = self._unknown_fields(data.keys(), {"fecha_baja"})
        if unknown:
            return self._error(start_response, 400, "campos desconocidos.")
        fecha_baja = data.get("fecha_baja")
        if not _is_iso_date(fecha_baja):
            return self._error(start_response, 400, "fecha_baja es obligatoria y debe ser 'YYYY-MM-DD' válida.")

        todas = db.get_gastos_fijos(conn, solo_activos=False)
        fila = next((row for row in todas if row["id"] == fijo_id), None)
        if fila is None:
            return self._error(start_response, 404, f"no existe gasto fijo id={fijo_id}.")
        grupo = fila["fijo_grupo_id"] or fijo_id
        anterior = db._version_vigente_en(conn, grupo, fecha_baja)
        if anterior is not None and not _valid_money(anterior["monto_estimado"]):
            return self._error(start_response, 422, "datos almacenados inválidos.")
        if anterior is not None:
            json.dumps(anterior, allow_nan=False)

        try:
            nuevo_id = db.dar_baja_fijo(conn, fijo_id, fecha_baja, SERVER_ACTOR)
        except ValueError:
            return self._error(start_response, 409, "no se pudo dar de baja la serie.")

        baja = next(row for row in db.get_gastos_fijos(conn, solo_activos=False) if row["id"] == nuevo_id)
        baja = {**baja, "monto_mensual": db.monto_mensual(baja)}
        return self._json(start_response, 200, {"fixed": baja})

    # --- summary ----------------------------------------------------------

    def summary(self, ctx, conn, start_response):
        unknown = self._unknown_fields(ctx.query.keys(), {"month"})
        if unknown:
            return self._error(start_response, 400, "parámetros de query desconocidos.")
        month = ctx.query_param("month")
        if month is not None and not _is_iso_month(month):
            return self._error(start_response, 400, "month debe ser 'YYYY-MM' válido.")

        if month is not None:
            return self._json(start_response, 200, self._build_month_summary(conn, month))

        meses = self._meses_presentes(conn)
        resumenes = [self._build_month_summary(conn, mes) for mes in meses]
        return self._json(start_response, 200, {"months": resumenes})

    @staticmethod
    def _meses_presentes(conn):
        gastos = db.get_gastos(conn)
        ingresos = db.get_ingresos(conn)
        meses = {row["fecha"][:7] for row in gastos if row.get("fecha")}
        meses |= {row["fecha"][:7] for row in ingresos if row.get("fecha")}
        return sorted(meses)

    @staticmethod
    def _build_month_summary(conn, month):
        gastos = db.get_gastos(conn)
        ingresos = db.get_ingresos(conn)
        fijos = db.get_gastos_fijos(conn, solo_activos=False)
        # Las funciones de deuda y proporción del dominio acumulan floats/SQL
        # REAL. Verificar todo el ledger que pueden recorrer antes de llamarlas.
        _bounded_sum(_stored_money(row["monto"]) for row in gastos)
        _bounded_sum(_stored_money(row["monto"]) for row in ingresos)
        if any(row["categoria"] == "Salario" and row["persona"] not in validaciones.PERSONA_INGRESO_VALIDOS for row in ingresos):
            raise ValueError("persona de salario almacenada inválida")
        for row in fijos:
            _stored_money(row["monto_estimado"])
        for row in gastos:
            if row["tipo_proporcion"] == "custom":
                jd, pinki = row["proporcion_jd"], row["proporcion_pinki"]
                if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100 for v in (jd, pinki))
                        or abs(jd + pinki - 100) > validaciones.TOLERANCIA_PROPORCION):
                    raise ValueError("proporción almacenada inválida")
        gastos_mes = [row for row in gastos if (row.get("fecha") or "")[:7] == month]
        ingresos_mes = [row for row in ingresos if (row.get("fecha") or "")[:7] == month]
        fijos_vigentes = db.get_fijos_vigentes(conn, fecha=db._ultimo_dia_mes(month))
        total_gastos = _bounded_sum(_stored_money(row["monto"]) for row in gastos_mes)
        total_ingresos = _bounded_sum(_stored_money(row["monto"]) for row in ingresos_mes)
        total_fijos = _bounded_sum(Decimal(str(db.monto_mensual(f))) for f in fijos_vigentes)
        return {
            "month": month,
            "expenses_total": float(total_gastos),
            "income_total": float(total_ingresos),
            "fixed_total_mensual": float(total_fijos),
            "proportion": db.calcular_proporcion_mes(conn, month),
            "debt_month": db.calcular_deudas_mes(conn, month),
            "debt_pending_through_month": db.calcular_deudas_pendientes(conn, hasta_mes=month),
            "debt_status": db.calcular_estado_saldado_mes(conn, month),
        }


def create_app(db_path, internal_secret):
    """Fábrica única de la app. Falla cerrado si falta cualquiera de los dos
    parámetros explícitos — nunca usa `db.DEFAULT_DB_PATH` ni un secreto
    implícito."""
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path es obligatorio y debe ser un string no vacío (sin default).")
    if not isinstance(internal_secret, str) or not internal_secret.strip():
        raise ValueError("internal_secret es obligatorio y debe ser un string no vacío (sin default).")
    return _App(db_path, internal_secret)


def _parse_cli_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Servidor HTTP local (solo 127.0.0.1) de la API candidata LIFE. "
            "Sin despliegue, sin escucha pública, sin defaults de datos reales."
        ),
    )
    parser.add_argument("--port", type=int, required=True, help="Puerto explícito en 127.0.0.1.")
    parser.add_argument(
        "--db-path", required=True,
        help="Ruta explícita al archivo SQLite, o ':memory:' para una base efímera de un solo proceso.",
    )
    secret_group = parser.add_mutually_exclusive_group(required=True)
    secret_group.add_argument(
        "--secret",
        help="Valor explícito del secreto interno. Queda visible en la lista de procesos; preferir --secret-file.",
    )
    secret_group.add_argument(
        "--secret-file",
        help="Ruta a un archivo cuyo contenido (sin salto de línea final) es el secreto interno.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_cli_args(sys.argv[1:] if argv is None else argv)
    if args.secret_file:
        with open(args.secret_file, "r", encoding="utf-8") as fh:
            secret = fh.read().strip()
    else:
        secret = args.secret

    app = create_app(args.db_path, secret)
    httpd = make_server(HOST, args.port, app)
    print(f"API candidata LIFE escuchando en http://{HOST}:{args.port} (solo localhost).", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
