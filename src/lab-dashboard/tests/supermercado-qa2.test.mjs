import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../style.css', import.meta.url), 'utf8');
const script = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const source = script.slice(script.indexOf('let supermercadoData = null;'), script.indexOf('// ── VISTA RECETAS'));
const escapeHtml = value => String(value ?? '—').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const counts = rows => {
  const vacios = rows.filter(row => row.estado === 'Vacío').length;
  return { productos: rows.length, a_reponer: rows.filter(row => row.a_comprar > 0).length,
    vacios, reponer: rows.filter(row => row.estado === 'Reponer').length,
    ok: rows.filter(row => row.estado === 'OK').length,
    porcentaje_vacio: rows.length ? 100 * vacios / rows.length : 0,
    porcentaje_lleno: rows.length ? 100 * (rows.length - vacios) / rows.length : 0 };
};
const product = (id, stock, desired = 5, category = 1, version = 1, name = 'Leche') => ({ id, categoria_id: category,
  categoria: category === null ? null : 'Lácteos', producto: name, unidad: 'L', stock_actual: stock,
  stock_deseado: desired, a_comprar: Math.max(0, desired - stock), porcentaje_faltante: desired ? Math.max(0, desired - stock) / desired * 100 : 0,
  estado: stock <= 0 ? 'Vacío' : stock < desired ? 'Reponer' : 'OK', version });
const snapshot = (rows = [], categories = [{ id: 1, nombre: 'Lácteos', orden: 2 }]) => ({ categorias: categories, productos: rows,
  resumen: { global: counts(rows), categorias: [...categories.map(cat => ({ ...cat, ...counts(rows.filter(row => row.categoria_id === cat.id)) })),
    { id: null, nombre: 'Sin categoría', orden: null, ...counts(rows.filter(row => row.categoria_id === null)) }] } });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const flushUntil = async (condition) => {
  for (let step = 0; step < 30 && !condition(); step++) await Promise.resolve();
  assert.ok(condition(), 'la operación diferida debe alcanzar el punto esperado');
};
function harness({ reads = [], writes = [], online = true, withWindow = false } = {}) {
  const elements = new Map();
  const events = {};
  const element = id => {
    if (!elements.has(id)) {
      const item = { id, value: '', innerHTML: '', textContent: '', hidden: false, disabled: false, open: false, dataset: {},
        classList: { toggle() {} }, addEventListener(type, callback) { this[type] = callback; }, focus() { document.activeElement = this; },
        showModal() { this.open = true; }, close() { this.open = false; }, blur() { document.activeElement = null; } };
      elements.set(id, item);
    }
    return elements.get(id);
  };
  const document = { activeElement: null, visibilityState: 'visible', getElementById: element, querySelectorAll: () => [],
    addEventListener(type, callback) { events[type] = callback; } };
  const window = withWindow ? { addEventListener(type, callback) { events[type] = callback; }, setInterval(callback) { events.interval = callback; } } : undefined;
  const requests = [];
  const context = vm.createContext({ document, window, navigator: { onLine: online }, currentView: 'supermercado',
    Intl, Number, Error, encodeURIComponent, escapeHtml, clearTimeout, setTimeout,
    fetchJSON: async () => { const result = reads.shift(); if (result instanceof Error) throw result; return await result; },
    fetch: async (path, options) => { requests.push({ path, options }); const result = writes.shift(); if (result instanceof Error) throw result; return await result; } });
  vm.runInContext(source, context);
  return { context, element, document, events, requests };
}

