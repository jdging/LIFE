import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const script = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const source = script.slice(script.indexOf('let supermercadoData = null;'), script.indexOf('// ── VISTA RECETAS'));
const counts = rows => {
  const empty = rows.filter(row => row.estado === 'Vacío').length;
  return { productos: rows.length, a_reponer: rows.filter(row => row.a_comprar > 0).length,
    vacios: empty, reponer: rows.filter(row => row.estado === 'Reponer').length,
    ok: rows.filter(row => row.estado === 'OK').length,
    porcentaje_vacio: rows.length ? 100 * empty / rows.length : 0,
    porcentaje_lleno: rows.length ? 100 * (rows.length - empty) / rows.length : 0 };
};
const product = (id, actual, desired = 5, version = 1) => ({ id, categoria_id: null, categoria: null,
  producto: `Producto ${id}`, unidad: 'kg', stock_actual: actual, stock_deseado: desired,
  a_comprar: Math.max(0, desired - actual), porcentaje_faltante: desired ? Math.max(0, desired - actual) / desired * 100 : 0,
  estado: actual <= 0 ? 'Vacío' : actual < desired ? 'Reponer' : 'OK', version });
const snapshot = rows => ({ categorias: [], productos: rows,
  resumen: { global: counts(rows), categorias: [{ id: null, nombre: 'Sin categoría', orden: null, ...counts(rows) }] } });
const escapeHtml = value => String(value ?? '—').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

function harness(reads, form = null, response = null) {
  const elements = new Map();
  const element = id => {
    if (id === 'supermercado-product-form' && form) return form;
    if (!elements.has(id)) elements.set(id, { id, value: '', innerHTML: '', textContent: '', disabled: false,
      classList: { toggle() {} }, dataset: {}, addEventListener() {}, focus() {}, blur() {} });
    return elements.get(id);
  };
  const writes = [];
  const document = { getElementById: element, querySelectorAll: () => [] };
  const context = vm.createContext({ document, navigator: { onLine: true }, Intl, Number, Error, escapeHtml,
    setTimeout: () => 1, clearTimeout: () => {},
    fetchJSON: async () => reads.shift(),
    fetch: async (path, options) => {
      writes.push({ path, options });
      return response || { ok: true, json: async () => ({ registro: { version: 2 } }) };
    } });
  vm.runInContext(source, context);
  return { context, element, writes };
}

test('las acciones reales suman y restan una unidad sin alterar la fracción ni superar límites', () => {
  const { context } = harness([]);
  const step = (raw, direction) => vm.runInContext(`stepSuperStock(${JSON.stringify(raw)}, ${direction})`, context);
  for (const [raw, direction, expected] of [
    ['0', 1, '1'], ['1', 1, '2'], ['2', -1, '1'], ['0.5', 1, '1.5'],
    ['1.5', 1, '2.5'], ['2.5', -1, '1.5'], ['1.25', 1, '2.25'],
    ['2.25', -1, '1.25'], ['1.000001', 1, '2.000001'],
    ['0', -1, null], ['0.5', -1, null], ['1000000000', 1, null],
    ['999999999.5', 1, null], ['1000000000', -1, '999999999'],
    ['', 1, null], ['1.', 1, null], ['hola', -1, null], ['1.1234567', 1, null],
  ]) assert.equal(step(raw, direction), expected, `${raw} + ${direction}`);
});

test('flechas, botones y edición manual usan el mismo borrador; inválidos no generan PATCH', async () => {
  const { context, element, writes } = harness([snapshot([product(7, 0.5)]), snapshot([product(7, 1.5, 5, 2)])]);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  const input = element('super-stock-7');
  input.value = '0.5';
  // Both paths call the real input handler and preserve the fractional part.
  vm.runInContext("handleSuperStockKeydown({ key: 'ArrowUp', preventDefault() {}, target: document.getElementById('super-stock-7') }, 7)", context);
  assert.equal(input.value, '1.5');
  assert.equal(vm.runInContext('superStockDrafts.get(7).value', context), '1.5');
  vm.runInContext('handleSuperStockStep(7, 1)', context);
  assert.equal(input.value, '2.5');
  vm.runInContext("handleSuperStockKeydown({ key: 'ArrowDown', preventDefault() {}, target: document.getElementById('super-stock-7') }, 7)", context);
  assert.equal(input.value, '1.5');
  assert.equal(writes.length, 0);
  await vm.runInContext('saveSuperStock(7)', context);
  assert.equal(JSON.parse(writes[0].options.body).stock_actual, 1.5);
  assert.equal(vm.runInContext('supermercadoData.productos[0].stock_actual', context), 1.5);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  input.value = '';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  vm.runInContext('handleSuperStockStep(7, 1)', context);
  assert.equal(input.value, '');
  assert.equal(await vm.runInContext('saveSuperStock(7)', context), false);
  assert.equal(writes.length, 1);
  assert.match(element('super-stock-status-7').innerHTML, /cantidad válida/);
});

