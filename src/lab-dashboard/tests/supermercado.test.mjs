import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHmac, webcrypto } from 'node:crypto';
import vm from 'node:vm';
import { handleMiddleware } from '../middleware.js';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const script = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const superStart = script.indexOf('let supermercadoData = null;');
const superEnd = script.indexOf('// ── VISTA RECETAS', superStart);
const superScript = script.slice(superStart, superEnd);
const emptySnapshot = () => ({ categorias: [], productos: [], resumen: { global: {
  productos: 0, a_reponer: 0, vacios: 0, reponer: 0, ok: 0, porcentaje_vacio: 0, porcentaje_lleno: 0,
}, categorias: [] } });

test('UI stock uses live API, explicit empty/error states, stock audit and PDF action', () => {
  assert.match(html, /id="supermercado-product-form"/);
  assert.match(html, /id="supermercado-category-form"/);
  assert.match(html, /id="supermercado-status"[^>]*aria-live="polite"/);
  assert.match(html, /id="supermercado-availability"[^>]*aria-live="polite"/);
  assert.match(script, /fetchJSON\('\/api\/supermercado'\)/);
  assert.match(script, /\/api\/supermercado\/productos\/\$\{id\}\/stock/);
  assert.match(script, /\/api\/supermercado\/lista\.pdf/);
  assert.match(script, /escapeHtml\(row\.producto\)/);
  assert.doesNotMatch(script.slice(script.indexOf('async function ensureComprasLoaded'), script.indexOf('// ── VISTA RECETAS')), /data\/compras\.json/);
});

test('PDF proxy requires session and returns fresh binary response', async () => {
  const names = ['DASHBOARD_PASSWORD', 'VPS_API_BASE_URL', 'VPS_INTERNAL_SECRET'];
  const old = Object.fromEntries(names.map(name => [name, process.env[name]]));
  const originalFetch = globalThis.fetch;
  process.env.DASHBOARD_PASSWORD = 'synthetic-password';
  process.env.VPS_API_BASE_URL = 'https://example.test/private';
  process.env.VPS_INTERNAL_SECRET = 'synthetic-internal-secret';
  const expiry = String(Date.now() + 60_000);
  const signature = createHmac('sha256', process.env.DASHBOARD_PASSWORD).update(expiry).digest('hex');
  const url = 'https://life.example.test/api/supermercado/lista.pdf';
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(new TextEncoder().encode('%PDF-1.4\nsynthetic'), { status: 200, headers: { 'content-type': 'application/pdf', 'set-cookie': 'bad=1' } }); };
  try {
    assert.equal((await handleMiddleware(new Request(url), () => new Response('static'))).status, 401);
    assert.equal(calls, 0);
    const response = await handleMiddleware(new Request(url, { headers: { cookie: `dashboard_session=${expiry}.${signature}` } }), () => new Response('static'));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'application/pdf');
    assert.equal(response.headers.get('set-cookie'), null);
    assert.match(await response.text(), /^%PDF-/);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
    for (const name of names) old[name] === undefined ? delete process.env[name] : process.env[name] = old[name];
  }
});

test('UI renders empty and error states without stock snapshot fallback', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '',
      classList: { toggle() {} }, addEventListener() {} });
    return elements.get(id);
  };
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => [] }, Intl, Number, Error,
    fetchJSON: async () => emptySnapshot(),
    escapeHtml: value => String(value).replaceAll('<', '&lt;'), fetch: async () => { throw new Error('unexpected'); } });
  vm.runInContext(superScript, context);
  await vm.runInContext('ensureComprasLoaded()', context);
  assert.match(element('supermercado-content').innerHTML, /No hay productos/);
  vm.runInContext(`supermercadoData = null; fetchJSON = async () => { throw new Error('sin API'); }`, context);
  await vm.runInContext('ensureComprasLoaded()', context);
  assert.match(element('supermercado-status').textContent, /sin API/);
  assert.match(element('supermercado-content').textContent, /No se pudo cargar/);
});