function domHarness(reads, writes = []) {
  const standalone = new Map();
  const document = { activeElement: null };
  class TextNode {
    constructor(text) { this.nodeType = 3; this.textContent = text; this.parentNode = null; }
    remove() {
      if (!this.parentNode) return;
      this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1);
      this.parentNode = null;
    }
  }
  class Node {
    constructor(classes = '', id = '') {
      this.nodeType = 1;
      this.classes = classes.split(' ').filter(Boolean);
      this.classList = { contains: name => this.classes.includes(name), toggle() {} };
      this.id = id;
      this._childNodes = [];
      this.parentNode = null;
      this.dataset = {};
      this.innerHTML = '';
      this.value = '';
      this.disabled = false;
    }
    get childNodes() { return this._childNodes; }
    get children() { return this._childNodes.filter(node => node.nodeType === 1); }
    get textContent() { return this._childNodes.map(node => node.textContent).join(''); }
    set textContent(value) {
      for (const child of this._childNodes) child.parentNode = null;
      this._childNodes = [];
      if (value) this.insertBefore(new TextNode(value), null);
    }
    get isConnected() { return this === content || Boolean(this.parentNode?.isConnected); }
    get nextSibling() { return this.parentNode?.childNodes[this.parentNode.childNodes.indexOf(this) + 1] || null; }
    contains(node) { return this === node || this.children.some(child => child.contains(node)); }
    insertBefore(node, before) {
      if (node.nodeType === 1 && node.isConnected && node.contains(document.activeElement)) document.activeElement = null;
      if (node.parentNode) node.parentNode.childNodes.splice(node.parentNode.childNodes.indexOf(node), 1);
      const index = before ? this.childNodes.indexOf(before) : this.childNodes.length;
      this.childNodes.splice(index, 0, node);
      node.parentNode = this;
      return node;
    }
    remove() {
      if (!this.parentNode) return;
      this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1);
      this.parentNode = null;
    }
    querySelectorAll(selector) {
      const matches = node => selector.startsWith('.') && node.classes.includes(selector.slice(1));
      return this.children.flatMap(child => [matches(child) ? child : null, ...child.querySelectorAll(selector)].filter(Boolean));
    }
    querySelector(selector) {
      if (selector === '.super-group-head') return this.header;
      if (selector === '.super-group-items') return this.items;
      if (selector === '.super-item-main') return this.main;
      if (selector === '.super-stock-control label') return this.label;
      if (selector === 'input') return this.input;
      return null;
    }
    focus() { document.activeElement = this; }
    blur() { if (document.activeElement === this) document.activeElement = null; }
    showModal() { this.open = true; }
    close() { this.open = false; }
  }
  const content = new Node();
  content.textContent = 'Cargando…';
  const parse = markup => {
    const root = new Node();
    for (const sectionMatch of markup.matchAll(/<section class="super-group" data-super-category-id="([^"]+)"[^>]*>([\s\S]*?)<\/section>/g)) {
      const section = new Node('super-group');
      section.dataset.superCategoryId = sectionMatch[1];
      section.header = new Node('super-group-head');
      section.header.innerHTML = sectionMatch[2].match(/<header class="super-group-head">([\s\S]*?)<\/header>/)?.[1] || '';
      section.items = new Node('super-group-items');
      section.insertBefore(section.header, null);
      section.insertBefore(section.items, null);
      for (const articleMatch of sectionMatch[2].matchAll(/<article class="super-item" data-super-product-id="(\d+)">([\s\S]*?)<\/article>/g)) {
        const article = new Node('super-item');
        article.dataset.superProductId = articleMatch[1];
        const body = articleMatch[2];
        article.main = new Node('super-item-main');
        article.main.innerHTML = body.match(/<div class="super-item-main">([\s\S]*)<\/div>\s*<div class="super-stock-control">/)?.[1] || '';
        article.label = new Node();
        article.label.innerHTML = body.match(/<label[^>]*>([^<]*)<\/label>/)?.[1] || '';
        article.input = new Node('', `super-stock-${articleMatch[1]}`);
        article.input.value = body.match(/<input[^>]* value="([^"]*)"/)?.[1] || '';
        article.status = new Node('', `super-stock-status-${articleMatch[1]}`);
        article.status.innerHTML = body.match(/<div id="super-stock-status-[^"]+"[^>]*>([\s\S]*?)<\/div>/)?.[1] || '';
        article.history = new Node('', `super-history-button-${articleMatch[1]}`);
        article.edit = new Node('', `super-edit-button-${articleMatch[1]}`);
        for (const child of [article.main, article.label, article.input, article.status, article.edit, article.history]) article.insertBefore(child, null);
        section.items.insertBefore(article, null);
      }
      root.insertBefore(section, null);
    }
    return root;
  };
  const find = (node, id) => node.id === id ? node : node.children.map(child => find(child, id)).find(Boolean);
  const element = id => {
    if (id === 'supermercado-content') return content;
    const found = find(content, id);
    if (found) return found;
    if (!standalone.has(id)) standalone.set(id, Object.assign(new Node('', id), { textContent: '', addEventListener() {} }));
    return standalone.get(id);
  };
  document.getElementById = id => id === 'supermercado-content' ? content : element(id);
  document.createElement = tag => tag === 'template' ? { content: new Node(), set innerHTML(markup) { this.content = parse(markup); } } : new Node();
  document.querySelectorAll = () => [];
  const requests = [];
  const context = vm.createContext({ document, navigator: { onLine: true }, Intl, Number, Error, escapeHtml, clearTimeout, setTimeout,
    fetchJSON: async () => { const result = reads.shift(); if (result instanceof Error) throw result; return await result; },
    fetch: async (path, options) => {
      requests.push({ path, options });
      const response = writes.shift();
      if (!response) throw new Error('unexpected PATCH');
      return response;
    } });
  vm.runInContext(source, context);
  return { context, element, document, requests, content };
}

test('QA3: los controles de una unidad conservan los nodos al pasar al siguiente producto', async () => {
  const { context, element, document, requests } = domHarness([snapshot([product(1, 0.5), product(2, 1.25)])]);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const first = element('super-stock-1');
  const second = element('super-stock-2');
  vm.runInContext('handleSuperStockBlur(1)', context);
  assert.equal(element('super-stock-2'), second, 'un blur limpio conserva el destino');
  first.value = '0.5';
  first.focus();
  vm.runInContext('handleSuperStockStep(1, 1)', context);
  assert.equal(first.value, '1.5');
  vm.runInContext('handleSuperStockBlur(1, { relatedTarget: { dataset: { superStockTarget: "super-stock-1" } } })', context);
  assert.equal(requests.length, 0, 'el click del control no publica un valor anterior');
  second.focus();
  vm.runInContext('renderSupermercadoList()', context);
  assert.equal(element('super-stock-1'), first);
  assert.equal(element('super-stock-2'), second);
  assert.equal(document.activeElement, second);
  assert.equal(vm.runInContext('superStockDrafts.get(1).value', context), '1.5');
  vm.runInContext('clearTimeout(superStockDrafts.get(1).timer)', context);
});

