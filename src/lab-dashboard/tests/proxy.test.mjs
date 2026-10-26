import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac, webcrypto } from 'node:crypto';
import middleware, { handleMiddleware } from '../middleware.js';

// All credentials and hostnames below are disposable. fetch is always mocked.
if (!globalThis.crypto) globalThis.crypto = webcrypto;

const DASHBOARD_PASSWORD = 'test-dashboard-password';
const INTERNAL_SECRET = 'test-internal-secret';
const BASE_URL = 'https://api.example.test/private';
const SITE_URL = 'https://life.example.test';

function sessionCookie(expiresAt = Date.now() + 60_000) {
  const expiry = String(expiresAt);
  const signature = createHmac('sha256', DASHBOARD_PASSWORD).update(expiry).digest('hex');
  return `dashboard_session=${expiry}.${signature}`;
}

function apiRequest(path = '/api/health', options = {}) {
  const headers = new Headers(options.headers);
  if (options.cookie !== null) headers.set('cookie', options.cookie || sessionCookie());
  if (options.body !== undefined && !headers.has('content-type')) headers.set('content-type', 'application/json');
  if (['POST', 'PATCH', 'DELETE'].includes(options.method) && options.origin !== null && !headers.has('origin')) {
    headers.set('origin', SITE_URL);
  }
  return new Request(`${SITE_URL}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body,
    ...(options.body instanceof ReadableStream ? { duplex: 'half' } : {}),
  });
}

function upstreamJson(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...headers },
  });
}

async function withHarness(action, options = {}) {
  const names = ['DASHBOARD_PASSWORD', 'VPS_API_BASE_URL', 'VPS_INTERNAL_SECRET', 'VPS_PROXY_TIMEOUT_MS'];
  const previous = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  const originalFetch = globalThis.fetch;
  process.env.DASHBOARD_PASSWORD = DASHBOARD_PASSWORD;
  if (options.baseUrl === null) delete process.env.VPS_API_BASE_URL;
  else process.env.VPS_API_BASE_URL = options.baseUrl ?? BASE_URL;
  if (options.internalSecret === null) delete process.env.VPS_INTERNAL_SECRET;
  else process.env.VPS_INTERNAL_SECRET = options.internalSecret ?? INTERNAL_SECRET;
  if (options.timeoutMs === undefined) delete process.env.VPS_PROXY_TIMEOUT_MS;
  else process.env.VPS_PROXY_TIMEOUT_MS = String(options.timeoutMs);
  globalThis.fetch = options.fetch || (() => Promise.resolve(upstreamJson({ ok: true })));
  try {
    await action();
  } finally {
    globalThis.fetch = originalFetch;
    for (const name of names) {
      if (previous[name] === undefined) delete process.env[name];
      else process.env[name] = previous[name];
    }
  }
}

async function settleWithin(promise) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error('proxy did not settle before watchdog')), 500);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function withTrackedProxyTimer(timeoutMs, action) {
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const active = new Set();
  globalThis.setTimeout = (callback, delay, ...args) => {
    const timer = originalSetTimeout(callback, delay, ...args);
    if (delay === timeoutMs) active.add(timer);
    return timer;
  };
  globalThis.clearTimeout = (timer) => {
    active.delete(timer);
    return originalClearTimeout(timer);
  };
  try {
    await action();
    assert.equal(active.size, 0, 'proxy deadline timer must be cleared');
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
    for (const timer of active) originalClearTimeout(timer);
  }
}

test('API rejects missing, invalid, and expired sessions without fetching', async () => {
  let calls = 0;
  await withHarness(async () => {
    for (const cookie of [null, 'dashboard_session=invalid', 'dashboard_session=%ZZ', sessionCookie(Date.now() - 1)]) {
      const response = await middleware(apiRequest('/api/health', { cookie }));
      assert.equal(response.status, 401);
      assert.deepEqual(await response.json(), { error: 'unauthorized' });
      assert.equal(response.headers.get('cache-control'), 'no-store');
    }
  }, { fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  assert.equal(calls, 0);
});

test('missing or invalid upstream configuration fails closed', async () => {
  let calls = 0;
  for (const config of [
    { baseUrl: null }, { internalSecret: null }, { internalSecret: '\r\ninvalid' },
    { internalSecret: '  ' },
  ]) {
    await withHarness(async () => {
      const response = await middleware(apiRequest('/api/health'));
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { error: 'upstream_not_configured' });
      assert.equal(response.headers.get('cache-control'), 'no-store');
    }, { ...config, fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  }
  assert.equal(calls, 0);
});

test('every contracted method forwards the exact path and query to the configured host', async () => {
  const routes = [
    ['GET', '/api/health'],
    ['GET', '/api/expenses?month=2026-10'],
    ['POST', '/api/expenses', '{}'],
    ['PATCH', '/api/expenses/1', '{}'],
    ['DELETE', '/api/expenses/1'],
    ['POST', '/api/expenses/1/saldar'],
    ['GET', '/api/income'],
    ['POST', '/api/income', '{}'],
    ['PATCH', '/api/income/2', '{}'],
    ['DELETE', '/api/income/2'],
    ['GET', '/api/inventory'],
    ['POST', '/api/inventory', '{}'],
    ['PATCH', '/api/inventory/2', '{}'],
    ['DELETE', '/api/inventory/2'],
    ['GET', '/api/fixed?dateISO=2026-10-17'],
    ['POST', '/api/fixed', '{}'],
    ['GET', '/api/fixed/versions'],
    ['GET', '/api/fixed/range?fromISO=2026-10-01&toISO=2026-10-31'],
    ['GET', '/api/fixed/3/historial'],
    ['PATCH', '/api/fixed/3', '{}'],
    ['DELETE', '/api/fixed/3', '{"fecha_baja":"2026-10-17"}'],
    ['GET', '/api/summary?month=2026-10'],
    ['GET', '/api/categories?tipo=Gasto'],
  ];
  let calls = 0;
  await withHarness(async () => {
    for (const [method, path, body] of routes) {
      const response = await middleware(apiRequest(path, { method, body }));
      assert.equal(response.status, method === 'POST' ? 201 : 200, `${method} ${path}`);
      assert.deepEqual(await response.json(), { ok: true });
    }
  }, {
    fetch: async (target, options) => {
      const [method, path, body] = routes[calls++];
      assert.equal(target, `${BASE_URL}${path}`);
      assert.equal(new URL(target).hostname, 'api.example.test');
      assert.equal(options.method, method);
      assert.equal(options.redirect, 'manual');
      assert.equal(options.headers.get('x-internal-proxy-secret'), INTERNAL_SECRET);
      assert.deepEqual([...options.headers.keys()].sort(), body === undefined
        ? ['x-internal-proxy-secret'] : ['content-type', 'x-internal-proxy-secret']);
      assert.equal(body === undefined ? options.body : new TextDecoder().decode(options.body), body);
      return upstreamJson({ ok: true }, method === 'POST' ? 201 : 200, { 'set-cookie': 'ignored=1' });
    },
  });
  assert.equal(calls, routes.length);
});

test('known paths reject wrong methods with Allow; unknown paths stay 404', async () => {
  const wrong = [
    ['/api/health', 'POST', 'GET'],
    ['/api/expenses', 'PATCH', 'GET, POST'],
    ['/api/expenses/1', 'GET', 'PATCH, DELETE'],
    ['/api/expenses/1/saldar', 'GET', 'POST'],
    ['/api/income', 'DELETE', 'GET, POST'],
    ['/api/income/1', 'GET', 'PATCH, DELETE'],
    ['/api/inventory', 'DELETE', 'GET, POST'],
    ['/api/inventory/1', 'GET', 'PATCH, DELETE'],
    ['/api/fixed', 'DELETE', 'GET, POST'],
    ['/api/fixed/versions', 'POST', 'GET'],
    ['/api/fixed/range', 'PATCH', 'GET'],
    ['/api/fixed/1/historial', 'POST', 'GET'],
    ['/api/fixed/1', 'GET', 'PATCH, DELETE'],
    ['/api/summary', 'POST', 'GET'],
    ['/api/categories', 'POST', 'GET'],
  ];
  const unknown = [
    '/api/gastos', '/api/ingresos', '/api/fijos', '/api/inventario', '/api/expenses/F-1',
    '/api/expenses/0', '/api/expenses/1/saldar/x', '/api/income/-1', '/api/inventory/0', '/api/inventory/-1',
    '/api/fixed/0/historial', '/api/fixed/1/versions', '/api/fixed/1%2Fhistorial',
    '/api/unknown', '/api',
  ];
  let calls = 0;
  await withHarness(async () => {
    for (const [path, method, allow] of wrong) {
      const response = await middleware(apiRequest(path, { method }));
      assert.equal(response.status, 405, `${method} ${path}`);
      assert.equal(response.headers.get('allow'), allow);
    }
    for (const path of unknown) {
      const response = await middleware(apiRequest(path));
      assert.equal(response.status, 404, path);
      assert.equal(response.headers.get('allow'), null);
    }
  }, { fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  assert.equal(calls, 0);
});

test('query whitelist validates names, multiplicity, dates, and method scope', async () => {
  const invalid = [
    '/api/health?month=2026-10', '/api/expenses?tag=x',
    '/api/expenses?month=2026-10&month=2026-11', '/api/expenses?month=2026-13',
    '/api/expenses?month=0000-01', '/api/income?month=2026-10',
    '/api/fixed?dateISO=2026-02-30', '/api/fixed/range?fromISO=2026-10-01',
    '/api/fixed/range?fromISO=2026-10-01&toISO=2026-10-32',
    '/api/fixed/versions?dateISO=2026-10-01', '/api/fixed/1/historial?x=1',
    '/api/summary?month=%ZZ', '/api/summary?month=2026-00',
    '/api/expenses/1?month=2026-10', '/api/inventory?month=2026-10',
    '/api/categories?tag=x', '/api/categories?tipo=Gasto&tipo=Ingreso',
    '/api/categories?tipo=Factura',
  ];
  let calls = 0;
  await withHarness(async () => {
    for (const path of invalid) {
      const method = path.startsWith('/api/expenses/1?') ? 'DELETE' : 'GET';
      const response = await middleware(apiRequest(path, { method }));
      assert.equal(response.status, 400, path);
      assert.deepEqual(await response.json(), { error: 'invalid_query' });
    }
    for (const [path, method] of [['/api/expenses?month=2026-10', 'POST'], ['/api/fixed?dateISO=2026-10-17', 'POST']]) {
      const response = await middleware(apiRequest(path, { method, body: '{}' }));
      assert.equal(response.status, 400, path);
    }
  }, { fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  assert.equal(calls, 0);
});

test('writes require exact Origin; caller credentials and identity headers are never forwarded', async () => {
  let calls = 0;
  await withHarness(async () => {
    for (const headers of [
      { origin: 'https://other.example.test' }, { referer: `${SITE_URL}/finanzas` },
      { origin: `${SITE_URL}/extra` },
    ]) {
      const response = await middleware(apiRequest('/api/expenses', {
        method: 'POST', body: '{}', origin: null, headers,
      }));
      assert.equal(response.status, 403);
    }
    const response = await middleware(apiRequest('/api/expenses', {
      method: 'POST', body: '{}', headers: {
        authorization: 'Bearer disposable-client-value',
        'x-internal-proxy-secret': 'disposable-client-value',
        'x-actor-id': 'fake-actor', 'x-forwarded-user': 'fake-user',
      },
    }));
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('set-cookie'), null);
  }, {
    fetch: async (_target, options) => {
      calls++;
      assert.deepEqual([...options.headers.keys()].sort(), ['content-type', 'x-internal-proxy-secret']);
      assert.equal(options.headers.get('x-internal-proxy-secret'), INTERNAL_SECRET);
      return upstreamJson({ ok: true }, 201, { 'set-cookie': 'ignored=1' });
    },
  });
  assert.equal(calls, 1);
});

test('redirects and non-JSON or oversized upstream bodies are rejected', async () => {
  for (const upstream of [
    new Response(null, { status: 302, headers: { location: 'https://other.example.test/' } }),
    new Response('<html>bad</html>', { headers: { 'content-type': 'text/html' } }),
    upstreamJson({ message: 'x'.repeat(1024 * 1024) }),
  ]) {
    await withHarness(async () => {
      const response = await middleware(apiRequest('/api/health'));
      assert.equal(response.status, 502);
      assert.equal(response.headers.get('set-cookie'), null);
      assert.equal(response.headers.get('location'), null);
    }, { fetch: async () => upstream });
  }
});

test('rejected upstream headers cancel open bodies and clear the deadline timer', async () => {
  const cases = [
    { name: 'redirect', status: 302, headers: { location: 'https://other.example.test/' }, error: 'upstream_redirect_blocked' },
    { name: 'unsafe status', status: 500, headers: { 'content-type': 'application/json' }, error: 'upstream_error' },
    { name: 'non-JSON', status: 200, headers: { 'content-type': 'text/html' }, error: 'upstream_invalid_response' },
  ];
  for (const { name, status, headers, error } of cases) {
    let cancellations = 0;
    const upstream = new Response(new ReadableStream({
      cancel() { cancellations++; },
    }), { status, headers });
    await withHarness(async () => {
      await withTrackedProxyTimer(1000, async () => {
        const response = await settleWithin(middleware(apiRequest('/api/health')));
        assert.equal(response.status, 502, name);
        assert.deepEqual(await response.json(), { error }, name);
      });
    }, { timeoutMs: 1000, fetch: async () => upstream });
    assert.equal(cancellations, 1, `${name} body must be cancelled`);
  }
});

test('rejected or unresolved body cancellation does not delay a 502 or leak its timer', async () => {
  for (const mode of ['reject', 'never']) {
    let cancellations = 0;
    const upstream = new Response(new ReadableStream({
      cancel() {
        cancellations++;
        if (mode === 'reject') return Promise.reject(new Error('disposable cancellation failure'));
        return new Promise(() => {});
      },
    }), { status: 302, headers: { location: 'https://other.example.test/' } });
    await withHarness(async () => {
      await withTrackedProxyTimer(1000, async () => {
        const response = await settleWithin(middleware(apiRequest('/api/health')));
        assert.equal(response.status, 502, mode);
        assert.deepEqual(await response.json(), { error: 'upstream_redirect_blocked' }, mode);
      });
    }, { timeoutMs: 1000, fetch: async () => upstream });
    assert.equal(cancellations, 1, `${mode} cancellation must be attempted once`);
  }
});

test('64 KiB request body boundary is enforced from stream bytes', async () => {
  let calls = 0;
  await withHarness(async () => {
    const exact = await middleware(apiRequest('/api/fixed', {
      method: 'POST', body: ' '.repeat(64 * 1024 - 2) + '{}',
    }));
    assert.equal(exact.status, 201);
    const excess = await middleware(apiRequest('/api/fixed', {
      method: 'POST', body: ' '.repeat(64 * 1024 - 1) + '{}',
      headers: { 'content-length': '1' },
    }));
    assert.equal(excess.status, 413);
    assert.deepEqual(await excess.json(), { error: 'request_body_too_large' });
  }, { fetch: () => { calls++; return upstreamJson({ ok: true }, 201); } });
  assert.equal(calls, 1);
});

test('one deadline covers an unfinished request body and cancels its reader', async () => {
  let cancelled = false;
  let calls = 0;
  const body = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('{')); },
    cancel() { cancelled = true; },
  });
  await withHarness(async () => {
    const response = await settleWithin(middleware(apiRequest('/api/fixed', { method: 'POST', body })));
    assert.equal(response.status, 504);
    assert.deepEqual(await response.json(), { error: 'upstream_timeout' });
  }, { timeoutMs: 10, fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  assert.equal(cancelled, true);
  assert.equal(calls, 0);
});

test('one deadline covers stalled upstream headers even if fetch ignores abort', async () => {
  await withHarness(async () => {
    const response = await settleWithin(middleware(apiRequest('/api/health')));
    assert.equal(response.status, 504);
  }, { timeoutMs: 10, fetch: () => new Promise(() => {}) });
});

test('one deadline covers a stalled upstream body and cancels its reader', async () => {
  let cancelled = false;
  await withHarness(async () => {
    const response = await settleWithin(middleware(apiRequest('/api/health')));
    assert.equal(response.status, 504);
  }, {
    timeoutMs: 10,
    fetch: async () => new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode('{')); },
      cancel() { cancelled = true; },
    }), { headers: { 'content-type': 'application/json' } }),
  });
  assert.equal(cancelled, true);
});

test('only a validated configured hostname is used; literal/private-name destinations fail closed', async () => {
  let calls = 0;
  for (const baseUrl of [
    'http://api.example.test', 'https://user:pass@api.example.test',
    'https://localhost', 'https://service.localhost', 'https://127.0.0.1',
    'https://2130706433', 'https://169.254.169.254', 'https://[::1]',
    'https://metadata.google.internal', 'https://service.internal',
    'https://service.local', 'https://api.example.test/?token=x',
  ]) {
    await withHarness(async () => {
      const response = await middleware(apiRequest('/api/health'));
      assert.equal(response.status, 503, baseUrl);
    }, { baseUrl, fetch: () => { calls++; return upstreamJson({ ok: true }); } });
  }
  await withHarness(async () => {
    const response = await middleware(apiRequest('/api/summary'));
    assert.equal(response.status, 200);
  }, {
    baseUrl: 'https://trusted.example.test/base',
    fetch: async (target) => {
      calls++;
      assert.equal(target, 'https://trusted.example.test/base/api/summary');
      return upstreamJson({ months: [] });
    },
  });
  assert.equal(calls, 1);
});

test('decoded JSON keys and strings cannot reflect secret or sensitive URL', async () => {
  const secretValues = ['discarded"quote', 'discarded\\slash', 'discarded-é'];
  for (const value of secretValues) {
    for (const payload of [
      { nested: [{ message: `prefix ${value} suffix` }] },
      { nested: [{ [`prefix ${value} suffix`]: 'value' }] },
    ]) {
      await withHarness(async () => {
        const response = await middleware(apiRequest('/api/health'));
        assert.equal(response.status, 502);
        assert.deepEqual(await response.json(), { error: 'upstream_invalid_response' });
      }, { internalSecret: value, fetch: async () => upstreamJson(payload) });
    }
  }
  await withHarness(async () => {
    const response = await middleware(apiRequest('/api/health'));
    assert.equal(response.status, 502);
  }, {
    internalSecret: 'discarded-é',
    fetch: async () => new Response('{"nested":[{"text":"discarded-\\u00e9"}]}', {
      headers: { 'content-type': 'application/json' },
    }),
  });
  for (const value of [BASE_URL, new URL(BASE_URL).origin]) {
    await withHarness(async () => {
      const response = await middleware(apiRequest('/api/health'));
      assert.equal(response.status, 502);
    }, { fetch: async () => upstreamJson({ nested: [{ [value]: 'reflected' }] }) });
  }
});

test('login, logout, and protected assets retain the gate and call continuation', async () => {
  const continuation = { continued: true };
  let calls = 0;
  const next = () => { calls++; return continuation; };
  await withHarness(async () => {
    assert.equal(await handleMiddleware(new Request(`${SITE_URL}/login`), next), continuation);
    const form = new FormData();
    form.set('password', DASHBOARD_PASSWORD);
    const login = await handleMiddleware(new Request(`${SITE_URL}/login`, { method: 'POST', body: form }), next);
    assert.equal(login.status, 303);
    assert.equal(login.headers.get('location'), `${SITE_URL}/`);
    const cookie = login.headers.get('set-cookie').split(';')[0];
    assert.equal(await handleMiddleware(new Request(`${SITE_URL}/style.css`, { headers: { cookie } }), next), continuation);
    const denied = await handleMiddleware(new Request(`${SITE_URL}/style.css`), next);
    assert.equal(denied.status, 303);
    assert.equal(denied.headers.get('location'), `${SITE_URL}/login`);
    const logout = await handleMiddleware(new Request(`${SITE_URL}/logout`, { headers: { cookie } }), next);
    assert.equal(logout.status, 303);
    assert.match(logout.headers.get('set-cookie'), /Max-Age=0/);
  }, { fetch: () => assert.fail('static route reached fetch') });
  assert.equal(calls, 2);
});

// ── Atajos de iPhone (S5, t_a60a2f67): manifest/íconos públicos + destino
// preservado a través del login con allowlist same-origin ──────────────────

test('manifest and icon exact paths bypass the gate: public, GET-only, no session or DASHBOARD_PASSWORD required', async () => {
  const previousPassword = process.env.DASHBOARD_PASSWORD;
  delete process.env.DASHBOARD_PASSWORD;
  try {
    const continuation = { continued: true };
    const next = () => continuation;
    for (const path of ['/manifest.webmanifest', '/icons/icon-180.png', '/icons/icon-192.png', '/icons/icon-512.png']) {
      assert.equal(await handleMiddleware(new Request(`${SITE_URL}${path}`), next), continuation, path);
    }
    // Not one of the exact allowlisted paths: still gated (missing-secret 500, same as any other path).
    const otherIcon = await handleMiddleware(new Request(`${SITE_URL}/icons/icon-1024.png`), next);
    assert.equal(otherIcon.status, 500);
    // Same exact path but POST: not public, falls through to the gate.
    const postManifest = await handleMiddleware(new Request(`${SITE_URL}/manifest.webmanifest`, { method: 'POST' }), next);
    assert.equal(postManifest.status, 500);
  } finally {
    if (previousPassword === undefined) delete process.env.DASHBOARD_PASSWORD;
    else process.env.DASHBOARD_PASSWORD = previousPassword;
  }
});

test('an unauthenticated known ?accion= deep link is preserved through /login; anything else defaults to "/"', async () => {
  await withHarness(async () => {
    for (const accion of ['gasto', 'ingreso', 'fijo', 'fijos']) {
      const response = await handleMiddleware(new Request(`${SITE_URL}/?accion=${accion}`), () => assert.fail('must redirect, not continue'));
      assert.equal(response.status, 303);
      const expected = new URL('/login', SITE_URL);
      expected.searchParams.set('next', `/?accion=${accion}`);
      assert.equal(response.headers.get('location'), expected.toString(), accion);
    }
    const noPreservedNext = [
      '/?accion=desconocido', '/?accion=gasto&otro=1', '/style.css?accion=gasto', '/',
      '/?accion=gasto&accion=ingreso',
    ];
    for (const path of noPreservedNext) {
      const response = await handleMiddleware(new Request(`${SITE_URL}${path}`), () => assert.fail('must redirect, not continue'));
      assert.equal(response.status, 303, path);
      assert.equal(response.headers.get('location'), `${SITE_URL}/login`, path);
    }
  }, { fetch: () => assert.fail('must not reach the VPS') });
});

test('POST /login preserves a validated next target on success and failure; a forged or malformed next falls back to "/"', async () => {
  await withHarness(async () => {
    const validNext = '/?accion=ingreso';

    const okForm = new FormData();
    okForm.set('password', DASHBOARD_PASSWORD);
    const ok = await handleMiddleware(
      new Request(`${SITE_URL}/login?next=${encodeURIComponent(validNext)}`, { method: 'POST', body: okForm }),
      () => assert.fail('must redirect, not continue')
    );
    assert.equal(ok.status, 303);
    assert.equal(ok.headers.get('location'), `${SITE_URL}${validNext}`);
    assert.match(ok.headers.get('set-cookie'), /^dashboard_session=/);

    const badForm = new FormData();
    badForm.set('password', 'wrong-password');
    const bad = await handleMiddleware(
      new Request(`${SITE_URL}/login?next=${encodeURIComponent(validNext)}`, { method: 'POST', body: badForm }),
      () => assert.fail('must redirect, not continue')
    );
    assert.equal(bad.status, 303);
    const badLocation = new URL(bad.headers.get('location'));
    assert.equal(badLocation.pathname, '/login');
    assert.equal(badLocation.searchParams.get('error'), '1');
    assert.equal(badLocation.searchParams.get('next'), validNext);
    assert.equal(bad.headers.get('set-cookie'), null);

    const forgedNextValues = [
      'https://evil.example.test/', '//evil.example.test', '/other-page',
      '/?accion=gasto&x=1', '/?accion=desconocido', '/\\evil', '/?ACCION=gasto',
    ];
    for (const forgedNext of forgedNextValues) {
      const forgedForm = new FormData();
      forgedForm.set('password', DASHBOARD_PASSWORD);
      const forged = await handleMiddleware(
        new Request(`${SITE_URL}/login?next=${encodeURIComponent(forgedNext)}`, { method: 'POST', body: forgedForm }),
        () => assert.fail('must redirect, not continue')
      );
      assert.equal(forged.status, 303, forgedNext);
      assert.equal(forged.headers.get('location'), `${SITE_URL}/`, forgedNext);
    }
  }, { fetch: () => assert.fail('must not reach the VPS') });
});