test('en cero, máximo y entrada vacía las acciones no crean borrador ni auditoría', async () => {
  const { context, element, writes } = harness([snapshot([product(7, 0), product(8, 1000000000, 1000000000)])]);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  element('super-stock-7').value = '0';
  element('super-stock-8').value = '1000000000';
  vm.runInContext('handleSuperStockStep(7, -1); handleSuperStockStep(8, 1)', context);
  vm.runInContext("handleSuperStockKeydown({ key: 'ArrowDown', preventDefault() {} }, 7)", context);
  assert.equal(element('super-stock-7').value, '0');
  assert.equal(element('super-stock-8').value, '1000000000');
  assert.equal(vm.runInContext('superStockDrafts.size', context), 0);
  element('super-stock-7').value = '';
  vm.runInContext('handleSuperStockStep(7, 1)', context);
  assert.equal(element('super-stock-7').value, '');
  assert.equal(vm.runInContext('superStockDrafts.size', context), 0);
  assert.equal(writes.length, 0);
});

test('dos fracciones escritas a mano se autoguardan en orden con GET verificador', async () => {
  const { context, element, writes } = harness([
    snapshot([product(7, 0), product(8, 0)]),
    snapshot([product(7, 0.5, 5, 2), product(8, 0)]),
    snapshot([product(7, 0.5, 5, 2), product(8, 1.25, 5, 2)]),
  ]);
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  element('super-stock-7').value = '0.5';
  element('super-stock-8').value = '1.25';
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-7") }, 7)', context);
  vm.runInContext('handleSuperStockInput({ target: document.getElementById("super-stock-8") }, 8)', context);
  const first = vm.runInContext('saveSuperStock(7)', context);
  const second = vm.runInContext('saveSuperStock(8)', context);
  await Promise.all([first, second]);
  assert.deepEqual(writes.map(write => JSON.parse(write.options.body).stock_actual), [0.5, 1.25]);
  assert.equal(vm.runInContext('supermercadoData.productos[0].stock_actual', context), 0.5);
  assert.equal(vm.runInContext('supermercadoData.productos[1].stock_actual', context), 1.25);
  assert.match(element('super-stock-status-7').innerHTML, /Guardado y verificado/);
  assert.match(element('super-stock-status-8').innerHTML, /Guardado y verificado/);
});

test('el formulario configura ambos stocks con step any y conserva decimales en el POST', async () => {
  const listeners = new Map();
  const numberInput = value => ({ value, step: '0.000001', disabled: false,
    addEventListener(type, listener) { this[type] = listener; }, closest() { return null; } });
  const form = { elements: { id: { value: '' }, producto: { value: 'Arroz' }, unidad: { value: 'kg' },
    categoria_id: { value: '' }, stock_deseado: numberInput('0.5'), stock_actual: numberInput('1.25') },
    dataset: {}, addEventListener(type, listener) { listeners.set(type, listener); },
    reportValidity() { return this.elements.stock_deseado.step === 'any' && this.elements.stock_actual.step === 'any'; },
    reset() {} };
  const { context, writes } = harness([snapshot([]), snapshot([])], form,
    { ok: true, json: async () => ({ registro: { id: 7, version: 1 } }) });
  assert.equal(form.elements.stock_deseado.step, 'any');
  assert.equal(form.elements.stock_actual.step, 'any');
  assert.equal(await vm.runInContext('ensureComprasLoaded()', context), true);
  let prevented = false;
  form.elements.stock_deseado.keydown({ key: 'ArrowUp', preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(form.elements.stock_deseado.value, '1.5');
  vm.runInContext("handleSuperFormStockStep(document.getElementById('supermercado-product-form').elements.stock_deseado, -1)", context);
  assert.equal(form.elements.stock_deseado.value, '0.5');
  await listeners.get('submit')({ preventDefault() {}, currentTarget: form });
  assert.equal(writes.length, 1);
  assert.equal(writes[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(writes[0].options.body), {
    producto: 'Arroz', unidad: 'kg', categoria_id: null, stock_deseado: 0.5, stock_actual: 1.25,
  });
  form.elements.stock_deseado.value = '1.1234567';
  await listeners.get('submit')({ preventDefault() {}, currentTarget: form });
  assert.equal(writes.length, 1, 'una cantidad fuera de precisión no genera otra escritura');
});