// The old manual action tests remain in supermercado.test.mjs; these cover the new flows.
test('clean stock blur keeps the next input and History action mounted through verified saves', async () => {
  const rows = [product(1, 0), product(2, 0, 5, 1, 1, 'Arroz')];
  const afterFirst = [product(1, 1, 5, 1, 2), rows[1]];
  const afterSecond = [afterFirst[0], product(2, 2, 5, 1, 2, 'Arroz')];
  const { context, element, document, requests } = domHarness(
    [snapshot(rows), snapshot(afterFirst), snapshot(afterSecond)],
    [{ ok: true, json: async () => ({ registro: { version: 2 } }) },
      { ok: true, json: async () => ({ registro: { version: 2 } }) }]);
  await vm.runInContext('ensureComprasLoaded()', context);
  const first = element('super-stock-1');
  const second = element('super-stock-2');
  const history = element('super-history-button-2');
  first.value = '1';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-1") }, 1)', context);
  await vm.runInContext('saveSuperStock(1)', context);
  assert.match(element('super-stock-status-1').innerHTML, /Guardado y verificado/);
  assert.equal(element('super-stock-1'), first);
  assert.match(element('supermercado-content').querySelectorAll('.super-item')[0].main.innerHTML, /Actual: 1 L/);

  first.focus();
  first.blur();
  vm.runInContext('handleSuperStockBlur(1)', context);
  second.focus();
  second.value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-2") }, 2)', context);
  assert.equal(element('super-stock-2'), second, 'blur limpio conserva el nodo de destino');
  assert.equal(second.value, '2');
  assert.equal(document.activeElement, second);
  await vm.runInContext('saveSuperStock(2)', context);
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[1].options.body).stock_actual, 2);
  assert.equal(element('super-stock-2'), second);
  assert.match(element('supermercado-content').querySelectorAll('.super-item')[1].main.innerHTML, /Actual: 2 L/);

  first.focus();
  first.blur();
  vm.runInContext('handleSuperStockBlur(1)', context);
  assert.equal(element('super-history-button-2'), history, 'blur limpio conserva el botón Historial');
  context.superRequest = async () => ({ historial: [], next_cursor: null, has_more: false });
  await vm.runInContext('showSuperHistory(2, null, document.getElementById("super-history-button-2"))', context);
  assert.equal(element('supermercado-history').open, true);
  assert.match(element('super-history-title').textContent, /Arroz/);
});

test('late GET updates row metadata and regroups articles without losing a long edit or caret', async () => {
  const pending = deferred();
  const categories = [{ id: 1, nombre: 'Lácteos', orden: 1 }, { id: 2, nombre: 'Almacén', orden: 2 }];
  const initial = [product(1, 0), product(2, 0, 5, 1, 1, 'Arroz')];
  const updated = [product(1, 4, 5, 2), initial[1]];
  const { context, element, document, requests, content } = domHarness([snapshot(initial, categories), pending.promise]);
  await vm.runInContext('ensureComprasLoaded()', context);
  const first = element('super-stock-1');
  const second = element('super-stock-2');
  const history = element('super-history-button-2');
  second.focus();
  second.value = '123456';
  second.selectionStart = 3;
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-2") }, 2)', context);
  const loading = vm.runInContext('ensureComprasLoaded(true)', context);
  pending.resolve(snapshot(updated, categories));
  await loading;
  assert.equal(element('super-stock-1'), first);
  assert.equal(element('super-stock-2'), second);
  assert.equal(element('super-history-button-2'), history);
  assert.equal(second.value, '123456');
  assert.equal(second.selectionStart, 3);
  assert.equal(document.activeElement, second);
  assert.match(content.querySelectorAll('.super-item').find(article => article.dataset.superProductId === '1').main.innerHTML, /Actual: 4 L/);
  assert.equal(content.querySelectorAll('.super-group').length, 2);
  assert.equal(content.querySelectorAll('.super-item').length, 2, 'la reagrupación no duplica productos');
  assert.equal(requests.length, 0, 'el GET tardío y la reagrupación no publican el borrador');
  vm.runInContext('clearTimeout(superStockDrafts.get(2).timer)', context);
});

test('verified list removes initial loading text and keeps keyed controls during category refresh', async () => {
  const categories = [{ id: 1, nombre: 'Lácteos', orden: 1 }, { id: 2, nombre: 'Almacén', orden: 2 }];
  const initial = [product(1, 1)];
  const moved = [product(1, 1, 5, 2, 2)];
  const { context, element, content, requests } = domHarness([snapshot(initial, categories), snapshot(moved, categories)]);
  assert.equal(content.childNodes.length, 1);
  assert.equal(content.childNodes[0].nodeType, 3);
  assert.equal(content.childNodes[0].textContent, 'Cargando…');
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const input = element('super-stock-1');
  assert.equal(content.childNodes.filter(node => node.nodeType === 3).length, 0);
  assert.equal(content.children.length, 1);
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(element('super-stock-1'), input);
  assert.equal(content.querySelectorAll('.super-group')[0].dataset.superCategoryId, '2');
  assert.equal(content.childNodes.filter(node => node.nodeType === 3).length, 0);
  assert.equal(requests.length, 0, 'GET y reagrupación no escriben stock');
});

test('failed initial GET text disappears after recovery and later category changes', async () => {
  const categories = [{ id: 1, nombre: 'Lácteos', orden: 1 }, { id: 2, nombre: 'Almacén', orden: 2 }];
  const { context, element, content, requests } = domHarness([
    new Error('API caída'), snapshot([product(1, 1)], categories),
    snapshot([product(1, 3, 5, 2, 2)], categories)]);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), false);
  assert.match(content.childNodes[0].textContent, /No se pudo cargar/);
  assert.equal(content.childNodes[0].nodeType, 3);
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  const input = element('super-stock-1');
  assert.equal(content.childNodes.filter(node => node.nodeType === 3).length, 0);
  assert.equal(content.children.length, 1);
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(element('super-stock-1'), input);
  assert.equal(input.value, '3');
  assert.equal(content.querySelectorAll('.super-group')[0].dataset.superCategoryId, '2');
  assert.equal(content.childNodes.filter(node => node.nodeType === 3).length, 0);
  assert.equal(requests.length, 0);
});