test('Supermercado gates writes on its own valid GET and revokes them on failed reload or 401/403 mutation', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '', disabled: true,
      classList: { toggle() {} }, addEventListener() {}, reportValidity: () => true });
    return elements.get(id);
  };
  const controls = [element('category-submit'), element('product-submit')];
  const reads = [];
  const mutations = [];
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => controls },
    Intl, Number, Error, escapeHtml: String,
    fetchJSON: async () => { const next = reads.shift(); if (next instanceof Error) throw next; return next; },
    fetch: async (_path, options) => {
      mutations.push(options.method);
      const status = mutations.length === 1 ? 401 : 403;
      return { ok: false, status, json: async () => {
        if (status === 403) throw new Error('Respuesta no JSON');
        return { error: 'Sesión rechazada' };
      } };
    } });
  vm.runInContext(superScript, context);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false);
  assert.equal(mutations.length, 0, 'antes de GET no debe haber fetch de escritura');
  assert.match(element('supermercado-status').textContent, /solo lectura\/no disponible/);
  reads.push({ categorias: [], productos: [], resumen: { global: {}, categorias: [] } });
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), false, 'estructura inválida no habilita escritura');
  assert.equal(controls.every(control => control.disabled), true);
  reads.push(emptySnapshot());
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(vm.runInContext('supermercadoWriteAvailable', context), true);
  assert.equal(controls.every(control => !control.disabled), true);
  assert.match(element('supermercado-availability').textContent, /Supermercado en vivo/);
  reads.push(new Error('sin API'));
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), false);
  assert.equal(controls.every(control => control.disabled), true);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false);
  assert.equal(mutations.length, 0, 'una recarga fallida no permite escribir con datos viejos');
  reads.push(emptySnapshot());
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false);
  assert.equal(mutations.length, 1);
  assert.equal(controls.every(control => control.disabled), true, 'mutation 401 revoca escritura');
  assert.equal(vm.runInContext('supermercadoMutationPending', context), false, '401 libera el lock sin habilitar controles');
  reads.push(emptySnapshot());
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false);
  assert.equal(mutations.length, 2);
  assert.equal(controls.every(control => control.disabled), true, 'mutation 403 revoca escritura');
  assert.equal(vm.runInContext('supermercadoMutationPending', context), false, '403 libera el lock sin habilitar controles');
  reads.push(Object.assign(new Error('Sin sesión'), { status: 401 }));
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), false);
  assert.match(element('supermercado-availability').textContent, /solo lectura\/no disponible/);
});

test('an invalidated old GET cannot reenable writes after the newer GET fails', async () => {
  let resolveOld;
  const oldGet = new Promise(resolve => { resolveOld = resolve; });
  const reads = [emptySnapshot(), oldGet, new Error('recarga fallida')];
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '',
      classList: { toggle() {} }, addEventListener() {} });
    return elements.get(id);
  };
  const control = { disabled: true };
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => [control] },
    Intl, Number, Error, escapeHtml: String, fetchJSON: async () => {
      const next = reads.shift(); if (next instanceof Error) throw next; return next;
    }, fetch: async () => { throw new Error('unexpected mutation'); } });
  vm.runInContext(superScript, context);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const oldLoad = vm.runInContext('ensureComprasLoaded(true)', context);
  const freshLoad = vm.runInContext('ensureComprasLoaded(true)', context);
  resolveOld(emptySnapshot());
  assert.equal(await oldLoad, false);
  assert.equal(await freshLoad, false);
  assert.equal(vm.runInContext('supermercadoWriteAvailable', context), false);
  assert.equal(control.disabled, true);
});

