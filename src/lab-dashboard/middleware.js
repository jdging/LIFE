// Vercel Routing Middleware — password gate for the static dashboard.
// The runtime is selected by Vercel; this file does not declare one.
// Continuing to a static asset uses next() from @vercel/functions.
//
// Behavior:
// - Every request is intercepted before any static file (index.html, app.js,
//   style.css, data/*.json) is served.
// - A valid `dashboard_session` cookie lets the request continue unchanged.
// - Anything else is redirected to /login, EXCEPT requests under /api/,
//   which get a JSON 401 `{"error":"unauthorized"}` instead (no HTML
//   redirect makes sense for a JSON API consumed via fetch()).
// - POST /login verifies the submitted password against DASHBOARD_PASSWORD
//   (an env var configured in the Vercel dashboard, see README.md) and, if
//   correct, sets a signed, long-lived session cookie ("remember me").

const COOKIE_NAME = 'dashboard_session';
const SESSION_DAYS = 90;
const SESSION_MAX_AGE_SECONDS = SESSION_DAYS * 24 * 60 * 60;

// PWA manifest + íconos (S5, t_a60a2f67): Safari necesita poder leerlos para
// el prompt de "Agregar a inicio" ANTES de que haya una sesión — nunca llevan
// datos propios, así que quedan fuera del gate. Rutas EXACTAS únicamente: no
// es un prefijo ni cubre el resto de /icons/.
const PUBLIC_STATIC_PATHS = new Set([
  '/manifest.webmanifest',
  '/icons/icon-180.png',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
]);

// Atajos de iPhone (S5, t_a60a2f67): únicos destinos "post-login" admitidos
// para no abrir un open redirect vía ?next=. Debe reflejar los valores que
// consumeAccionDeepLink() entiende en app.js.
const DEEP_LINK_ACCIONES = new Set(['gasto', 'ingreso', 'fijo', 'fijos']);

// Sólo "/" con exactamente ?accion=<conocida> cuenta como destino preservable.
// Cualquier otra cosa (otro path, parámetros extra, un valor desconocido) cae
// al default "/" — nunca se redirige a un valor arbitrario del cliente.
function sanitizeNextTarget(pathname, search) {
  if (pathname !== '/') return null;
  const params = new URLSearchParams(search);
  if ([...params.keys()].length !== 1) return null;
  const accion = params.get('accion');
  if (!accion || !DEEP_LINK_ACCIONES.has(accion)) return null;
  return `/?accion=${encodeURIComponent(accion)}`;
}

// Revalida un `next` recibido por query (en la propia URL del POST /login,
// nunca por header ni body) contra el mismo formato exacto que produce
// sanitizeNextTarget, antes de usarlo como Location de la redirección.
function isAllowedNextTarget(value) {
  if (typeof value !== 'string') return false;
  const match = /^\/\?accion=([a-z]+)$/.exec(value);
  return !!match && DEEP_LINK_ACCIONES.has(match[1]);
}

async function sha256Hex(message) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(message));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmacSha256Hex(secret, message) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// Fixed-length digest comparison avoids leaking string length / early-exit timing.
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