test('clean saved draft adopts external value and version without replacing focused input or writing on GET', async () => {
  const { context, element, document, requests } = domHarness(
    [snapshot([product(7, 1)]), snapshot([product(7, 2, 5, 1, 2)]),
      snapshot([product(7, 4, 5, 1, 3)]), snapshot([product(7, 5, 5, 1, 4)])],
    [{ ok: true, json: async () => ({ registro: { version: 2 } }) },
      { ok: true, json: async () => ({ registro: { version: 4 } }) }]);
  await vm.runInContext('ensureComprasLoaded()', context);
  const input = element('super-stock-7');
  input.value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(vm.runInContext('superStockDrafts.get(7).dirty', context), false);
  input.focus();
  assert.equal(await vm.runInContext('ensureComprasLoaded(true)', context), true);
  assert.equal(requests.length, 1);
  assert.equal(element('super-stock-7'), input);
  assert.equal(document.activeElement, input);
  assert.equal(input.value, '4');
  assert.equal(vm.runInContext('superStockDrafts.get(7).value', context), '4');
  assert.equal(vm.runInContext('superStockDrafts.get(7).version', context), 3);
  input.value = '5';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[1].options.body).expected_version, 3);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
});

test('deleted clean draft is removed while deleted dirty draft stays as a conflict', async () => {
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 1), product(8, 1, 5, 1, 1, 'Arroz')]),
    snapshot([product(8, 1, 5, 1, 1, 'Arroz')]), snapshot([])] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '1';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  element('super-stock-8').value = '3';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
  await vm.runInContext('ensureComprasLoaded(true)', context);
  assert.equal(vm.runInContext('superStockDrafts.has(7)', context), false);
  assert.equal(vm.runInContext('superStockDrafts.get(8).dirty', context), true);
  await vm.runInContext('ensureComprasLoaded(true)', context);
  assert.equal(vm.runInContext('superStockDrafts.get(8).conflict', context), true);
  assert.equal(vm.runInContext('superStockDrafts.get(8).timer', context), null);
  assert.match(element('supermercado-content').innerHTML, /Borrador conservado: 3/);
  assert.equal(requests.length, 0);
});

test('grouping preserves server order, search grouping, escaped names, zero desired and empty state', async () => {
  const name = '<script>un nombre larguísimo de producto & unidad</script>';
  const rows = [product(1, 0, 5, 1, 1, name), product(2, 3, 0, null, 1, 'Extra')];
  const { context, element } = harness({ reads: [snapshot(rows), snapshot([])] });
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const rendered = element('supermercado-content').innerHTML;
  assert.ok(rendered.indexOf('Lácteos') < rendered.indexOf('Sin categoría'));
  assert.match(rendered, /&lt;script&gt;/);
  assert.doesNotMatch(rendered, /<script>/);
  assert.match(rendered, /Deseado 0 · hay 3 L; excedente/);
  assert.match(rendered, /Vacío/);
  element('supermercado-search').value = 'extra';
  vm.runInContext('renderSupermercadoList()', context);
  assert.match(element('supermercado-content').innerHTML, /Sin categoría/);
  assert.doesNotMatch(element('supermercado-content').innerHTML, /Lácteos/);
  element('supermercado-search').value = '';
  await vm.runInContext('ensureComprasLoaded(true)', context);
  assert.match(element('supermercado-content').innerHTML, /No hay productos/);
  assert.match(css, /@media \(max-width: 440px\)/);
  assert.doesNotMatch(html, />Actualizar stock<|>Guardar stock</);
});