test('global snapshot banner limits its scope while Supermercado reports its own status', () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', hidden: false, classList: { toggle() {} } });
    return elements.get(id);
  };
  const start = script.indexOf('function updateAvailability()');
  const end = script.indexOf('// ── NAVEGACIÓN', start);
  const context = vm.createContext({ document: { getElementById: element, querySelector: () => element('fijos-snapshot'), querySelectorAll: () => [] },
    liveMode: false, authState: 'unavailable', inventoryAvailable: false,
    reloadFailed: false, writePending: false, reloadPending: false });
  vm.runInContext(script.slice(start, end) + '\nupdateAvailability()', context);
  assert.match(element('api-status').textContent, /Finanzas y otros módulos.*snapshot de solo lectura/i);
  assert.match(element('api-status').textContent, /Supermercado informa su propio estado/);
  assert.doesNotMatch(element('api-status').textContent, /todo el dashboard|no se pueden guardar cambios\.(?! Supermercado)/i);
});

test('successful stock write waits for a fresh GET and never restores an older snapshot', async () => {
  const deferred = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
  };
  const oldGet = deferred();
  const patch = deferred();
  const freshGet = deferred();
  const reads = [];
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '',
      classList: { toggle() {} }, addEventListener() {}, reportValidity: () => true });
    return elements.get(id);
  };
  const snapshot = (stock, version) => ({ categorias: [], productos: [{ id: 7, producto: 'Leche', unidad: 'L',
    categoria: null, stock_deseado: 5, stock_actual: stock, a_comprar: 5 - stock,
    porcentaje_faltante: (5 - stock) * 20, estado: stock < 5 ? 'Reponer' : 'OK', version }],
    resumen: { global: { productos: 1, a_reponer: stock < 5 ? 1 : 0, vacios: 0, reponer: stock < 5 ? 1 : 0,
      ok: stock === 5 ? 1 : 0, porcentaje_vacio: 0, porcentaje_lleno: 100 }, categorias: [] } });
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => [] }, Intl, Number, Error,
    escapeHtml: String,
    fetchJSON: async () => { const next = reads.length === 1 ? oldGet : freshGet; reads.push(next); return reads.length === 1 ? snapshot(1, 1) : next.promise; },
    fetch: async (path, options) => {
      assert.equal(path, '/api/supermercado/productos/7/stock');
      assert.equal(options.method, 'PATCH');
      const body = JSON.parse(options.body);
      assert.equal(body.expected_version, 1);
      assert.equal(body.stock_actual, 5);
      return patch.promise;
    } });
  vm.runInContext(superScript, context);

  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  assert.equal(vm.runInContext('supermercadoWriteAvailable', context), true);
  element('super-stock-7').value = '5';
  const oldLoad = vm.runInContext('ensureComprasLoaded(true)', context);
  const mutation = vm.runInContext('saveSuperStock(7)', context);
  patch.resolve({ ok: true, json: async () => ({ registro: { id: 7, version: 2 } }) });
  for (let step = 0; step < 10 && !vm.runInContext('supermercadoRefreshPromise', context); step++) await Promise.resolve();
  assert.ok(vm.runInContext('supermercadoRefreshPromise', context), 'the PATCH must queue a forced refresh');
  const reopening = vm.runInContext('ensureComprasLoaded()', context);
  oldGet.resolve(snapshot(0, 1));
  assert.equal(await oldLoad, false);
  await Promise.resolve();
  assert.equal(reads.length, 3, 'the successful PATCH must start a later GET');
  assert.equal(vm.runInContext('supermercadoData.productos[0].stock_actual', context), 1,
    'the old GET cannot overwrite the cache before the fresh GET');
  freshGet.resolve(snapshot(5, 2));
  await mutation;
  assert.equal(await reopening, true, 'reopening during the refresh waits for the new snapshot');
  assert.equal(vm.runInContext('supermercadoData.productos[0].stock_actual', context), 5);
  assert.equal(vm.runInContext('supermercadoData.productos[0].version', context), 2);
  assert.match(element('supermercado-content').innerHTML, /value="5"/);
  assert.doesNotMatch(element('supermercado-status').textContent, /no se pudo recargar|pérdida/i);
  await vm.runInContext('ensureComprasLoaded()', context);
  assert.equal(reads.length, 3, 'reopening the tab must use the new snapshot');
  assert.equal(vm.runInContext('supermercadoData.productos[0].version', context), 2);
});