function getCookie(request, name) {
  const header = request.headers.get('cookie') || '';
  const match = header.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

// Session token = "<expiryMs>.<hmac(expiryMs)>". Unguessable without the
// secret (DASHBOARD_PASSWORD) and self-expiring, without needing a session
// store — appropriate for a personal, two-user dashboard.
async function createSessionCookieValue(secret) {
  const expiresAt = Date.now() + SESSION_MAX_AGE_SECONDS * 1000;
  const signature = await hmacSha256Hex(secret, String(expiresAt));
  return `${expiresAt}.${signature}`;
}

async function isValidSessionCookie(value, secret) {
  if (!value) return false;
  const [expiresAtStr, signature] = value.split('.');
  if (!expiresAtStr || !signature) return false;

  const expiresAt = Number(expiresAtStr);
  if (!Number.isFinite(expiresAt) || expiresAt < Date.now()) return false;

  const expectedSignature = await hmacSha256Hex(secret, expiresAtStr);
  return timingSafeEqual(expectedSignature, signature);
}

// ---------------------------------------------------------------------------
// VPS API proxy — only reachable for /api/*
// paths, after the dashboard_session check in the main handler below. See
// README-proxy.md for the full design. Dormant by design until an operator
// sets VPS_API_BASE_URL and VPS_INTERNAL_SECRET in Vercel: both missing or
// invalid fail closed with a 503, never with a silent pass-through.

const PROXY_REQUEST_BODY_LIMIT_BYTES = 64 * 1024; // 64 KiB
const PROXY_UPSTREAM_RESPONSE_LIMIT_BYTES = 1 * 1024 * 1024; // 1 MiB safety cap
const PROXY_UPSTREAM_TIMEOUT_MS_DEFAULT = 10_000;
const PROXY_UPSTREAM_TIMEOUT_MS_MAX = 60_000;

const PROXY_ROUTES = [
  { pattern: /^\/api\/health$/, methods: ['GET'], query: {} },
  { pattern: /^\/api\/expenses$/, methods: ['GET', 'POST'], query: { GET: { month: 'month' } } },
  { pattern: /^\/api\/expenses\/[1-9]\d*$/, methods: ['DELETE'], query: {} },
  { pattern: /^\/api\/income$/, methods: ['GET', 'POST'], query: {} },
  { pattern: /^\/api\/income\/[1-9]\d*$/, methods: ['PATCH', 'DELETE'], query: {} },
  { pattern: /^\/api\/inventory$/, methods: ['GET', 'POST'], query: {} },
  { pattern: /^\/api\/inventory\/[1-9]\d*$/, methods: ['PATCH', 'DELETE'], query: {} },
  { pattern: /^\/api\/fixed$/, methods: ['GET', 'POST'], query: { GET: { dateISO: 'date' } } },
  { pattern: /^\/api\/fixed\/versions$/, methods: ['GET'], query: {} },
  { pattern: /^\/api\/fixed\/range$/, methods: ['GET'], query: { GET: { fromISO: 'date', toISO: 'date' } }, requiredQuery: ['fromISO', 'toISO'] },
  { pattern: /^\/api\/fixed\/[1-9]\d*\/historial$/, methods: ['GET'], query: {} },
  { pattern: /^\/api\/fixed\/[1-9]\d*$/, methods: ['PATCH', 'DELETE'], query: {} },
  { pattern: /^\/api\/summary$/, methods: ['GET'], query: { GET: { month: 'month' } } },
  { pattern: /^\/api\/categories$/, methods: ['GET'], query: { GET: { tipo: 'tipo' } } },
];

const PROXY_SAFE_UPSTREAM_STATUSES = new Set([
  200, 201, 202, 400, 401, 403, 404, 405, 409, 410, 413, 415, 422, 429,
]);

function jsonResponse(status, data, extraHeaders) {
  const headers = new Headers({
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  });
  if (extraHeaders) {
    for (const [key, value] of Object.entries(extraHeaders)) headers.set(key, value);
  }
  return new Response(JSON.stringify(data), { status, headers });
}

function getUpstreamTimeoutMs() {
  const raw = Number(process.env.VPS_PROXY_TIMEOUT_MS);
  if (Number.isFinite(raw) && raw > 0 && raw <= PROXY_UPSTREAM_TIMEOUT_MS_MAX) return raw;
  return PROXY_UPSTREAM_TIMEOUT_MS_DEFAULT;
}

function isValidMonth(value) {
  return /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(value);
}

function isValidDate(value) {
  if (!/^(?!0000)\d{4}-(0[1-9]|1[0-2])-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

const CATEGORY_TIPOS = new Set(['Gasto', 'Ingreso', 'Inversión']);

function isValidTipo(value) {
  return CATEGORY_TIPOS.has(value);
}

function isValidProxyQuery(search, route, method) {
  try {
    decodeURIComponent(search);
  } catch {
    return false;
  }
  const allowed = route.query[method] || {};
  const seen = new Set();
  for (const [key, value] of new URLSearchParams(search)) {
    if (seen.has(key) || !Object.hasOwn(allowed, key)) return false;
    if (allowed[key] === 'month' && !isValidMonth(value)) return false;
    if (allowed[key] === 'date' && !isValidDate(value)) return false;
    if (allowed[key] === 'tipo' && !isValidTipo(value)) return false;
    seen.add(key);
  }
  return (route.requiredQuery || []).every((key) => seen.has(key));
}

// Require a DNS hostname: URL normalizes numeric host aliases (such as
// 2130706433) into IP literals, which this check also rejects. DNS resolution
// must still be restricted by the operator's network policy.
function parseUpstreamBaseUrl(raw) {
  if (typeof raw !== 'string' || raw !== raw.trim() || !/^https:\/\//i.test(raw) || raw.includes('\\')) {
    return null;
  }
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:') return null;
  if (parsed.username || parsed.password) return null;
  if (parsed.search || parsed.hash) return null;
  const hostname = parsed.hostname.toLowerCase().replace(/\.+$/, '');
  if (!hostname || !hostname.includes('.') || hostname.startsWith('[')) return null;
  if (/^\d+(?:\.\d+){3}$/.test(hostname)) return null;
  if (hostname === 'localhost' || hostname.endsWith('.localhost')) return null;
  if (hostname === 'metadata.google.internal' || hostname.endsWith('.internal')) return null;
  if (hostname.endsWith('.local')) return null;
  return parsed;
}

function matchProxyRoute(pathname) {
  for (const route of PROXY_ROUTES) {
    if (route.pattern.test(pathname)) return route;
  }
  return null;
}

// Appends the whitelisted dashboard path to whatever path prefix (if any)
// the operator configured in VPS_API_BASE_URL, instead of letting standard
// URL resolution silently drop that prefix (new URL('/x', 'https://h/base')
// discards '/base' because '/x' is an absolute-path reference).
function buildUpstreamUrl(baseUrl, pathname, search) {
  let prefix = baseUrl.pathname;
  if (prefix === '/') prefix = '';
  else if (prefix.endsWith('/')) prefix = prefix.slice(0, -1);
  const target = new URL(`${baseUrl.origin}${prefix}${pathname}`);
  target.search = search;
  if (target.hostname !== baseUrl.hostname || target.protocol !== 'https:') return null;
  return target;
}

function isExactOriginMatch(originHeader, url) {
  if (!originHeader) return false;
  return originHeader === url.origin;
}

function isJsonContentType(contentType) {
  return (
    typeof contentType === 'string' &&
    contentType.toLowerCase().split(';')[0].trim() === 'application/json'
  );
}

// Reads the request body without ever buffering more than `limitBytes`,
// regardless of what Content-Length claims — a spoofed or absent header
// must not bypass the cap.
function awaitWithAbort(promise, signal) {
  if (signal.aborted) return Promise.reject(new DOMException('Timed out', 'AbortError'));
  return new Promise((resolve, reject) => {
    const abort = () => {
      signal.removeEventListener('abort', abort);
      reject(new DOMException('Timed out', 'AbortError'));
    };
    signal.addEventListener('abort', abort, { once: true });
    Promise.resolve(promise).then(
      (value) => { signal.removeEventListener('abort', abort); resolve(value); },
      (error) => { signal.removeEventListener('abort', abort); reject(error); }
    );
  });
}

// Cancellation is best effort: some streams reject or never settle their
// cancel promise. Never wait for it after the request deadline has ended.
function cancelReadableBody(body) {
  if (!body) return;
  try {
    void Promise.resolve(body.cancel()).catch(() => {});
  } catch {
    // A locked or already closed body may reject cancellation synchronously.
  }
}

async function readLimitedStream(body, limitBytes, tooLargeErrorCode, signal) {
  if (!body) return new Uint8Array(0);
  const reader = body.getReader();
  const chunks = [];
  let total = 0;
  let complete = false;
  let cancellationStarted = false;
  const cancel = () => {
    if (cancellationStarted) return;
    cancellationStarted = true;
    try {
      void Promise.resolve(reader.cancel()).catch(() => {});
    } catch {
      // Cancellation must not replace the original read error or timeout.
    }
  };
  signal.addEventListener('abort', cancel, { once: true });
  try {
    for (;;) {
      const { done, value } = await awaitWithAbort(reader.read(), signal);
      if (done) {
        complete = true;
        break;
      }
      total += value.byteLength;
      if (total > limitBytes) {
        const error = new Error(tooLargeErrorCode);
        error.code = tooLargeErrorCode;
        throw error;
      }
      chunks.push(value);
    }
  } finally {
    signal.removeEventListener('abort', cancel);
    if (!complete) cancel();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function containsSensitiveJsonValue(parsedBody, sensitiveValues) {
  const pending = [parsedBody];
  while (pending.length) {
    const value = pending.pop();
    if (typeof value === 'string') {
      if (sensitiveValues.some((sensitive) => value.includes(sensitive))) return true;
    } else if (Array.isArray(value)) {
      for (const child of value) pending.push(child);
    } else if (value !== null && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        if (sensitiveValues.some((sensitive) => key.includes(sensitive))) return true;
        pending.push(child);
      }
    }
  }
  return false;
}

async function handleApiProxy(request, url, pathname) {
  const baseUrlRaw = process.env.VPS_API_BASE_URL;
  const vpsSecret = process.env.VPS_INTERNAL_SECRET;

  // Fail closed: both env vars are required and are never echoed back to
  // the client or logged, success or failure.
  if (!baseUrlRaw || !vpsSecret || !vpsSecret.trim()) {
    return jsonResponse(503, { error: 'upstream_not_configured' });
  }

  const baseUrl = parseUpstreamBaseUrl(baseUrlRaw);
  if (!baseUrl) {
    return jsonResponse(503, { error: 'upstream_not_configured' });
  }

  const route = matchProxyRoute(pathname);
  if (!route) {
    return jsonResponse(404, { error: 'not_found' });
  }
  if (!route.methods.includes(request.method)) {
    return jsonResponse(405, { error: 'method_not_allowed' }, { Allow: route.methods.join(', ') });
  }

  if (!isValidProxyQuery(url.search, route, request.method)) {
    return jsonResponse(400, { error: 'invalid_query' });
  }

  const isWrite = request.method === 'POST' || request.method === 'PATCH' || request.method === 'DELETE';
  const origin = request.headers.get('origin');
  if (origin && !isExactOriginMatch(origin, url)) {
    return jsonResponse(403, { error: 'origin_rejected' });
  }
  if (isWrite) {
    // Exact match only. Referer is never accepted as a substitute (it is
    // easier to omit/forge and doesn't carry the same browser guarantees),
    // and there is no cross-host allowlist — the request must be
    // same-origin with itself.
    if (!origin) {
      return jsonResponse(403, { error: 'origin_rejected' });
    }
  }

  // Allowlist only: Content-Type (validated after reading the body) and
  // X-Internal-Proxy-Secret (server-side, from env). Everything else from
  // the inbound request — Authorization, Cookie, any
  // X-Internal-Proxy-Secret / actor / trust header the client may have
  // sent — is never read and never forwarded. The upstream actor identity
  // is a fixed, unverified constant on the VPS side; the shared
  // dashboard_session cookie never becomes a per-user identity for it.
  const outboundHeaders = new Headers();
  try {
    outboundHeaders.set('x-internal-proxy-secret', vpsSecret);
    if (outboundHeaders.get('x-internal-proxy-secret') !== vpsSecret) {
      return jsonResponse(503, { error: 'upstream_not_configured' });
    }
  } catch {
    return jsonResponse(503, { error: 'upstream_not_configured' });
  }

  const targetUrl = buildUpstreamUrl(baseUrl, pathname, url.search);
  if (!targetUrl) return jsonResponse(503, { error: 'upstream_not_configured' });

  const controller = new AbortController();
  const timeoutMs = getUpstreamTimeoutMs();
  const deadline = Date.now() + timeoutMs;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  let upstreamResponse;
  let upstreamBodyComplete = false;

  try {
    let bodyBytes;
    try {
      bodyBytes = await readLimitedStream(request.body, PROXY_REQUEST_BODY_LIMIT_BYTES, 'REQUEST_BODY_TOO_LARGE', controller.signal);
    } catch (error) {
      if (controller.signal.aborted || (error && error.name === 'AbortError')) throw error;
      if (error && error.code === 'REQUEST_BODY_TOO_LARGE') {
        return jsonResponse(413, { error: 'request_body_too_large' });
      }
      return jsonResponse(400, { error: 'invalid_request_body' });
    }

    if (bodyBytes.byteLength > 0 && !isJsonContentType(request.headers.get('content-type'))) {
      return jsonResponse(400, { error: 'unsupported_content_type' });
    }
    if (bodyBytes.byteLength > 0) {
      try {
        JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bodyBytes));
      } catch {
        return jsonResponse(400, { error: 'invalid_json_body' });
      }
      outboundHeaders.set('content-type', 'application/json');
    }

    if (controller.signal.aborted || Date.now() >= deadline) {
      return jsonResponse(504, { error: 'upstream_timeout' });
    }

    upstreamResponse = await awaitWithAbort(
      Promise.resolve(fetch(targetUrl.toString(), {
        method: request.method,
        headers: outboundHeaders,
        body: bodyBytes.byteLength > 0 ? bodyBytes : undefined,
        redirect: 'manual', // a redirect from the VPS is an error, never followed
        signal: controller.signal,
      })).then((response) => {
        // A fetch implementation can ignore abort and deliver headers later.
        if (controller.signal.aborted) cancelReadableBody(response.body);
        return response;
      }),
      controller.signal
    );

    if (controller.signal.aborted) {
      return jsonResponse(504, { error: 'upstream_timeout' });
    }

    if (
      upstreamResponse.type === 'opaqueredirect' ||
      (upstreamResponse.status >= 300 && upstreamResponse.status < 400)
    ) {
      return jsonResponse(502, { error: 'upstream_redirect_blocked' });
    }

    if (upstreamResponse.status === 204) {
      // No body by definition; never forward upstream headers (in
      // particular, the VPS must not be able to set cookies on this origin).
      return new Response(null, { status: 204, headers: new Headers({ 'cache-control': 'no-store' }) });
    }

    if (!PROXY_SAFE_UPSTREAM_STATUSES.has(upstreamResponse.status)) {
      return jsonResponse(502, { error: 'upstream_error' });
    }

    if (!isJsonContentType(upstreamResponse.headers.get('content-type'))) {
      return jsonResponse(502, { error: 'upstream_invalid_response' });
    }

    const upstreamBytes = await readLimitedStream(
      upstreamResponse.body,
      PROXY_UPSTREAM_RESPONSE_LIMIT_BYTES,
      'UPSTREAM_RESPONSE_TOO_LARGE',
      controller.signal
    );
    upstreamBodyComplete = true;

    const upstreamText = new TextDecoder('utf-8', { fatal: true }).decode(upstreamBytes);
    const parsedBody = JSON.parse(upstreamText);
    if (controller.signal.aborted || Date.now() >= deadline) {
      return jsonResponse(504, { error: 'upstream_timeout' });
    }
    if (containsSensitiveJsonValue(parsedBody, [vpsSecret, baseUrlRaw, baseUrl.origin])) {
      return jsonResponse(502, { error: 'upstream_invalid_response' });
    }
    if (controller.signal.aborted || Date.now() >= deadline) {
      return jsonResponse(504, { error: 'upstream_timeout' });
    }

    // Never forward upstream response headers verbatim: jsonResponse() builds
    // a fresh header set, so any Set-Cookie (or anything else) from the VPS
    // is dropped here.
    return jsonResponse(upstreamResponse.status, parsedBody);
  } catch (error) {
    if (controller.signal.aborted || Date.now() >= deadline || (error && error.name === 'AbortError')) {
      return jsonResponse(504, { error: 'upstream_timeout' });
    }
    return jsonResponse(502, { error: 'upstream_unavailable' });
  } finally {
    if (upstreamResponse && !upstreamBodyComplete) cancelReadableBody(upstreamResponse.body);
    clearTimeout(timeoutId);
  }
}

export const config = {
  matcher: '/:path*',
};

async function continueToStaticAsset() {
  const { next } = await import('@vercel/functions');
  return next();
}

// Tests inject a continuation to check the gate without requiring the Vercel
// SDK in this candidate. Production uses the SDK's documented next().
export async function handleMiddleware(request, continueRequest) {
  const url = new URL(request.url);
  const { pathname } = url;

  if (request.method === 'GET' && PUBLIC_STATIC_PATHS.has(pathname)) {
    return continueRequest();
  }

  const secret = process.env.DASHBOARD_PASSWORD;

  if (!secret) {
    return new Response(
      'Falta configurar la variable de entorno DASHBOARD_PASSWORD en Vercel ' +
        '(Settings → Environment Variables). Ver README.md.',
      { status: 500, headers: { 'content-type': 'text/plain; charset=utf-8' } }
    );
  }

  const isLoginPath = pathname === '/login' || pathname === '/login.html';

  if (request.method === 'POST' && pathname === '/login') {
    const form = await request.formData();
    const submittedPassword = String(form.get('password') || '');

    const passwordOk = timingSafeEqual(
      await sha256Hex(submittedPassword),
      await sha256Hex(secret)
    );

    // El `next` sólo viaja en la URL del propio POST /login (nunca en el body:
    // el form action lo reenvía ahí desde login.html), y se revalida acá de
    // nuevo contra el allowlist antes de usarlo como destino.
    const requestedNext = url.searchParams.get('next');
    const nextTarget = isAllowedNextTarget(requestedNext) ? requestedNext : null;

    if (!passwordOk) {
      const failedLoginUrl = new URL('/login', url);
      failedLoginUrl.searchParams.set('error', '1');
      if (nextTarget) failedLoginUrl.searchParams.set('next', nextTarget);
      return Response.redirect(failedLoginUrl, 303);
    }

    const cookieValue = await createSessionCookieValue(secret);
    // Response.redirect(...) devuelve headers inmutables en el runtime de Vercel
    // (TypeError: immutable al intentar .append()) -- hay que construir la
    // respuesta a mano con un Headers propio (mutable) desde el arranque.
    const headers = new Headers({ Location: new URL(nextTarget || '/', url).toString() });
    headers.append(
      'Set-Cookie',
      `${COOKIE_NAME}=${cookieValue}; Path=/; Max-Age=${SESSION_MAX_AGE_SECONDS}; ` +
        'HttpOnly; Secure; SameSite=Lax'
    );
    return new Response(null, { status: 303, headers });
  }

  if (isLoginPath) {
    // Already logged in and browsing to /login on purpose: send them home.
    if (request.method === 'GET') {
      const existingCookie = getCookie(request, COOKIE_NAME);
      if (await isValidSessionCookie(existingCookie, secret)) {
        return Response.redirect(new URL('/', url), 303);
      }
    }
    return continueRequest(); // let Vercel serve the static login.html
  }

  if (pathname === '/logout' && (request.method === 'GET' || request.method === 'POST')) {
    const headers = new Headers({ Location: new URL('/login', url).toString() });
    headers.set('Set-Cookie', `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`);
    headers.set('Cache-Control', 'no-store');
    return new Response(null, { status: 303, headers });
  }

  const cookieValue = getCookie(request, COOKIE_NAME);
  const sessionValid = await isValidSessionCookie(cookieValue, secret);

  // API routes never redirect to /login (there's no browser navigation to
  // redirect): missing/expired session means a JSON 401 so fetch() callers
  // can handle it programmatically instead of following an HTML redirect.
  if (pathname === '/api' || pathname.startsWith('/api/')) {
    if (!sessionValid) {
      return jsonResponse(401, { error: 'unauthorized' });
    }
    return handleApiProxy(request, url, pathname);
  }

  if (!sessionValid) {
    const next = sanitizeNextTarget(pathname, url.search);
    const loginUrl = new URL('/login', url);
    if (next) loginUrl.searchParams.set('next', next);
    return Response.redirect(loginUrl, 303);
  }

  return continueRequest(); // valid session: continue to the original static asset
}

export default function middleware(request) {
  return handleMiddleware(request, continueToStaticAsset);
}