test('count charts and product coverage never add incompatible units', async () => {
  const rows = [product(1, 0, 2), { ...product(2, 1, 4), unidad: 'kg' }, { ...product(3, 6, 0, null), unidad: 'u' }];
  const { context, element } = harness({ reads: [snapshot(rows)] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const chart = element('supermercado-general-chart').innerHTML;
  assert.match(chart, /1 de 3 productos a comprar|2 de 3 productos a comprar/);
  assert.match(chart, /Cobertura promedio por producto/);
  assert.match(chart, /No se suman cantidades de distintas unidades/);
  assert.match(element('supermercado-content').innerHTML, /Faltan 2 L/);
  assert.match(element('supermercado-content').innerHTML, /Faltan 3 kg/);
  assert.match(element('supermercado-category-summary').innerHTML, /Sin categoría/);
});

test('history uses audit snapshots, older cursor, X/Escape close, focus return and ignores late requests', async () => {
  const first = deferred();
  const { context, element, document } = harness({ reads: [snapshot([product(7, 4)])] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const calls = [];
  context.superRequest = async (_method, path) => {
    calls.push(path);
    if (calls.length === 1) return first.promise;
    return { historial: [{ id: 1, fecha_utc: '2026-10-01T00:00:00Z', operacion: 'alta', antes: null,
      despues: { producto: 'Leche', unidad: 'L', stock_actual: '1', stock_deseado: '5' } }], next_cursor: null, has_more: false };
  };
  const origin = element('origin'); origin.focus();
  const pending = vm.runInContext('showSuperHistory(7, null, document.activeElement)', context);
  assert.equal(element('supermercado-history').open, true);
  element('super-history-x').click();
  assert.equal(element('supermercado-history').open, false);
  assert.equal(document.activeElement, origin);
  first.resolve({ historial: [{ id: 2, fecha_utc: '2026-10-02T00:00:00Z', operacion: 'stock', antes: null, despues: null }], next_cursor: null, has_more: false });
  await pending;
  assert.equal(element('super-history-events').innerHTML, '');
  await vm.runInContext('showSuperHistory(7, null, document.activeElement)', context);
  assert.match(element('super-history-events').innerHTML, /Alta/);
  assert.match(element('super-history-chart').innerHTML, /1 punto auditado/);
  assert.doesNotMatch(element('super-history-chart').innerHTML, /NaN/);
  element('supermercado-history').cancel({ preventDefault() {} });
  assert.equal(element('supermercado-history').open, false);
});

test('stock auto save coalesces an edit made during PATCH and verifies each reading before success', async () => {
  const first = deferred();
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 1)]), snapshot([product(7, 2, 5, 1, 2)]), snapshot([product(7, 3, 5, 1, 3)])],
    writes: [first.promise, { ok: true, json: async () => ({ registro: { version: 3 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const input = element('super-stock-7'); input.value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const saving = vm.runInContext('saveSuperStock(7)', context);
  input.value = '3';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  vm.runInContext('handleSuperStockBlur(7)', context);
  vm.runInContext('handleSuperStockKeydown({ key: "Enter", preventDefault() {}, target: document.getElementById("super-stock-7") }, 7)', context);
  assert.equal(requests.length, 1);
  first.resolve({ ok: true, json: async () => ({ registro: { version: 2 } }) });
  await saving;
  assert.equal(requests.length, 2);
  assert.deepEqual(requests.map(call => JSON.parse(call.options.body).expected_version), [1, 2]);
  assert.deepEqual(requests.map(call => JSON.parse(call.options.body).stock_actual), [2, 3]);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
});

test('two products serialize PATCH plus verifier while focus and poll wait', async () => {
  const getA = deferred(), getB = deferred();
  const reads = [snapshot([product(7, 1), product(8, 1, 5, 1, 1, 'Arroz')]), getA.promise, getB.promise];
  const { context, element, events, requests } = harness({ reads,
    writes: [{ ok: true, json: async () => ({ registro: { version: 2 } }) },
      { ok: true, json: async () => ({ registro: { version: 2 } }) }], withWindow: true });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const savingA = vm.runInContext('saveSuperStock(7)', context);
  await flushUntil(() => reads.length === 1);
  assert.doesNotMatch(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  element('super-stock-8').value = '4';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
  const savingB = vm.runInContext('saveSuperStock(8)', context);
  events.focus(); events.interval();
  assert.equal(requests.length, 1);
  assert.equal(reads.length, 1, 'focus y poll no empiezan otro GET durante el verificador');
  getA.resolve(snapshot([product(7, 2, 5, 1, 2), product(8, 1, 5, 1, 1, 'Arroz')]));
  await flushUntil(() => requests.length === 2 && reads.length === 0);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  assert.doesNotMatch(element('super-stock-status-8').innerHTML, /Conflicto/);
  getB.resolve(snapshot([product(7, 2, 5, 1, 2), product(8, 4, 5, 1, 2, 'Arroz')]));
  await savingA; await savingB;
  assert.deepEqual(requests.map(call => JSON.parse(call.options.body).expected_version), [1, 1]);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  assert.match(element('super-stock-status-8').innerHTML, /Guardado y verificado/);
  assert.equal(vm.runInContext('supermercadoData.productos.find(row => row.id === 8).stock_actual', context), 4);
});

test('editing one product during its verifier keeps latest input and caret through focus refresh', async () => {
  const getFirst = deferred(), getLast = deferred();
  const reads = [snapshot([product(7, 1)]), getFirst.promise, getLast.promise];
  const { context, element, document, events, requests } = harness({ reads,
    writes: [{ ok: true, json: async () => ({ registro: { version: 2 } }) },
      { ok: true, json: async () => ({ registro: { version: 3 } }) }], withWindow: true });
  await vm.runInContext('ensureComprasLoaded()', context);
  const input = element('super-stock-7'); input.value = '2'; input.selectionStart = 1; input.focus();
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const saving = vm.runInContext('saveSuperStock(7)', context);
  await flushUntil(() => reads.length === 1);
  input.value = '3'; input.selectionStart = 1;
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  events.focus();
  getFirst.resolve(snapshot([product(7, 2, 5, 1, 2)]));
  await flushUntil(() => requests.length === 2 && reads.length === 0);
  assert.equal(input.value, '3');
  assert.equal(input.selectionStart, 1);
  assert.equal(document.activeElement, input);
  assert.equal(JSON.parse(requests[1].options.body).expected_version, 2);
  getLast.resolve(snapshot([product(7, 3, 5, 1, 3)]));
  await saving;
  assert.equal(vm.runInContext('superStockDrafts.get(7).value', context), '3');
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
});

test('administrative submit during autosave is rejected without losing its form', async () => {
  const verifier = deferred();
  const reads = [snapshot([product(7, 1)]), verifier.promise];
  const { context, element, requests } = harness({ reads,
    writes: [{ ok: true, json: async () => ({ registro: { version: 2 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const form = element('supermercado-product-form');
  form.reportValidity = () => true;
  form.elements = { id: { value: '' }, producto: { value: 'Compra nueva' }, unidad: { value: 'u' },
    categoria_id: { value: '' }, stock_deseado: { value: '2' }, stock_actual: { value: '0' } };
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const saving = vm.runInContext('saveSuperStock(7)', context);
  await flushUntil(() => reads.length === 0);
  await form.submit({ preventDefault() {}, currentTarget: form });
  assert.equal(requests.length, 1, 'el POST administrativo no interfiere con el GET verificador');
  assert.equal(form.elements.producto.value, 'Compra nueva');
  assert.match(element('supermercado-status').textContent, /formulario conserva tus datos/);
  verifier.resolve(snapshot([product(7, 2, 5, 1, 2)]));
  await saving;
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
});

test('dirty draft survives a late GET; invalid input, offline and polling never write', async () => {
  const pending = deferred();
  const { context, element, document, events, requests } = harness({ reads: [snapshot([product(7, 1)]), pending.promise, snapshot([product(7, 1)])], withWindow: true });
  await vm.runInContext('ensureComprasLoaded()', context);
  const input = element('super-stock-7'); input.value = '';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  document.activeElement = input;
  const loading = vm.runInContext('ensureComprasLoaded(true)', context);
  pending.resolve(snapshot([product(7, 1)]));
  await loading;
  assert.equal(input.value, '');
  assert.equal(document.activeElement, input);
  assert.equal(requests.length, 0);
  assert.match(element('super-stock-status-7').innerHTML, /cantidad válida/);
  vm.runInContext('navigator.onLine = false', context);
  events.offline();
  events.interval();
  assert.equal(requests.length, 0);
  assert.match(element('supermercado-status').textContent, /Sin conexión/);
  vm.runInContext('navigator.onLine = true', context);
  events.online();
  await Promise.resolve();
  assert.equal(requests.length, 0);
});

test('snapshot gate rejects missing, unknown and duplicate category references before enabling writes', async () => {
  const base = snapshot([product(7, 1)]);
  const invalid = [
    ['producto sin categoria_id', data => { delete data.productos[0].categoria_id; }],
    ['resumen sin id', data => { delete data.resumen.categorias[0].id; }],
    ['producto con referencia desconocida', data => { data.productos[0].categoria_id = 99; }],
    ['resumen con referencia desconocida', data => { data.resumen.categorias[0].id = 99; }],
    ['categoría duplicada', data => { data.categorias.push({ ...data.categorias[0] }); }],
    ['resumen duplicado', data => { data.resumen.categorias.push({ ...data.resumen.categorias[0] }); }],
    ['cantidad corrupta', data => { data.productos[0].stock_actual = -1; }],
    ['conteo corrupto', data => { data.resumen.categorias[0].productos = -1; }],
  ];
  for (const [label, corrupt] of invalid) {
    const data = structuredClone(base);
    corrupt(data);
    const { context, requests } = harness({ reads: [data] });
    assert.equal(await vm.runInContext('ensureComprasLoaded()', context), false, label);
    assert.equal(vm.runInContext('supermercadoWriteAvailable', context), false, label);
    assert.equal(await vm.runInContext("superMutate('POST', '/api/supermercado/productos', {}, 'guardado')", context), false, label);
    assert.equal(requests.length, 0, label);
  }
});

test('snapshot gate rejects coherent but false product and summary calculations', async () => {
  const base = snapshot([product(7, 0), product(8, 2, 5, 1, 1, 'Arroz')]);
  const invalid = [
    ['faltante falso y resumen coherente', data => {
      data.productos[0].a_comprar = 0;
      data.resumen.global.a_reponer = 1;
      data.resumen.categorias[0].a_reponer = 1;
    }],
    ['estado falso y resumen coherente', data => {
      data.productos[0].estado = 'OK';
      for (const row of [data.resumen.global, data.resumen.categorias[0]]) {
        row.vacios = 0; row.ok = 1; row.reponer = 1;
        row.porcentaje_vacio = 0; row.porcentaje_lleno = 100;
      }
    }],
    ['porcentaje faltante falso', data => { data.productos[1].porcentaje_faltante = 20; }],
    ['conteos globales falsos', data => {
      data.resumen.global.a_reponer = 1;
    }],
    ['conteos de categoría falsos', data => {
      data.resumen.categorias[0].a_reponer = 1;
    }],
    ['porcentajes globales falsos', data => {
      data.resumen.global.porcentaje_vacio = 0;
      data.resumen.global.porcentaje_lleno = 100;
    }],
    ['porcentajes de categoría falsos', data => {
      data.resumen.categorias[0].porcentaje_vacio = 0;
      data.resumen.categorias[0].porcentaje_lleno = 100;
    }],
    ['categoría vacía falsa', data => {
      data.categorias.push({ id: 2, nombre: 'Almacén', orden: 3 });
      data.resumen.categorias.splice(1, 0, { id: 2, nombre: 'Almacén', orden: 3,
        ...counts([]), porcentaje_lleno: 100 });
    }],
    ['Sin categoría falsa', data => { data.resumen.categorias.at(-1).porcentaje_lleno = 100; }],
  ];
  for (const [label, corrupt] of invalid) {
    const data = structuredClone(base);
    corrupt(data);
    const { context, requests } = harness({ reads: [data] });
    assert.equal(await vm.runInContext('ensureComprasLoaded()', context), false, label);
    assert.equal(vm.runInContext('supermercadoWriteAvailable', context), false, label);
    assert.equal(requests.length, 0, label);
  }
});

test('snapshot gate accepts zero over zero and canonical fractional values across three products', async () => {
  const categories = [{ id: 1, nombre: 'Lácteos', orden: 2 }, { id: 2, nombre: 'Almacén', orden: 3 }];
  const zero = product(1, 0, 0);
  const decimal = { ...product(2, 0.1, 0.3), a_comprar: 0.2,
    porcentaje_faltante: 66.66666666666667 };
  const fraction = { ...product(3, 0.666667, 1, null), a_comprar: 0.333333,
    porcentaje_faltante: 33.3333 };
  const data = snapshot([zero, decimal, fraction], categories);
  const { context, element, requests } = harness({ reads: [data] });
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  assert.equal(vm.runInContext('supermercadoWriteAvailable', context), true);
  assert.match(element('supermercado-summary').textContent, /3 productos · 2 a comprar · 1 vacíos/);
  assert.equal(requests.length, 0);
});

test('network failure pauses queued drafts and a recovery read never autosaves them', async () => {
  const patchA = deferred();
  const reads = [snapshot([product(7, 1), product(8, 1, 5, 1, 1, 'Arroz')]),
    snapshot([product(7, 1), product(8, 1, 5, 1, 1, 'Arroz')])];
  const { context, element, requests } = harness({ reads,
    writes: [patchA.promise, { ok: true, json: async () => ({ registro: { version: 2 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const saving = vm.runInContext('saveSuperStock(7)', context);
  element('super-stock-8').value = '4';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
  vm.runInContext('saveSuperStock(8)', context);
  patchA.resolve({ ok: false, status: 503, json: async () => ({ error: 'Red caída' }) });
  await saving;
  assert.equal(requests.length, 1);
  assert.match(element('super-stock-status-7').innerHTML, /Red caída.*Reintentar/);
  assert.match(element('super-stock-status-8').innerHTML, /Guardado pausado.*Reintentar/);
  await vm.runInContext('ensureComprasLoaded(true)', context);
  assert.equal(requests.length, 1);
  assert.equal(vm.runInContext('superStockDrafts.get(8).value', context), '4');
  element('super-stock-8').value = '5';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
  vm.runInContext('handleSuperStockBlur(8)', context);
  assert.equal(requests.length, 1, 'editar un borrador pausado no reintenta sin decisión explícita');
  assert.match(element('super-stock-status-8').innerHTML, /Reintentá/);
});

for (const [status, label] of [[401, 'Sesión vencida'], [409, 'Producto modificado']]) {
  test(`${status} pauses the module queue without retrying another product on refresh`, async () => {
    const patchA = deferred();
    const current = snapshot([product(7, 4, 5, 1, 2), product(8, 1, 5, 1, 1, 'Arroz')]);
    const reads = [snapshot([product(7, 1), product(8, 1, 5, 1, 1, 'Arroz')]), current, current];
    const { context, element, requests } = harness({ reads, writes: [patchA.promise] });
    await vm.runInContext('ensureComprasLoaded()', context);
    element('super-stock-7').value = '2';
    vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
    const saving = vm.runInContext('saveSuperStock(7)', context);
    element('super-stock-8').value = '3';
    vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
    vm.runInContext('saveSuperStock(8)', context);
    patchA.resolve({ ok: false, status, json: async () => ({ error: label }) });
    await saving;
    assert.equal(requests.length, 1);
    assert.match(element('super-stock-status-8').innerHTML, /Guardado pausado.*Reintentar/);
    if (status === 409) assert.match(element('super-stock-status-7').innerHTML, /Conflicto: servidor 4 L/);
    else assert.equal(vm.runInContext('supermercadoWriteAvailable', context), false);
    await vm.runInContext('ensureComprasLoaded(true)', context);
    assert.equal(requests.length, 1);
    assert.equal(vm.runInContext('superStockDrafts.get(8).value', context), '3');
  });
}

test('a later external stock change is reported after our accepted PATCH without rebasing the draft', async () => {
  const verifier = deferred();
  const reads = [snapshot([product(7, 1)]), verifier.promise];
  const { context, element, requests } = harness({ reads,
    writes: [{ ok: true, json: async () => ({ registro: { version: 2 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  const saving = vm.runInContext('saveSuperStock(7)', context);
  await flushUntil(() => reads.length === 0);
  verifier.resolve(snapshot([product(7, 4, 5, 1, 3)]));
  await saving;
  assert.equal(requests.length, 1);
  assert.match(element('super-stock-status-7').innerHTML, /servidor aceptó tu guardado, pero el stock cambió después/);
  assert.match(element('super-stock-status-7').innerHTML, /servidor 4 L.*borrador: 2/);
  assert.equal(vm.runInContext('superStockDrafts.get(7).version', context), 1);
});

test('409 preserves draft and requires explicit reattempt with refreshed version', async () => {
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 1)]), snapshot([product(7, 4, 5, 1, 2)]), snapshot([product(7, 3, 5, 1, 3)])],
    writes: [{ ok: false, status: 409, json: async () => ({ error: 'Producto modificado' }) },
      { ok: true, json: async () => ({ registro: { version: 3 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '3';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(requests.length, 1);
  assert.match(element('super-stock-status-7').innerHTML, /Conflicto: servidor 4 L.*borrador: 3/);
  await vm.runInContext('ensureComprasLoaded()', context);
  assert.equal(requests.length, 1);
  vm.runInContext('retrySuperStock(7)', context);
  for (let step = 0; step < 12 && requests.length < 2; step++) await Promise.resolve();
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[1].options.body).expected_version, 2);
});

test('stock authorization failure keeps the draft and recovery GET does not publish it', async () => {
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 1)]), snapshot([product(7, 1)])],
    writes: [{ ok: false, status: 401, json: async () => ({ error: 'Sesión vencida' }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(vm.runInContext('supermercadoWriteAvailable', context), false);
  assert.match(element('super-stock-status-7').innerHTML, /Sesión vencida/);
  await vm.runInContext('ensureComprasLoaded(true)', context);
  assert.equal(requests.length, 1, 'a recovery read must not issue another PATCH');
  assert.equal(vm.runInContext('superStockDrafts.get(7).value', context), '2');
});

test('history chart excludes missing audit quantities and product switches invalidate old response', async () => {
  const stale = deferred();
  const { context, element } = harness({ reads: [snapshot([product(7, 1), product(8, 2, 5, 1, 1, 'Arroz')])] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const audit = [
    { id: 1, fecha_utc: '2026-10-01T00:00:00Z', operacion: 'alta', antes: null, despues: { unidad: 'L', stock_actual: null, stock_deseado: 5 } },
    { id: 2, fecha_utc: '2026-10-02T00:00:00Z', operacion: 'stock', antes: { stock_actual: 1, stock_deseado: 5 }, despues: { unidad: 'L', stock_actual: 2, stock_deseado: 5 } },
  ];
  const chart = vm.runInContext(`superHistoryChart(${JSON.stringify(audit)}, 'L')`, context);
  assert.match(chart, /1 punto auditado/);
  assert.doesNotMatch(chart, /NaN|2 puntos auditados/);
  let call = 0;
  context.superRequest = async () => ++call === 1 ? stale.promise : { historial: [audit[1]], next_cursor: null, has_more: false };
  const old = vm.runInContext('showSuperHistory(7, null, document.getElementById("first"))', context);
  await vm.runInContext('showSuperHistory(8, null, document.getElementById("second"))', context);
  stale.resolve({ historial: [audit[0]], next_cursor: null, has_more: false });
  await old;
  assert.match(element('super-history-title').textContent, /Historial de Arroz/);
  assert.doesNotMatch(element('super-history-events').innerHTML, /Alta/);
});

test('history appends real older pages in date and id order', async () => {
  const { context, element } = harness({ reads: [snapshot([product(7, 2)])] });
  await vm.runInContext('ensureComprasLoaded()', context);
  const audit = (id, stock) => ({ id, fecha_utc: `2026-10-0${id}T00:00:00Z`, operacion: 'stock',
    antes: { producto: 'Leche', unidad: 'L', stock_actual: stock - 1, stock_deseado: 5 },
    despues: { producto: 'Leche', unidad: 'L', stock_actual: stock, stock_deseado: 5 } });
  const paths = [];
  context.superRequest = async (_method, path) => {
    paths.push(path);
    return paths.length === 1 ? { historial: [audit(3, 3), audit(2, 2)], next_cursor: 2, has_more: true }
      : { historial: [audit(1, 1)], next_cursor: null, has_more: false };
  };
  await vm.runInContext('showSuperHistory(7, null, document.getElementById("origin"))', context);
  assert.equal(element('supermercado-history-next').hidden, false);
  element('supermercado-history-next').click();
  for (let step = 0; step < 8 && element('supermercado-history-next').hidden === false; step++) await Promise.resolve();
  assert.equal(paths[1], '/api/supermercado/productos/7/historial?cursor=2');
  assert.equal(element('supermercado-history-next').hidden, true);
  assert.match(element('super-history-chart').innerHTML, /3 puntos auditados/);
  const events = element('super-history-events').innerHTML;
  assert.ok(events.indexOf('2026-10-03') < events.indexOf('2026-10-01'));
});

test('editing stock to its existing value does not create an audit PATCH', async () => {
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 2)])] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(requests.length, 0);
  assert.equal(vm.runInContext('superStockDrafts.get(7).dirty', context), false);
});

test('network error is row scoped, retryable and never announces success early', async () => {
  const failed = { ok: false, status: 503, json: async () => ({ error: 'Red caída' }) };
  const { context, element, requests } = harness({ reads: [snapshot([product(7, 1)]), snapshot([product(7, 2, 5, 1, 2)])],
    writes: [failed, { ok: true, json: async () => ({ registro: { version: 2 } }) }] });
  await vm.runInContext('ensureComprasLoaded()', context);
  element('super-stock-7').value = '2';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(requests.length, 1);
  assert.match(element('super-stock-status-7').innerHTML, /Red caída.*Reintentar/);
  assert.doesNotMatch(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  vm.runInContext('retrySuperStock(7)', context);
  for (let step = 0; step < 12 && !/Guardado y verificado/.test(element('super-stock-status-7').innerHTML); step++) await Promise.resolve();
  assert.equal(requests.length, 2);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
});

test('history quantities keep their audited unit when a product changes unit', () => {
  const { context, element } = harness();
  vm.runInContext(`supermercadoData = ${JSON.stringify(snapshot([product(7, 2)]))}; superHistoryProductId = 7; superHistoryRows = [{ id: 2, fecha_utc: '2026-10-02', operacion: 'edicion', antes: { producto: 'Leche', unidad: 'kg', stock_actual: 2, stock_deseado: 4, categoria_id: 1 }, despues: { producto: 'Leche', unidad: 'L', stock_actual: 3, stock_deseado: 5, categoria_id: null } }]`, context);
  vm.runInContext('renderSuperHistory()', context);
  const events = element('super-history-events').innerHTML;
  assert.match(events, /2 kg/);
  assert.match(events, /3 L/);
  assert.match(events, /Unidad: kg → L/);
  assert.match(events, /Categoría: Categoría #1 \(nombre actual: Lácteos; nombre histórico no registrado\) → Sin categoría/);
  assert.match(element('super-history-chart').innerHTML, /1 punto auditado con unidad L/);
});

test('renamed and deleted category audits show references without inventing historical names', () => {
  const { context, element } = harness();
  const data = snapshot([product(7, 2)], [{ id: 1, nombre: 'Nombre nuevo', orden: 2 }]);
  vm.runInContext(`supermercadoData = ${JSON.stringify(data)}; superHistoryProductId = 7; superHistoryRows = [
    { id: 3, fecha_utc: '2026-10-03', operacion: 'categoria_baja', antes: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: 99 }, despues: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: null } },
    { id: 2, fecha_utc: '2026-10-02', operacion: 'edicion', antes: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: 1 }, despues: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: 99 } },
    { id: 1, fecha_utc: '2026-10-01', operacion: 'edicion', antes: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: 1, categoria_nombre: 'Nombre registrado' }, despues: { producto: 'Leche', unidad: 'L', stock_actual: 2, stock_deseado: 5, categoria_id: null } }
  ]`, context);
  vm.runInContext('renderSuperHistory()', context);
  const events = element('super-history-events').innerHTML;
  assert.match(events, /Categoría #1 \(nombre actual: Nombre nuevo; nombre histórico no registrado\)/);
  assert.match(events, /Categoría #99 \(no disponible hoy; nombre histórico no registrado\)/);
  assert.match(events, /Categoría #1 \(Nombre registrado; nombre registrado en auditoría\)/);
  assert.doesNotMatch(events, /Categoría: Nombre nuevo →/);
});