test('two product form submits send one POST and a valid GET cannot unlock controls during refresh', async () => {
  const deferred = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
  };
  const post = deferred();
  const refresh = deferred();
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '', disabled: true,
      classList: { toggle() {} }, addEventListener(type, handler) { this[type] = handler; },
      reportValidity: () => true, reset() { this.resetCount = (this.resetCount || 0) + 1; } });
    return elements.get(id);
  };
  const form = element('supermercado-product-form');
  form.elements = { id: { value: '' }, producto: { value: 'Leche' }, unidad: { value: 'L' },
    categoria_id: { value: '' }, stock_deseado: { value: '5' }, stock_actual: { value: '1' } };
  const controls = [element('product-submit'), element('category-submit')];
  let reads = 0;
  const writes = [];
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => controls },
    Intl, Number, Error, escapeHtml: String,
    fetchJSON: async () => ++reads === 1 ? emptySnapshot() : refresh.promise,
    fetch: async (path, options) => { writes.push({ path, options }); return post.promise; } });
  vm.runInContext(superScript, context);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const submit = () => form.submit({ preventDefault() {}, currentTarget: form });
  const first = submit();
  const second = submit();
  assert.equal(await second, undefined);
  assert.equal(writes.length, 1, 'un doble submit de alta debe emitir un solo POST');
  assert.equal(writes[0].options.method, 'POST');
  assert.equal(controls.every(control => control.disabled), true);
  const concurrentGet = vm.runInContext('ensureComprasLoaded(true)', context);
  refresh.resolve(emptySnapshot());
  assert.equal(await concurrentGet, true);
  assert.equal(controls.every(control => control.disabled), true, 'GET válido durante POST no desbloquea controles');
  assert.equal(vm.runInContext('supermercadoMutationPending', context), true);
  post.resolve({ ok: true, json: async () => ({ registro: { id: 1, version: 1 } }) });
  await first;
  assert.equal(writes.length, 1);
  assert.equal(form.resetCount, 1);
  assert.equal(vm.runInContext('supermercadoMutationPending', context), false);
  assert.equal(controls.every(control => !control.disabled), true);
});

test('failed product POST releases the single-flight lock and allows a later retry', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '', disabled: true,
      classList: { toggle() {} }, addEventListener() {} });
    return elements.get(id);
  };
  const control = element('product-submit');
  let calls = 0;
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => [control] },
    Intl, Number, Error, escapeHtml: String, fetchJSON: async () => emptySnapshot(),
    fetch: async () => {
      calls++;
      return calls === 1
        ? { ok: false, status: 500, json: async () => ({ error: 'Error temporal' }) }
        : { ok: true, json: async () => ({ registro: { id: 1, version: 1 } }) };
    } });
  vm.runInContext(superScript, context);
  await vm.runInContext('ensureComprasLoaded()', context);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false);
  assert.equal(vm.runInContext('supermercadoMutationPending', context), false);
  assert.equal(control.disabled, false);
  assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), true);
  assert.equal(calls, 2);
  assert.equal(control.disabled, false);
});

test('UI sends read version, keeps conflicts visible, and opens the next history page', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '', hidden: false, dataset: {},
      classList: { toggle() {} }, addEventListener() {}, reportValidity: () => true,
      insertAdjacentElement(_where, child) { elements.set(child.id, child); } });
    return elements.get(id);
  };
  const context = vm.createContext({ document: { getElementById: element, querySelectorAll: () => [], createElement: () => ({ addEventListener() {} }) },
    Intl, Number, Error, confirm: () => true, encodeURIComponent, escapeHtml: String,
    fetchJSON: async () => emptySnapshot(),
    fetch: async () => { throw new Error('unexpected fetch'); } });
  vm.runInContext(superScript, context);
  element('super-stock-7').value = '4';
  vm.runInContext('supermercadoData = { productos: [{ id: 7, producto: "Leche", version: 3 }], categorias: [] }; supermercadoWriteAvailable = true', context);
  const writes = [];
  const realMutate = context.superMutate;
  context.superMutate = async (...args) => { writes.push(args); return true; };
  await vm.runInContext('saveSuperStock(7)', context);
  await vm.runInContext('deleteSuperProduct(7)', context);
  assert.equal(writes[0][2].expected_version, 3);
  assert.equal(writes[1][2].expected_version, 3);
  context.superRequest = async (_method, path) => ({ historial: [{ id: path.includes('cursor=') ? 2 : 3, fecha_utc: 'now', operacion: 'stock', actor: 'qa', antes: null, despues: {} }],
    next_cursor: path.includes('cursor=') ? null : 3, has_more: !path.includes('cursor=') });
  await vm.runInContext('showSuperHistory(7)', context);
  assert.equal(element('supermercado-history-next').hidden, false);
  await vm.runInContext('showSuperHistory(7, superHistoryCursor)', context);
  assert.equal(element('supermercado-history-next').hidden, true);
  let reloads = 0;
  context.ensureComprasLoaded = async () => { reloads++; return true; };
  context.superRequest = async () => { const error = new Error('Producto modificado; recargá.'); error.status = 409; throw error; };
  assert.equal(await realMutate('PATCH', '/api/supermercado/productos/7', {}, 'guardado'), false);
  assert.equal(reloads, 1);
  assert.match(element('supermercado-status').textContent, /Revisá los datos recargados/);
  assert.match(superScript, /payload\.expected_version = Number\(form\.dataset\.version\)/);
});

test('F4 proxy rejects unauthenticated and cross-origin writes, malformed and oversized PDF', async () => {
  const names = ['DASHBOARD_PASSWORD', 'VPS_API_BASE_URL', 'VPS_INTERNAL_SECRET'];
  const old = Object.fromEntries(names.map(name => [name, process.env[name]]));
  const originalFetch = globalThis.fetch;
  process.env.DASHBOARD_PASSWORD = 'synthetic-password';
  process.env.VPS_API_BASE_URL = 'https://example.test/private';
  process.env.VPS_INTERNAL_SECRET = 'synthetic-internal-secret';
  const expiry = String(Date.now() + 60_000);
  const signature = createHmac('sha256', process.env.DASHBOARD_PASSWORD).update(expiry).digest('hex');
  const cookie = `dashboard_session=${expiry}.${signature}`;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response('bad', { headers: { 'content-type': 'application/pdf' } }); };
  try {
    const root = 'https://life.example.test';
    const denied = await handleMiddleware(new Request(`${root}/api/supermercado/productos`, { method: 'POST', headers: { origin: root }, body: '{}' }), () => new Response('static'));
    assert.equal(denied.status, 401);
    const cross = await handleMiddleware(new Request(`${root}/api/supermercado/productos`, { method: 'POST', headers: { cookie, origin: 'https://evil.example.test' }, body: '{}' }), () => new Response('static'));
    assert.equal(cross.status, 403);
    const invalid = await handleMiddleware(new Request(`${root}/api/supermercado/lista.pdf`, { headers: { cookie } }), () => new Response('static'));
    assert.equal(invalid.status, 502);
    globalThis.fetch = async () => { calls++; return new Response(new Uint8Array(8 * 1024 * 1024 + 1).fill(65), { headers: { 'content-type': 'application/pdf' } }); };
    const excess = await handleMiddleware(new Request(`${root}/api/supermercado/lista.pdf`, { headers: { cookie } }), () => new Response('static'));
    assert.equal(excess.status, 502);
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = originalFetch;
    for (const name of names) old[name] === undefined ? delete process.env[name] : process.env[name] = old[name];
  }
});
