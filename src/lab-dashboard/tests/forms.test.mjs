import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Todos los registros de este archivo son SINTÉTICOS. No se llama a una API real.
const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
assert.doesNotMatch(source, /\.tarjeta_id\b|\['tarjeta_id'\]/,
  'El dashboard no debe leer la identificación histórica de tarjeta');
const cssSource = readFileSync(new URL('../style.css', import.meta.url), 'utf8');
const summaryFixture = JSON.parse(readFileSync(new URL('./fixtures/api-summary-synthetic.json', import.meta.url), 'utf8'));
const categoriesGastoFixture = JSON.parse(readFileSync(new URL('./fixtures/categories-gasto.json', import.meta.url), 'utf8'));

// Card total gastos (t_ce790609 #1): no hay navegador en Node, así que se verifica
// que la regla CSS exista (clamp fluido + wrap en vez de recorte/scroll). El
// coordinador confirma visualmente en Chromium a 375px y desktop.
const cardValueRule = cssSource.slice(cssSource.indexOf('.card .value {'), cssSource.indexOf('.card .value.muted {'));
assert.match(cardValueRule, /font-size:\s*clamp\(/, 'El monto del card debe usar un tamaño de fuente fluido (clamp)');
assert.match(cardValueRule, /overflow-wrap:\s*anywhere/, 'Debe poder partir un monto muy largo en vez de desbordar la card');
const cardValueMutedRule = cssSource.slice(cssSource.indexOf('.card .value.muted {'), cssSource.indexOf('.card .value-sub {'));
assert.match(cardValueMutedRule, /font-size:\s*clamp\(/, 'El valor "muted" (ej. proporción) también debe ser fluido');
console.log('CSS: regla clamp + overflow-wrap de .card .value verificada (revisión visual pendiente en Chromium)');
const slice = (from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `No se encontró el bloque ${from}`);
  return source.slice(start, end);
};
const calls = [];
const replies = new Map();
const reply = (path, status, body) => {
  const queue = replies.get(path) || [];
  queue.push({ status, body });
  replies.set(path, queue);
};
const fetch = async (path, options = {}) => {
  calls.push({ path, options });
  const next = replies.get(path)?.shift();
  if (!next) throw new Error(`Mock sin respuesta: ${path}`);
  if (next.status === 0) throw new Error('Sin red en prueba sintética');
  return { ok: next.status >= 200 && next.status < 300, status: next.status,
    json: async () => next.body };
};
const elements = new Map();
const element = (id) => {
  if (!elements.has(id)) elements.set(id, { textContent: '', value: '', hidden: false,
    classList: { toggle() {}, add() {}, remove() {} }, appendChild() {}, addEventListener() {},
    focus() { document.activeElement = this; } });
  return elements.get(id);
};
const document = {
  getElementById: element,
  querySelector: () => element('fijos-snapshot'),
  querySelectorAll: () => [],
  createElement: () => ({ addEventListener() {} }),
  activeElement: null,
};
const prelude = `
const P1 = 'JD', P2 = 'Pinki';
const DATA = { gastos: [], ingresos: [], fijos: [], resumen: [], loadErrors: {}, deudaPendiente: null };
let liveMode = false, authState = 'unknown', writePending = false, reloadPending = false, reloadFailed = false;
let period = null, currentView = 'gastos', snapshotCount = 0, renderCount = 0;
function renderView() { renderCount++; }
async function loadSnapshot() { snapshotCount++; liveMode = false; updateAvailability(); }
function thisMonth() { return '2026-10'; }
function switchView() { renderCount++; }
function fmtARS(value) { return '$' + value; }
function fmtARSExact(value) { return '$' + Number(value).toFixed(2); }
function cuotaLabel(row) { return row.cuota_nro + '/' + row.cuotas_total; }
function sum(rows, field) { return rows.reduce((acc, r) => acc + (parseFloat(r[field]) || 0), 0); }
`;
// computePeriod, monthsWithData, mesLabel y los filtros de período son las
// funciones REALES de app.js (no copias): loadLive() las llama de verdad al
// armar el selector de meses y el panel, así que si faltan en el VM, un
// ReferenceError real se traga el try/catch de loadAll() y el test lee un
// falso "quedó en snapshot" en vez de ver la causa.
const api = runInNewContext(`${prelude}
${slice('const MESES_LARGO = ', 'const MESES_CORTO = ')}
${slice('const INVENTARIO_ESTADOS = ', 'const iconFor = ')}
${slice('const capitalize = ', 'const fmtARS = ')}
${slice('function todayLocalISO(', 'function shortMonth(')}
${slice('async function fetchJSON(', 'async function loadSnapshot(')}
${slice('async function loadAll(', '// ── NAVEGACIÓN')}
${slice('function computePeriod(', 'function selectPeriodType(')}
${slice('function getMonthProportion(', '// ── ESTADO')}
${slice('function getRowPct(', '// ── FILTROS DE DATOS')}
${slice('function filterGastosPeriod(', 'function fijosLastDay(')}
${slice('function fijosLastDay(', 'function gastosTotalState(')}
${slice('function fixedAllocation(', 'function computeFixedForPersona(')}
${slice('function fijosRepartoLabel(', 'function setFijosMode(')}
${slice('function validFixedPercent(', 'function showWriteNotice(')}
${slice('function showWriteNotice(', 'async function handleFormSubmit(')}
${slice('function renderDeudaCard(', 'function renderComposicion(')}
({ DATA, loadAll, loadLive, canonicalId, compareIds, collectForm, describeForm, routeForForm, writeForm,
   saveAndReload, handleRetryReload, fijosVersionVigente, fijosHistorial, fijosTramos, fijosEvolutionData, adaptSummary,
   adaptCurrentDebt, getRowPct, fixedAllocation, getMonthProportion, renderDeudaCard,
   computePeriod, monthsWithData, todayLocalISO, filterGastosPeriod, filterCuotasComprometidas,
   get state() { return { liveMode, authState, reloadFailed, snapshotCount, renderCount, period, inventoryAvailable }; } })`,
{ fetch, document, Date, Number, Math });

const expense = { id: 21, fecha: '2026-10-05T12:00:00', monto: 30, categoria: 'Comida',
  subcategoria: 'Almacén', medio_pago: 'Efectivo', pagado_por: 'JD',
  tipo_proporcion: 'custom', proporcion_jd: 0, proporcion_pinki: 100,
  cuota_nro: 2, cuotas_total: 3, descripcion_original: 'Prueba sintética' };
const income = { id: 31, fecha: '2026-10-03 12:00:00', monto: 900, persona: 'JD',
  categoria: 'Salario', descripcion_original: 'Prueba sintética' };
const fixed = { id: 41, fijo_grupo_id: 41, vigente_desde: '2026-10-01',
  nombre: 'Prueba sintética', monto_estimado: 100, monto_mensual: 100,
  periodicidad: 'mensual', responsable: 'Común', tipo_proporcion: 'dinamica',
  proporcion_jd: null, activo: 1 };
const summary = { ...summaryFixture, month: '2026-10' };
assert.equal(summaryFixture.proportion.JD, 100);
assert.equal(summaryFixture.proportion.Pinki, 0);
assert.equal(api.adaptSummary(summaryFixture).proporcion_pinki, 0);
assert.equal(api.adaptSummary(summaryFixture).debt_status, 'sin_deuda');
const liveReplies = (monthSummary = summary) => {
  reply('/api/expenses', 200, { expenses: [expense] });
  reply('/api/income', 200, { income: [income] });
  reply('/api/fixed/versions', 200, { versions: [fixed] });
  reply('/api/summary', 200, { months: [monthSummary] });
  reply('/api/summary?month=2026-10', 200, monthSummary);
};

reply('/api/health', 401, { error: 'sin sesión' });
await api.loadAll();
assert.equal(api.state.liveMode, false);
assert.equal(api.state.snapshotCount, 1);
assert.match(element('api-status').textContent, /solo lectura/);
assert.equal(calls.filter((call) => call.options.method && call.options.method !== 'GET').length, 0);

reply('/api/health', 503, { error: 'no disponible' });
await api.loadAll();
assert.equal(api.state.liveMode, false);
reply('/api/health', 0, null);
await api.loadAll();
assert.equal(api.state.liveMode, false);
reply('/api/health', 200, { ok: true, mode: 'snapshot', capabilities: [] });
await api.loadAll();
assert.equal(api.state.liveMode, false);

reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies();
await api.loadAll();
assert.equal(api.state.liveMode, true);

const maxId = '9223372036854775807';
const largeId = '9007199254740993';
assert.equal(api.canonicalId(21), '21');
assert.equal(api.canonicalId(9007199254740991), '9007199254740991');
assert.equal(api.canonicalId(largeId), largeId);
assert.equal(api.canonicalId(maxId), maxId);
assert.equal(api.compareIds('9007199254740992', largeId), -1);
for (const bad of [0, -1, '0', '01', '-1', '1.0', '1e3', '9223372036854775808',
  9007199254740992, 9223372036854775807, true, 1n]) {
  assert.throws(() => api.canonicalId(bad), /ID inválido|inseguro/);
}
assert.equal(api.routeForForm('expense-delete', { id: largeId })[1], `/api/expenses/${encodeURIComponent(largeId)}`);
assert.equal(api.routeForForm('income-edit', { id: maxId })[1], `/api/income/${encodeURIComponent(maxId)}`);
assert.equal(api.routeForForm('fixed-edit', { id: largeId })[1], `/api/fixed/${encodeURIComponent(largeId)}`);
assert.throws(() => api.routeForForm('fixed-delete', { id: 9007199254740992 }), /inseguro/);
assert.deepEqual(Array.from(api.routeForForm('income-delete', { id: maxId })), ['DELETE', `/api/income/${encodeURIComponent(maxId)}`]);
assert.throws(() => api.routeForForm('income-delete', { id: 9007199254740992 }), /inseguro/);

// La baja de un ingreso de Salario avisa del impacto en la proporción; otras categorías no.
assert.match(api.describeForm('income-delete', income, null), /Salario.*proporción del mes y las deudas/);
assert.doesNotMatch(api.describeForm('income-delete', { ...income, categoria: 'Extra' }, null), /Salario/);

// Un número JSON fuera del rango seguro pierde precisión antes de llegar a JS: no habilitar escritura.
for (const field of ['expenses', 'income', 'versions', 'group']) {
  reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
  reply('/api/expenses', 200, { expenses: [{ ...expense, id: field === 'expenses' ? 9007199254740992 : largeId }] });
  reply('/api/income', 200, { income: [{ ...income, id: field === 'income' ? 9007199254740992 : maxId }] });
  reply('/api/fixed/versions', 200, { versions: [{ ...fixed,
    id: field === 'versions' ? 9007199254740992 : largeId,
    fijo_grupo_id: field === 'group' ? 9007199254740992 : largeId }] });
  reply('/api/summary', 200, { months: [summary] });
  reply('/api/summary?month=2026-10', 200, summary);
  const beforeInvalid = api.state.snapshotCount;
  await api.loadAll();
  assert.equal(api.state.liveMode, false, `${field}: live debe quedar cerrado`);
  assert.equal(api.state.snapshotCount, beforeInvalid + 1);
  assert.match(element('api-status').textContent, /solo lectura/);
}
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
reply('/api/expenses', 200, { expenses: [{ ...expense, id: largeId }] });
reply('/api/income', 200, { income: [{ ...income, id: maxId }] });
reply('/api/fixed/versions', 200, { versions: [{ ...fixed, id: maxId, fijo_grupo_id: largeId }] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
await api.loadAll();
assert.equal(api.state.liveMode, true);
assert.equal(api.DATA.gastos[0].id, largeId);
assert.equal(api.DATA.ingresos[0].id, maxId);
assert.equal(api.DATA.fijos[0].id, maxId);
assert.equal(api.DATA.fijos[0].fijo_grupo_id, largeId);
assert.equal(api.fijosHistorial(api.DATA.fijos, largeId)[0].id, maxId);
assert.equal(api.fijosTramos(api.DATA.fijos, '2026-10-01', '2026-10-31')[0].fijo_grupo_id, largeId);
const largeVersions = [{ ...fixed, id: '9007199254740992', fijo_grupo_id: largeId },
  { ...fixed, id: largeId, fijo_grupo_id: largeId }];
assert.equal(api.fijosVersionVigente(largeVersions, largeId, '2026-10-31').id, largeId);
assert.equal(api.fijosHistorial(largeVersions, largeId)[1].id, largeId);

// Restablecer la fixture corriente para las pruebas de formularios existentes.
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies();
await api.loadAll();
assert.equal(api.state.authState, 'authenticated');
assert.equal(api.DATA.gastos[0].id, '21');
assert.equal(api.DATA.gastos[0].fecha, '2026-10-05');
assert.equal(api.DATA.ingresos[0].id, '31');
assert.equal(api.DATA.ingresos[0].fecha, '2026-10-03');
assert.equal(api.DATA.fijos[0].id, '41');
assert.equal(api.DATA.resumen[0].proporcion_pinki, 0);
assert.equal(api.DATA.resumen[0].proporcion_jd, 100);
assert.equal(api.DATA.resumen[0].debt_status, 'sin_deuda');
assert.equal(api.DATA.deudaPendiente.monto, 0);
api.renderDeudaCard();
assert.equal(element('g-deuda').textContent, '$0');
assert.match(element('g-deuda-quien').textContent, /sin deuda pendiente/);
assert.equal(api.getRowPct({ fecha: '2026-10-05', tipo_proporcion: 'dinamico' }).pct2, 0);
assert.equal(api.fixedAllocation({ ...fixed, tipo_proporcion: 'dinamico' }, '2026-10').pct1, 100);
assert.throws(() => api.adaptSummary({ ...summary, proportion: {} }), /proporción/);
assert.throws(() => api.adaptSummary({ ...summary, proportion: { JD: 60, Pinki: 60 } }), /proporción/);
assert.throws(() => api.adaptSummary({ ...summary, debt_pending_through_month: {} }), /deuda/);
const owing = { deudor: 'Pinki', acreedor: 'JD', monto: 25 };
assert.equal(api.adaptSummary({ ...summary, debt_pending_through_month: owing }).debt_pending_through_month.monto, 25);
assert.equal(api.state.period.refMonth, '2026-10');
assert.equal(calls.filter((call) => call.path.startsWith('/api/')).every((call) => call.options.credentials === 'same-origin'), true);

const snapshotsBeforeInvalid = api.state.snapshotCount;
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies({ ...summary, proportion: { JD: 100, Pinki: 100 } });
await api.loadAll();
assert.equal(api.state.liveMode, false, 'Una proporción inválida no habilita live');
assert.equal(api.state.snapshotCount, snapshotsBeforeInvalid + 1);
assert.match(element('api-status').textContent, /solo lectura/);
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies();
await api.loadAll();
assert.equal(api.state.liveMode, true);

const expenseValues = { fecha: '2026-10-05', monto: '90.00', categoria: 'Comida',
  subcategoria: 'Almacén', descripcion_original: 'Prueba sintética', medio_pago: 'Efectivo',
  pagado_por: 'JD', tarjeta_id: '', tipo_proporcion: 'custom', proporcion_jd: '0',
  proporcion_pinki: '100', cuotas_total: '3' };
const collectedExpense = api.collectForm('expense', null, expenseValues);
assert.equal(Object.keys(collectedExpense.errors).length, 0);
assert.equal(collectedExpense.payload.proporcion_jd, 0);
assert.equal(collectedExpense.payload.cuotas_total, 3);
assert.equal('tarjeta_id' in collectedExpense.payload, false);
assert.ok(api.collectForm('expense', null, { ...expenseValues, monto: '1.001' }).errors.monto);
assert.ok(api.collectForm('expense', null, { ...expenseValues, cuotas_total: '121' }).errors.cuotas_total);
assert.ok(api.collectForm('expense', null, { ...expenseValues, proporcion_pinki: '99' }).errors.proporcion_jd);

// PATCH /api/expenses/:id (t_b5c6e680, punto 3): mismo formulario de alta,
// precargado, pero sin `cuotas_total` -- no es editable (ver db.py,
// GASTO_CAMPOS_EDITABLES). `expense` tiene tipo_proporcion='custom'; pasar a
// 'dinamico' en la edición debe limpiar proporcion_jd/proporcion_pinki a
// `null` explícito, porque el servidor valida la fila RESULTANTE (fila
// actual + estos cambios) y 'dinamico' no admite esos campos no nulos.
const expenseEditValues = { fecha: '2026-10-06', monto: '45.00', categoria: 'Hogar',
  subcategoria: 'Alquiler', descripcion_original: 'Alquiler editado', medio_pago: 'Transferencia',
  pagado_por: 'Común', tarjeta_id: '', tipo_proporcion: 'dinamico', proporcion_jd: '50', proporcion_pinki: '50' };
const collectedExpenseEdit = api.collectForm('expense-edit', expense, expenseEditValues);
assert.equal(Object.keys(collectedExpenseEdit.errors).length, 0);
assert.equal('cuotas_total' in collectedExpenseEdit.payload, false);
assert.equal('cuotas_total' in api.collectForm('expense-edit', expense,
  { ...expenseEditValues, cuotas_total: '5' }).payload, false, 'cuotas_total nunca viaja en el payload de edición, aunque el cliente lo mande');
assert.equal('tarjeta_id' in collectedExpenseEdit.payload, false);
assert.equal(collectedExpenseEdit.payload.proporcion_jd, null);
assert.equal(collectedExpenseEdit.payload.proporcion_pinki, null);

const customExpenseEditValues = { ...expenseEditValues, tipo_proporcion: 'custom', proporcion_jd: '20', proporcion_pinki: '80' };
const collectedCustomExpenseEdit = api.collectForm('expense-edit', expense, customExpenseEditValues);
assert.equal(Object.keys(collectedCustomExpenseEdit.errors).length, 0);
assert.equal(collectedCustomExpenseEdit.payload.proporcion_jd, 20);
assert.equal(collectedCustomExpenseEdit.payload.proporcion_pinki, 80);
assert.ok(api.collectForm('expense-edit', expense, { ...expenseEditValues, monto: '1.001' }).errors.monto);
assert.ok(api.collectForm('expense-edit', expense, { ...expenseEditValues, categoria: '' }).errors.categoria);

assert.deepEqual(Array.from(api.routeForForm('expense-edit', { id: expense.id })), ['PATCH', `/api/expenses/${expense.id}`]);
assert.equal(api.routeForForm('expense-edit', { id: maxId })[1], `/api/expenses/${encodeURIComponent(maxId)}`);
assert.match(api.describeForm('expense-edit', expense, collectedExpenseEdit.payload), /Editar gasto #21/);
assert.match(api.describeForm('expense-edit', expense, collectedExpenseEdit.payload), /no cambian/);

const incomeValues = { fecha: '2026-10-03', monto: '900', persona: 'JD',
  categoria: 'Salario', descripcion_original: 'Prueba sintética' };
const collectedIncome = api.collectForm('income-edit', income, incomeValues);
assert.equal(Object.keys(collectedIncome.errors).length, 0);
assert.match(api.describeForm('income-edit', income, collectedIncome.payload), /proporciones/);
assert.match(api.describeForm('income-edit', { ...income, categoria: 'Extra' },
  { ...collectedIncome.payload, categoria: 'Salario' }), /proporciones/);
const fixedValues = { nombre: 'Prueba sintética nueva', monto_estimado: '120',
  periodicidad: 'mensual', responsable: 'Común', fixed_tipo_proporcion: 'dinamica',
  vigente_desde: '2026-10-15' };
assert.equal(Object.keys(api.collectForm('fixed', null, fixedValues).errors).length, 0);
const customFixed = { ...fixed, tipo_proporcion: 'custom', proporcion_jd: 0 };
const retainedCustom = api.collectForm('fixed-edit', customFixed,
  { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: '0' });
assert.equal(retainedCustom.payload.responsable, 'Común');
assert.equal('tipo_proporcion' in retainedCustom.payload, false);
assert.equal('proporcion_jd' in retainedCustom.payload, false);
assert.match(api.describeForm('fixed-edit', customFixed, retainedCustom.payload), /0% JD \/ 100% Pinki.*historial/);
const markupApi = runInNewContext(`
function todayLocalISO() { return '2026-10-17'; }
const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
${slice('function formField(', 'async function openForm(')}
({ formMarkup })`, { DATA: { gastos: [], fijos: [{ categoria: 'Hogar' }, { categoria: 'Servicios' }, { categoria: null }] } });
const fixedMarkup = markupApi.formMarkup('fixed-edit', customFixed);
assert.match(fixedMarkup, /id="field-responsable"/);
assert.match(fixedMarkup, /id="field-fixed_tipo_proporcion"/);
assert.match(fixedMarkup, /value="custom" selected/);
assert.match(fixedMarkup, /id="field-proporcion_jd"[^>]*value="0"/);
assert.match(fixedMarkup, /id="fixed-pinki-percent"/);
assert.doesNotMatch(fixedMarkup, /API.*no.*reparto/i);

// Categoría de fijo (brief F1 #5): campo libre con datalist de categorías ya
// usadas (sin catálogo cerrado), y precarga con la categoría de la fila.
assert.match(fixedMarkup, /id="field-categoria"/);
assert.match(fixedMarkup, /<option value="Hogar"><\/option>/);
assert.match(fixedMarkup, /<option value="Servicios"><\/option>/);
const fixedWithCategoriaRow = { ...customFixed, categoria: 'Servicios' };
assert.match(markupApi.formMarkup('fixed-edit', fixedWithCategoriaRow), /id="field-categoria"[^>]*value="Servicios"/);
const fixedAltaMarkup = markupApi.formMarkup('fixed', null);
assert.match(fixedAltaMarkup, /id="field-categoria"[^>]*value=""/, 'El alta no precarga ninguna categoría');

// Categoría/subcategoría de fijo con catálogo real (brief t_38a7253f F1b,
// hallazgo A): mismo patrón que el formulario de gasto -- <select> + <select>
// dependiente poblados desde /api/categories?tipo=Gasto -- pero OPCIONALES
// (sin `required`, a diferencia de gasto) y preservando un valor ya guardado
// que no esté en el catálogo, en vez de perderlo en silencio.
const fixedAltaConCatalogo = markupApi.formMarkup('fixed', null, categoriesGastoFixture.categories);
assert.match(fixedAltaConCatalogo, /<select id="field-categoria" name="categoria" aria-describedby/,
  'El select de categoría de fijo no debe ser obligatorio (a diferencia del de gasto)');
for (const entry of categoriesGastoFixture.categories) {
  assert.match(fixedAltaConCatalogo, new RegExp(`<option value="${entry.categoria}">${entry.categoria}</option>`));
}
assert.match(fixedAltaConCatalogo, /<option value="" selected>Sin categoría<\/option>/,
  'El alta sin fila no debe preseleccionar ninguna categoría del catálogo');

const fixedEditEnCatalogo = { ...customFixed, categoria: 'Hogar', subcategoria: 'Alquiler' };
const fixedEditConCatalogoHtml = markupApi.formMarkup('fixed-edit', fixedEditEnCatalogo, categoriesGastoFixture.categories);
assert.match(fixedEditConCatalogoHtml, /<option value="Hogar" selected>Hogar<\/option>/);
assert.match(fixedEditConCatalogoHtml, /<option value="Alquiler" selected>Alquiler<\/option>/);
assert.match(fixedEditConCatalogoHtml, /<option value="Comida">Comida<\/option>/, 'las demás categorías no deben quedar marcadas');

// Valor legacy fuera del catálogo: se conserva como opción extra, nunca se pierde.
const fixedEditFueraDeCatalogo = { ...customFixed, categoria: 'Categoría vieja', subcategoria: 'Sub vieja' };
const fixedEditFueraDeCatalogoHtml = markupApi.formMarkup('fixed-edit', fixedEditFueraDeCatalogo, categoriesGastoFixture.categories);
assert.match(fixedEditFueraDeCatalogoHtml, /<option value="Categoría vieja" selected>Categoría vieja<\/option>/,
  'Una categoría guardada que ya no está en el catálogo debe conservarse como opción extra');
assert.match(fixedEditFueraDeCatalogoHtml, /<option value="Sub vieja" selected>Sub vieja<\/option>/,
  'Una subcategoría guardada que ya no está en el catálogo debe conservarse como opción extra');

// formMarkup('expense-edit', ...): mismo formulario de alta, precargado con la
// fila, salvo cuotas_total (no editable por PATCH, ver GASTO_CAMPOS_EDITABLES).
const expenseMarkupApi = runInNewContext(`
function todayLocalISO() { return '2026-10-17'; }
function cuotaLabel(r) { return (r.cuotas_total > 1) ? r.cuota_nro + '/' + r.cuotas_total : '—'; }
const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
${slice('function formField(', 'async function openForm(')}
({ formMarkup })`, { DATA: { gastos: [] } });
const expenseEditMarkup = expenseMarkupApi.formMarkup('expense-edit', expense);
assert.doesNotMatch(expenseEditMarkup, /name="cuotas_total"/, 'cuotas_total no debe poder editarse desde este form');
assert.match(expenseEditMarkup, /cuota 2\/3/, 'debe avisar que la edición es solo de esta cuota');
assert.match(expenseEditMarkup, /id="field-monto"[^>]*value="30"/);
assert.match(expenseEditMarkup, /id="field-categoria"[^>]*value="Comida"/);
assert.match(expenseEditMarkup, /id="field-subcategoria"[^>]*value="Almacén"/);
assert.match(expenseEditMarkup, /id="field-descripcion_original"[^>]*value="Prueba sintética"/);
assert.match(expenseEditMarkup, /<option value="Efectivo" selected>/);
assert.match(expenseEditMarkup, /<option value="JD" selected>/);
assert.match(expenseEditMarkup, /<option value="custom" selected>/);
assert.match(expenseEditMarkup, /id="field-proporcion_jd"[^>]*value="0"/);
assert.match(expenseEditMarkup, /id="field-proporcion_pinki"[^>]*value="100"/);
// Edición de un gasto guardado como 'custom' 50/50 (brief fix4 #6): debe
// preseleccionar "Manual por porcentajes" con ambos campos en 50, igual
// que cualquier otro 'custom' -- el backend nunca persiste '50/50' literal
// (ver collectForm), así que no hay un valor "50/50" que reconstruir acá.
const expenseMitadMarkup = expenseMarkupApi.formMarkup('expense-edit',
  { ...expense, tipo_proporcion: 'custom', proporcion_jd: 50, proporcion_pinki: 50 });
assert.match(expenseMitadMarkup, /<option value="custom" selected>/);
assert.match(expenseMitadMarkup, /id="field-proporcion_jd"[^>]*value="50"/);
assert.match(expenseMitadMarkup, /id="field-proporcion_pinki"[^>]*value="50"/);
const expenseAltaMarkup = expenseMarkupApi.formMarkup('expense', null);
assert.match(expenseAltaMarkup, /name="cuotas_total"/, 'El alta sigue permitiendo elegir la cantidad de cuotas');
// Atajos de reparto "100% JD" / "100% Pinki" (brief F1 #6), junto a los
// atajos existentes (dinámico, 50/50, manual).
assert.match(expenseAltaMarkup, /<option value="jd_100"[^>]*>100% JD<\/option>/);
assert.match(expenseAltaMarkup, /<option value="pinki_100"[^>]*>100% Pinki<\/option>/);
// Con catálogo real (igual que en el alta, t_ce790609): el alta no debe
// cambiar su markup exacto al agregar precarga de edición a la misma
// función (sin selected, sin espacio extra antes de cerrar la etiqueta).
const expenseAltaConCatalogo = expenseMarkupApi.formMarkup('expense', null, categoriesGastoFixture.categories);
for (const entry of categoriesGastoFixture.categories) {
  assert.match(expenseAltaConCatalogo, new RegExp(`<option value="${entry.categoria}">${entry.categoria}</option>`),
    `El alta con catálogo no debe agregar "selected" a "${entry.categoria}" sin una fila`);
}
// Con catálogo real y una fila (expense-edit): categoría y subcategoría
// deben venir preseleccionadas desde el render inicial, sin pasar por
// onExpenseCategoriaChange() (que resetearía la subcategoría a '').
const expenseEditConCatalogo = expenseMarkupApi.formMarkup('expense-edit', expense, categoriesGastoFixture.categories);
assert.match(expenseEditConCatalogo, /<option value="Comida" selected>Comida<\/option>/);
assert.match(expenseEditConCatalogo, /<option value="Almacén" selected>Almacén<\/option>/);
assert.match(expenseEditConCatalogo, /<option value="Hogar">Hogar<\/option>/, 'las demás categorías no deben quedar marcadas');

const expenseTableApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
const P1 = 'JD', P2 = 'Pinki';
${slice('function getRowPct(', '// ── FILTROS DE DATOS')}
const TABLE_KEY_MAP = { monto_total: 'monto_propio', pago: 'pagado_por' };
let tableFiltroCat = '', sortState = { key: 'fecha', dir: 'desc' }, personaFiltro = 'comun';
let gastosTableRows = [{ ...expenseRow, id: bigId, categoria: '<img src=x onerror=alert(1)>',
  descripcion_original: '<svg onload=alert(2)>', monto_propio: expenseRow.monto }];
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
function iconFor() { return '🔸'; }
function fmtARS(value) { return '$' + value; }
function pillClassFor() { return 'pill-jd'; }
function cuotaLabel() { return '2/3'; }
${slice('function renderGastosTable()', "document.querySelectorAll('#tabla-gastos thead th[data-key]')")}
({ renderGastosTable })`, { document, expenseRow: expense, bigId: largeId, DATA: { resumen: [] } });
expenseTableApi.renderGastosTable();
const expenseTableHtml = element('tabla-body').innerHTML;
assert.match(expenseTableHtml, new RegExp(`data-id="${largeId}"`));
assert.match(expenseTableHtml, /openForm\('expense-edit', this\.dataset\.id\)/, 'la tabla de Gastos debe ofrecer un botón Editar por fila (t_b5c6e680)');
assert.match(expenseTableHtml, /openForm\('expense-delete', this\.dataset\.id\)/);
assert.doesNotMatch(expenseTableHtml, /<img/i);
assert.match(expenseTableHtml, /&lt;img/);
// Columna Descripción (BRIEF.md #4): visible, con data-label para la vista mobile, y escapada.
assert.match(expenseTableHtml, /data-label="Descripción"/);
// Columnas de reparto (brief F1 #4): proporción y monto que le corresponde a
// cada persona, calculados con el % propio del gasto (tipo_proporcion=custom,
// proporcion_jd=0 → 0% JD / 100% Pinki), no con el filtro de persona activo.
assert.match(expenseTableHtml, /data-label="Proporción"[^>]*>0% JD \/ 100% Pinki</);
assert.match(expenseTableHtml, /data-label="\$ JD"[^>]*>\$0</);
assert.match(expenseTableHtml, /data-label="\$ Pinki"[^>]*>\$30</);
assert.doesNotMatch(expenseTableHtml, /<svg/i, 'Un payload XSS en descripcion_original no debe crear un elemento');
assert.match(expenseTableHtml, /&lt;svg onload=alert\(2\)&gt;/, 'La descripción maliciosa debe llegar escapada al innerHTML');

// ── HALLAZGO B (QA Juan, t_38a7253f F1b): "Monto" de la tabla de detalle de
// gastos siempre muestra el TOTAL del gasto, nunca la porción recortada por
// un filtro de persona activo -- "$ JD"/"$ Pinki" ya muestran esa porción, y
// mostrarla también en "Monto" hacía parecer un error donde no lo había.
// Casos reales del QA: gasto 856 ($15.600, reparto custom 50/50) y 857
// ($7.000, reparto dinámico 69.4113/30.5887 de octubre 2026).
const montoColumnApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
const P1 = 'JD', P2 = 'Pinki';
${slice('function getMonthProportion(', 'function getDebtRows(')}
${slice('function getRowPct(', 'function setPersonaFiltro(')}
const TABLE_KEY_MAP = { monto_total: 'monto_propio', pago: 'pagado_por' };
let tableFiltroCat = '', sortState = { key: 'fecha', dir: 'desc' }, personaFiltro = 'comun';
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
let gastosTableRows = [];
function iconFor() { return '🔸'; }
function fmtARS(value) { return '$' + (Math.round(value * 100) / 100); }
function pillClassFor() { return 'pill-jd'; }
function cuotaLabel() { return '—'; }
${slice('function renderGastosTable()', "document.querySelectorAll('#tabla-gastos thead th[data-key]')")}
({ renderGastosTable,
   setFiltro(value) { personaFiltro = value; },
   setSort(key, dir) { sortState = { key, dir }; },
   buildRows(rows) {
     const personaFilteredRows = applyPersonaFiltro(rows);
     gastosTableRows = applyPersonaMonto(personaFilteredRows)
       .map((r, i) => ({ ...r, monto_propio: personaFilteredRows[i].monto }));
   } })`,
  { document, DATA: { resumen: [
    { mes: '2026-10', proporcion_jd: 69.4113, proporcion_pinki: 30.5887, total_ingresos: 100 },
  ] } });

const gasto856 = { id: 856, fecha: '2026-10-05', monto: 15600, categoria: 'Comida',
  descripcion_original: 'Super', medio_pago: 'Efectivo', pagado_por: 'JD',
  tipo_proporcion: 'custom', proporcion_jd: 50, proporcion_pinki: 50 };
const gasto857 = { id: 857, fecha: '2026-10-06', monto: 7000, categoria: 'Transporte',
  descripcion_original: 'Nafta', medio_pago: 'Efectivo', pagado_por: 'Pinki',
  tipo_proporcion: 'dinamico' };

const rowFor = (html, id) => (html.match(/<tr>[\s\S]*?<\/tr>/g) || [])
  .find((row) => row.includes(`data-id="${id}"`));
const cellFor = (rowHtml, label) => rowHtml.match(new RegExp(`data-label="${label}"[^>]*>([^<]*)<`))?.[1];

for (const filtro of ['jd_comun', 'comun']) {
  montoColumnApi.setFiltro(filtro);
  montoColumnApi.buildRows([gasto856, gasto857]);
  montoColumnApi.renderGastosTable();
  const html = element('tabla-body').innerHTML;
  const row856 = rowFor(html, 856);
  const row857 = rowFor(html, 857);
  assert.equal(cellFor(row856, 'Monto'), '$15600', `filtro=${filtro}: Monto de 856 debe ser el total, no la porción filtrada`);
  assert.equal(cellFor(row856, '\\$ JD'), '$7800');
  assert.equal(cellFor(row856, '\\$ Pinki'), '$7800');
  assert.equal(cellFor(row857, 'Monto'), '$7000', `filtro=${filtro}: Monto de 857 debe ser el total, no la porción filtrada`);
  assert.equal(cellFor(row857, '\\$ JD'), '$4858.79');
  assert.equal(cellFor(row857, '\\$ Pinki'), '$2141.21');
}

// Con filtro de persona activo, la columna de esa persona queda resaltada
// (clase CSS); con filtro 'comun' (sin una persona puntual) no se resalta ninguna.
montoColumnApi.setFiltro('jd_comun');
montoColumnApi.buildRows([gasto856, gasto857]);
montoColumnApi.renderGastosTable();
let htmlJd = element('tabla-body').innerHTML;
assert.match(rowFor(htmlJd, 856), /data-label="\$ JD" class="td-amount td-persona-jd"/);
assert.doesNotMatch(rowFor(htmlJd, 856), /data-label="\$ Pinki" class="td-amount td-persona-pinki"/);

montoColumnApi.setFiltro('pinki_comun');
montoColumnApi.buildRows([gasto856, gasto857]);
montoColumnApi.renderGastosTable();
let htmlPinki = element('tabla-body').innerHTML;
assert.match(rowFor(htmlPinki, 856), /data-label="\$ Pinki" class="td-amount td-persona-pinki"/);
assert.doesNotMatch(rowFor(htmlPinki, 856), /data-label="\$ JD" class="td-amount td-persona-jd"/);

montoColumnApi.setFiltro('comun');
montoColumnApi.buildRows([gasto856, gasto857]);
montoColumnApi.renderGastosTable();
let htmlComun = element('tabla-body').innerHTML;
assert.doesNotMatch(htmlComun, /td-persona-jd|td-persona-pinki/, 'Sin filtro de una persona puntual no debe resaltarse ninguna columna');

// El ordenamiento por "Monto" debe ordenar por el total mostrado (monto_propio),
// no por la porción recortada por el filtro -- con estos montos y reparto,
// un sort por la porción filtrada (jd_comun) daría el orden inverso.
const gastoChico = { id: 901, fecha: '2026-10-01', monto: 5000, categoria: 'Hogar',
  descripcion_original: 'Chico', medio_pago: 'Efectivo', pagado_por: 'Común',
  tipo_proporcion: 'custom', proporcion_jd: 90, proporcion_pinki: 10 };
const gastoGrande = { id: 902, fecha: '2026-10-02', monto: 10000, categoria: 'Hogar',
  descripcion_original: 'Grande', medio_pago: 'Efectivo', pagado_por: 'Común',
  tipo_proporcion: 'custom', proporcion_jd: 10, proporcion_pinki: 90 };
montoColumnApi.setFiltro('jd_comun');
montoColumnApi.buildRows([gastoGrande, gastoChico]);
montoColumnApi.setSort('monto_total', 'asc');
montoColumnApi.renderGastosTable();
const sortedHtml = element('tabla-body').innerHTML;
const sortedIds = Array.from(sortedHtml.matchAll(/data-id="(\d+)"/g), (m) => m[1]);
assert.deepEqual([...new Set(sortedIds)], ['901', '902'],
  'Orden ascendente por Monto debe seguir el total (5000 < 10000), no la porción recortada por el filtro jd_comun (que la invertiría)');

// Mismo chequeo en orden DESCENDENTE (cobertura pedida por QA, brief
// t_38a7253f F1b-fix2 punto 3): con filtro de persona activo, el total
// manda igual que en ascendente, solo invertido.
montoColumnApi.setFiltro('jd_comun');
montoColumnApi.buildRows([gastoGrande, gastoChico]);
montoColumnApi.setSort('monto_total', 'desc');
montoColumnApi.renderGastosTable();
const sortedHtmlDesc = element('tabla-body').innerHTML;
const sortedIdsDesc = Array.from(sortedHtmlDesc.matchAll(/data-id="(\d+)"/g), (m) => m[1]);
assert.deepEqual([...new Set(sortedIdsDesc)], ['902', '901'],
  'Orden descendente por Monto debe seguir el total (10000 > 5000), no la porción recortada por el filtro jd_comun');

console.log('Tabla de detalle de gastos: columna Monto = total, resaltado de persona filtrada y orden por total (asc/desc) verificados');

// renderDeudaDetail (brief fix4 #4): tras quitar la columna "Mes" el thead
// quedó en 8 columnas (Fecha, Descripción, Monto, %JD, %Pinki, $JD, $Pinki,
// acción); el tfoot debe cubrir exactamente la misma cantidad -- antes usaba
// colspan="6" + 3 celdas más (9 columnas), desalineando el total.
const deudaDetailElements = new Map();
const deudaDetailDocument = {
  getElementById: (id) => {
    if (!deudaDetailElements.has(id)) deudaDetailElements.set(id, { innerHTML: '' });
    return deudaDetailElements.get(id);
  },
};
const deudaDetailApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
const P1 = 'JD', P2 = 'Pinki';
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
function fmtARS(value) { return '$' + value; }
${slice('function getDebtRows(', '// ── ESTADO')}
${slice('function getRowPct(', '// ── FILTROS DE DATOS')}
${slice('function renderDeudaDetail(', 'function renderIngresosView(')}
({ renderDeudaDetail })`, { document: deudaDetailDocument, DATA: { loadErrors: {}, gastos: [
  { id: 11, fecha: '2026-09-01', monto: 1000, pagado_por: 'JD', categoria: 'Hogar',
    tipo_proporcion: 'custom', proporcion_jd: 50, proporcion_pinki: 50, saldado: null },
] } });
deudaDetailApi.renderDeudaDetail();
const deudaDetailHtml = deudaDetailElements.get('deuda-detail-inner').innerHTML;
const theadCols = (deudaDetailHtml.match(/<thead>[\s\S]*?<\/thead>/)[0].match(/<th[\s>]/g) || []).length;
const tfootBlock = deudaDetailHtml.match(/<tfoot>[\s\S]*?<\/tfoot>/)[0];
const tfootColspan = Number(tfootBlock.match(/colspan="(\d+)"/)[1]);
const tfootCellCount = (tfootBlock.match(/<td/g) || []).length;
assert.equal(tfootColspan + (tfootCellCount - 1), theadCols,
  'El tfoot de detalle de deuda debe cubrir la misma cantidad de columnas que el thead');

const fixedControls = new Map([
  ['field-responsable', { value: 'Común' }],
  ['fixed-split-fields', { hidden: false }],
  ['field-fixed_tipo_proporcion', { value: 'custom', disabled: false }],
  ['fixed-custom-proportion', { hidden: false }],
  ['field-proporcion_jd', { value: '0', disabled: false }],
  ['fixed-pinki-percent', { textContent: '' }],
]);
const splitUi = runInNewContext(`${slice('function syncCustomProportion(', 'function validMoney(')}
syncCustomProportion`, { document: { getElementById: (id) => fixedControls.get(id) || null }, Number });
splitUi();
assert.equal(fixedControls.get('fixed-pinki-percent').textContent, '100%');
fixedControls.get('field-responsable').value = 'JD';
splitUi();
assert.equal(fixedControls.get('fixed-split-fields').hidden, true);
assert.equal(fixedControls.get('field-fixed_tipo_proporcion').disabled, true);
assert.equal(fixedControls.get('field-proporcion_jd').disabled, true);
fixedControls.get('field-responsable').value = 'Pinki';
splitUi();
assert.equal(fixedControls.get('fixed-custom-proportion').hidden, true);
fixedControls.get('field-responsable').value = 'Común';
fixedControls.get('field-fixed_tipo_proporcion').value = 'dinamica';
splitUi();
assert.equal(fixedControls.get('fixed-custom-proportion').hidden, true);
assert.equal(fixedControls.get('field-proporcion_jd').disabled, true);
assert.equal(api.collectForm('fixed-delete', fixed, { fecha_baja: '2026-10-20' }).payload.fecha_baja, '2026-10-20');

const versions = [fixed,
  { ...fixed, id: 42, vigente_desde: '2026-10-01', monto_mensual: 110 },
  { ...fixed, id: 43, vigente_desde: '2026-11-01', monto_mensual: 120 }];
const history = api.fijosHistorial(versions, 41);
assert.equal(history[0].supersedida_mismo_dia, true);
assert.equal(history[0].vigente_hasta, null);
assert.equal(history[1].vigente_hasta, '2026-10-31');
assert.equal(api.fijosTramos(versions, '2026-10-01', '2026-11-30').length, 2);
assert.equal(api.fijosEvolutionData(history).dates.length, 2);

// Revisor d2efc768 #3: renderFijosHistoryGroup solo invierte el orden de
// VISUALIZACIÓN; el grupo llega cronológico (más viejo primero) y debe
// mostrarse con la versión más nueva primero.
const historyGroupApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
function fmtARS(value) { return '$' + value; }
${slice('function pillClassFor(', 'function sum(')}
${slice('function fijosDateLabel(', 'function fijosRepartoLabel(')}
${slice('function renderFijosHistoryGroup(', 'function renderFijosView(')}
({ renderFijosHistoryGroup })`, {});
const fijosHistoryOld = { tramo_desde: '2026-01-01', tramo_hasta: '2026-05-31', nombre: 'Internet',
  monto_mensual: 100, periodicidad: 'mensual', responsable: 'Común', activo: 1 };
const fijosHistoryNew = { tramo_desde: '2026-06-01', tramo_hasta: null, nombre: 'Internet',
  monto_mensual: 150, periodicidad: 'mensual', responsable: 'Común', activo: 1 };
const fijosHistoryHtml = historyGroupApi.renderFijosHistoryGroup('5', [fijosHistoryOld, fijosHistoryNew], fijosHistoryNew);
const newTramoIndex = fijosHistoryHtml.indexOf('$150/mes');
const oldTramoIndex = fijosHistoryHtml.indexOf('$100/mes');
assert.ok(newTramoIndex >= 0 && oldTramoIndex >= 0 && newTramoIndex < oldTramoIndex,
  'renderFijosHistoryGroup debe listar la versión más nueva primero');

// "Saldar todas las deudas" (brief F1 #2): sin fila propia (row=null), payload
// null (nada que revisar), ruta fija y un resumen (cantidad + monto total) que
// reusa el mismo universo que getDebtRows() -- pagado por JD o Pinki, nunca
// Común, sin saldar todavía.
const debtRowsBackup = api.DATA.gastos;
api.DATA.gastos = [
  { id: 201, fecha: '2026-09-01', monto: 1000, pagado_por: 'JD', tipo_proporcion: '50/50', saldado: null },
  { id: 202, fecha: '2026-09-02', monto: 500, pagado_por: 'Pinki', tipo_proporcion: '50/50', saldado: null },
  { id: 203, fecha: '2026-09-03', monto: 300, pagado_por: 'Común', tipo_proporcion: '50/50', saldado: null },
];
const saldarTodasCollected = api.collectForm('expense-saldar-todas', null, {});
assert.equal(saldarTodasCollected.payload, null);
assert.equal(Object.keys(saldarTodasCollected.errors).length, 0);
assert.deepEqual(Array.from(api.routeForForm('expense-saldar-todas', null)), ['POST', '/api/expenses/saldar-todas']);
assert.equal(api.describeForm('expense-saldar-todas', null, null),
  'Saldar 2 gastos pendientes por un total de $1500.00. Deja la deuda neta entre JD y Pinki en $0.');
api.DATA.gastos = debtRowsBackup;

// Reparto de gasto: atajos "100% JD" / "100% Pinki" (brief F1 #6). El backend
// solo admite tipo_proporcion 'dinamico'/'custom' (ver validaciones.py), así
// que ambos atajos viajan como 'custom' con el 100/0 ya resuelto.
const jd100 = api.collectForm('expense', null, { ...expenseValues, tipo_proporcion: 'jd_100' });
assert.equal(Object.keys(jd100.errors).length, 0);
assert.equal(jd100.payload.tipo_proporcion, 'custom');
assert.equal(jd100.payload.proporcion_jd, 100);
assert.equal(jd100.payload.proporcion_pinki, 0);
const pinki100 = api.collectForm('expense', null, { ...expenseValues, tipo_proporcion: 'pinki_100' });
assert.equal(pinki100.payload.tipo_proporcion, 'custom');
assert.equal(pinki100.payload.proporcion_jd, 0);
assert.equal(pinki100.payload.proporcion_pinki, 100);
const pinki100Edit = api.collectForm('expense-edit', expense, { ...expenseEditValues, tipo_proporcion: 'pinki_100' });
assert.equal(pinki100Edit.payload.tipo_proporcion, 'custom');
assert.equal(pinki100Edit.payload.proporcion_jd, 0);
assert.equal(pinki100Edit.payload.proporcion_pinki, 100);
// Cobertura faltante (brief fix4 #5): atajo "100% JD" en edición, mismo
// criterio que "100% Pinki" ya cubierto arriba.
const jd100Edit = api.collectForm('expense-edit', expense, { ...expenseEditValues, tipo_proporcion: 'jd_100' });
assert.equal(jd100Edit.payload.tipo_proporcion, 'custom');
assert.equal(jd100Edit.payload.proporcion_jd, 100);
assert.equal(jd100Edit.payload.proporcion_pinki, 0);

// Bug previo (brief fix4 #6): "Mitad y mitad" enviaba tipo_proporcion='50/50'
// tal cual, que el backend rechaza (validaciones.TIPO_PROPORCION_VALIDOS solo
// admite 'dinamico'/'custom'). Debe traducirse a 'custom' + 50/50, igual
// criterio que los atajos 100% JD/Pinki, tanto en alta como en edición.
const mitad = api.collectForm('expense', null, { ...expenseValues, tipo_proporcion: '50/50' });
assert.equal(Object.keys(mitad.errors).length, 0);
assert.equal(mitad.payload.tipo_proporcion, 'custom');
assert.equal(mitad.payload.proporcion_jd, 50);
assert.equal(mitad.payload.proporcion_pinki, 50);
const mitadEdit = api.collectForm('expense-edit', expense, { ...expenseEditValues, tipo_proporcion: '50/50' });
assert.equal(mitadEdit.payload.tipo_proporcion, 'custom');
assert.equal(mitadEdit.payload.proporcion_jd, 50);
assert.equal(mitadEdit.payload.proporcion_pinki, 50);

// Categoría de gasto fijo (brief F1 #5): se manda solo si el campo viene
// completo; vacío no pisa la categoría heredada de la versión vigente.
const fixedWithCategoriaValues = { ...fixedValues, categoria: 'Hogar' };
const collectedFixedCategoria = api.collectForm('fixed', null, fixedWithCategoriaValues);
assert.equal(collectedFixedCategoria.payload.categoria, 'Hogar');
assert.match(api.describeForm('fixed', null, collectedFixedCategoria.payload), /Nuevo fijo Prueba sintética nueva \(Hogar\)/);
assert.equal('categoria' in api.collectForm('fixed', null, fixedValues).payload, false,
  'Sin categoria en el form, el campo no viaja en el payload');
assert.equal('categoria' in api.collectForm('fixed-edit', fixed, fixedValues).payload, false,
  'Editar sin categoria no la manda -- la nueva versión hereda la vigente');

// Subcategoría de gasto fijo (brief t_38a7253f F1b, hallazgo A): misma regla
// de herencia que categoría.
const fixedWithSubcategoriaValues = { ...fixedValues, categoria: 'Hogar', subcategoria: 'Alquiler' };
const collectedFixedSubcategoria = api.collectForm('fixed', null, fixedWithSubcategoriaValues);
assert.equal(collectedFixedSubcategoria.payload.subcategoria, 'Alquiler');
assert.match(api.describeForm('fixed', null, collectedFixedSubcategoria.payload), /Nuevo fijo Prueba sintética nueva \(Hogar \/ Alquiler\)/);
assert.equal('subcategoria' in api.collectForm('fixed', null, fixedValues).payload, false,
  'Sin subcategoria en el form, el campo no viaja en el payload');
assert.equal('subcategoria' in api.collectForm('fixed-edit', fixed, fixedValues).payload, false,
  'Editar sin subcategoria no la manda -- la nueva versión hereda la vigente');

const writes = [
  ['expense', null, collectedExpense.payload, '/api/expenses', 201, { expenses: [expense] }],
  ['expense-edit', expense, collectedExpenseEdit.payload, '/api/expenses/21', 200, { expense }],
  ['expense-delete', expense, null, '/api/expenses/21', 200, { deleted: true, id: 21 }],
  ['expense-saldar-todas', null, null, '/api/expenses/saldar-todas', 200,
    { expenses: [{ ...expense, saldado: '2026-10-17' }], count: 1, total: 30 }],
  ['income', null, api.collectForm('income', null, incomeValues).payload, '/api/income', 201, { income }],
  ['income-edit', income, collectedIncome.payload, '/api/income/31', 200, { income }],
  ['fixed', null, api.collectForm('fixed', null, fixedValues).payload, '/api/fixed', 201, { fixed }],
  ['fixed-edit', fixed, api.collectForm('fixed-edit', fixed, fixedValues).payload, '/api/fixed/41', 200, { fixed }],
  ['fixed-delete', fixed, { fecha_baja: '2026-10-20' }, '/api/fixed/41', 200, { fixed: { ...fixed, activo: 0 } }],
];
for (const [kind, row, payload, path, status, body] of writes) {
  reply(path, status, body);
  await api.writeForm(kind, row, payload);
  const call = calls.at(-1);
  assert.equal(call.path, path);
  assert.equal(call.options.credentials, 'same-origin');
  assert.equal(call.options.method, api.routeForForm(kind, row)[0]);
  if (payload === null) assert.equal('body' in call.options, false);
  else {
    assert.equal(call.options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(call.options.body), JSON.parse(JSON.stringify(payload)));
    assert.equal('actor' in JSON.parse(call.options.body), false);
    assert.equal('confirmado' in JSON.parse(call.options.body), false);
  }
}

for (const jd of [0, 25, 100]) {
  const { payload, errors } = api.collectForm('fixed', null,
    { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: String(jd) });
  assert.equal(Object.keys(errors).length, 0);
  reply('/api/fixed', 201, { fixed: { ...fixed, tipo_proporcion: 'custom', proporcion_jd: jd } });
  await api.writeForm('fixed', null, payload);
  const body = JSON.parse(calls.at(-1).options.body);
  assert.equal(body.tipo_proporcion, 'custom');
  assert.equal(body.proporcion_jd, jd);
  assert.equal(typeof body.proporcion_jd, 'number');
  assert.equal(body.responsable, 'Común');
  assert.equal('proporcion_pinki' in body, false);
  assert.equal('actor' in body || 'confirmado' in body || 'secret' in body, false);
}
const decimal = api.collectForm('fixed', null,
  { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: '33.333' });
assert.equal(Object.keys(decimal.errors).length, 0);
assert.equal(decimal.payload.proporcion_jd, 33.333);
const dynamic = api.collectForm('fixed', null, fixedValues);
reply('/api/fixed', 201, { fixed });
await api.writeForm('fixed', null, dynamic.payload);
assert.equal(JSON.parse(calls.at(-1).options.body).tipo_proporcion, 'dinamica');
assert.equal(JSON.parse(calls.at(-1).options.body).proporcion_jd, null);

const existing25 = { ...customFixed, proporcion_jd: 25 };
const amountOnly = api.collectForm('fixed-edit', existing25,
  { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: '25' });
assert.equal('tipo_proporcion' in amountOnly.payload, false);
assert.equal('proporcion_jd' in amountOnly.payload, false);
reply('/api/fixed/41', 200, { fixed: { ...customFixed, id: 42, monto_estimado: 120, proporcion_jd: 25 } });
await api.writeForm('fixed-edit', existing25, amountOnly.payload);
assert.equal(calls.at(-1).options.method, 'PATCH');
assert.equal('tipo_proporcion' in JSON.parse(calls.at(-1).options.body), false);
assert.equal('proporcion_jd' in JSON.parse(calls.at(-1).options.body), false);
assert.match(api.describeForm('fixed-edit', existing25, amountOnly.payload), /25% JD \/ 75% Pinki.*historial/);
const changedCustom = api.collectForm('fixed-edit', customFixed,
  { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: '25' }).payload;
assert.equal(changedCustom.tipo_proporcion, 'custom');
assert.equal(changedCustom.proporcion_jd, 25);
reply('/api/fixed/41', 200, { fixed: { ...customFixed, id: 44, proporcion_jd: 25 } });
await api.writeForm('fixed-edit', customFixed, changedCustom);
assert.equal(JSON.parse(calls.at(-1).options.body).proporcion_jd, 25);

const changedToDynamic = api.collectForm('fixed-edit', customFixed, fixedValues).payload;
assert.equal(changedToDynamic.tipo_proporcion, 'dinamica');
assert.equal(changedToDynamic.proporcion_jd, null);
const retainedDynamic = api.collectForm('fixed-edit', fixed, fixedValues).payload;
assert.equal('tipo_proporcion' in retainedDynamic, false);
assert.equal('proporcion_jd' in retainedDynamic, false);
const changedToPersonal = api.collectForm('fixed-edit', customFixed,
  { ...fixedValues, responsable: 'JD', fixed_tipo_proporcion: 'custom', proporcion_jd: '25' }).payload;
assert.equal(changedToPersonal.responsable, 'JD');
assert.equal('tipo_proporcion' in changedToPersonal, false);
assert.equal('proporcion_jd' in changedToPersonal, false);
reply('/api/fixed/41', 200, { fixed: { ...customFixed, id: 43, responsable: 'JD', tipo_proporcion: null, proporcion_jd: 100 } });
await api.writeForm('fixed-edit', customFixed, changedToPersonal);
assert.equal('tipo_proporcion' in JSON.parse(calls.at(-1).options.body), false);
assert.equal('proporcion_jd' in JSON.parse(calls.at(-1).options.body), false);
const backToCommon = api.collectForm('fixed-edit', { ...fixed, responsable: 'JD', tipo_proporcion: null, proporcion_jd: 100 }, fixedValues).payload;
assert.equal(backToCommon.tipo_proporcion, 'dinamica');
assert.equal(backToCommon.proporcion_jd, null);

for (const bad of ['', '-1', '100.001', 'false', 'NaN', 'Infinity', false, true]) {
  const result = api.collectForm('fixed', null,
    { ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: bad });
  assert.ok(result.errors.proporcion_jd, `Porcentaje inválido: ${String(bad)}`);
}
for (const status of [400, 409, 500]) {
  reply('/api/expenses', status, { error: 'falló la prueba sintética' });
  await assert.rejects(api.writeForm('expense', null, collectedExpense.payload), new RegExp(`HTTP ${status}`));
}
// La baja de un ingreso ya borrado responde 404; se maneja como rechazo, no como éxito silencioso.
reply(`/api/income/${income.id}`, 404, { error: 'no encontrado' });
await assert.rejects(api.writeForm('income-delete', income, null), /HTTP 404/);

reply('/api/expenses', 201, { expenses: [expense] });
reply('/api/expenses', 500, { error: 'recarga fallida' });
reply('/api/income', 200, { income: [income] });
reply('/api/fixed/versions', 200, { versions: [fixed] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
const before = calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length;
const result = await api.saveAndReload('expense', null, collectedExpense.payload);
assert.equal(result.saved, true);
assert.equal(result.reloaded, false);
assert.equal(api.state.reloadFailed, true);
assert.equal(api.state.period.refMonth, '2026-10');
assert.equal(calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length, before + 1);
assert.equal(api.DATA.gastos[0].id, '21', 'La carga fallida conserva el panel previo');

// Un reintento sólo vuelve a leer. La respuesta nueva pasa a DATA sin repetir el POST.
const updatedExpense = { ...expense, id: 22, monto: 90 };
reply('/api/expenses', 200, { expenses: [expense, updatedExpense] });
reply('/api/income', 200, { income: [income] });
reply('/api/fixed/versions', 200, { versions: [fixed] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, { ...summary, expenses_total: 120,
  debt_pending_through_month: owing, debt_status: 'pendiente' });
await api.handleRetryReload();
assert.equal(api.DATA.gastos.length, 2);
assert.equal(api.DATA.gastos[1].monto, 90);
assert.equal(api.DATA.deudaPendiente.deudor, 'Pinki');
assert.equal(api.DATA.deudaPendiente.acreedor, 'JD');
assert.equal(api.DATA.deudaPendiente.monto, 25);
api.renderDeudaCard();
assert.match(element('g-deuda-quien').textContent, /Pinki le debe a JD/);
assert.equal(api.DATA.resumen.find((item) => item.mes === '2026-10').debt_status, 'pendiente');
assert.equal(api.state.reloadFailed, false);
assert.equal(calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length, before + 1);

// El 2xx con ID redondeado confirma el guardado; una recarga inválida bloquea escrituras.
reply('/api/expenses', 201, { expenses: [{ ...expense, id: 9007199254740992 }] });
reply('/api/expenses', 200, { expenses: [{ ...expense, id: 9007199254740992 }] });
reply('/api/income', 200, { income: [income] });
reply('/api/fixed/versions', 200, { versions: [fixed] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
const postsBeforeUnsafe = calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length;
const unsafeSaved = await api.saveAndReload('expense', null, collectedExpense.payload);
assert.equal(unsafeSaved.saved, true);
assert.equal(unsafeSaved.identityVerified, false);
assert.equal(unsafeSaved.reloaded, false);
assert.equal(api.state.reloadFailed, true);
assert.equal(calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length, postsBeforeUnsafe + 1);
reply('/api/expenses', 200, { expenses: [{ ...expense, id: largeId }] });
reply('/api/income', 200, { income: [{ ...income, id: maxId }] });
reply('/api/fixed/versions', 200, { versions: [{ ...fixed, id: maxId, fijo_grupo_id: largeId }] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
await api.handleRetryReload();
assert.equal(api.state.reloadFailed, false);
assert.equal(api.DATA.gastos[0].id, largeId);
assert.equal(calls.filter((call) => call.options.method === 'POST' && call.path === '/api/expenses').length, postsBeforeUnsafe + 1);

// Baja de ingreso: la escritura DELETE se confirma aunque la recarga posterior falle;
// el reintento de lectura nunca repite el DELETE.
reply(`/api/income/${income.id}`, 200, { deleted: true, id: income.id });
reply('/api/expenses', 200, { expenses: [{ ...expense, id: largeId }] });
reply('/api/income', 500, { error: 'recarga fallida' });
reply('/api/fixed/versions', 200, { versions: [{ ...fixed, id: maxId, fijo_grupo_id: largeId }] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
const deletesBefore = calls.filter((call) => call.options.method === 'DELETE' && call.path === `/api/income/${income.id}`).length;
const incomeDeleteResult = await api.saveAndReload('income-delete', income, null);
assert.equal(incomeDeleteResult.saved, true);
assert.equal(incomeDeleteResult.reloaded, false);
assert.equal(api.state.reloadFailed, true);
assert.equal(calls.filter((call) => call.options.method === 'DELETE' && call.path === `/api/income/${income.id}`).length, deletesBefore + 1);

reply('/api/expenses', 200, { expenses: [{ ...expense, id: largeId }] });
reply('/api/income', 200, { income: [] });
reply('/api/fixed/versions', 200, { versions: [{ ...fixed, id: maxId, fijo_grupo_id: largeId }] });
reply('/api/summary', 200, { months: [summary] });
reply('/api/summary?month=2026-10', 200, summary);
await api.handleRetryReload();
assert.equal(api.state.reloadFailed, false);
assert.equal(api.DATA.ingresos.length, 0, 'El reintento confirma que el ingreso ya no está');
assert.equal(calls.filter((call) => call.options.method === 'DELETE' && call.path === `/api/income/${income.id}`).length,
  deletesBefore + 1, 'El reintento de lectura no debe repetir el DELETE');

// También se comprueba el ID del envelope para cada método, sin convertirlo a Number.
for (const [kind, row, payload, path, body] of [
  ['expense-delete', { ...expense, id: largeId }, null, `/api/expenses/${largeId}`, { deleted: true, id: 9007199254740992 }],
  ['expense-edit', { ...expense, id: largeId }, collectedExpenseEdit.payload, `/api/expenses/${largeId}`, { expense: { ...expense, id: 9007199254740992 } }],
  ['income-edit', { ...income, id: largeId }, collectedIncome.payload, `/api/income/${largeId}`, { income: { ...income, id: 9007199254740992 } }],
  ['fixed-edit', { ...fixed, id: largeId }, amountOnly.payload, `/api/fixed/${largeId}`, { fixed: { ...fixed, id: maxId, fijo_grupo_id: largeId } }],
]) {
  reply(path, 200, body);
  const envelope = await api.writeForm(kind, row, payload);
  assert.equal(envelope.identityVerified, kind === 'fixed-edit');
  assert.equal(calls.at(-1).path, path);
}
reply(`/api/expenses/${largeId}`, 200, { deleted: true, id: largeId });
assert.equal((await api.writeForm('expense-delete', { ...expense, id: largeId }, null)).identityVerified, true);
reply('/api/expenses', 201, { expenses: [{ ...expense, id: largeId }] });
assert.equal((await api.writeForm('expense', null, collectedExpense.payload)).identityVerified, true);
reply(`/api/expenses/${largeId}`, 200, { expense: { ...expense, id: largeId } });
assert.equal((await api.writeForm('expense-edit', { ...expense, id: largeId }, collectedExpenseEdit.payload)).identityVerified, true);

// El submit real valida antes de llegar al fetch simulado.
const fixedModalElements = new Map();
const fixedModalElement = (id) => {
  if (!fixedModalElements.has(id)) fixedModalElements.set(id, {
    textContent: '', hidden: false, disabled: false,
    focus() {},
  });
  return fixedModalElements.get(id);
};
const fixedModalDocument = { getElementById: fixedModalElement, querySelectorAll: () => [] };
const fixedModalApi = runInNewContext(`
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
let authState = 'authenticated', currentView = 'fijos';
let activeForm = null;
function updateAvailability() {}
function showWriteNotice() {}
async function loadLive() {}
function fmtARSExact(value) { return '$' + Number(value).toFixed(2); }
function cuotaLabel(row) { return row.cuota_nro + '/' + row.cuotas_total; }
${slice('function fijosRepartoLabel(', 'function setFijosMode(')}
${slice('function closeForm(', 'function validMoney(')}
${slice('function validMoney(', 'function routeForForm(')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function routeForForm(', 'function showWriteNotice(')}
${slice('async function handleFormSubmit(', "document.getElementById('life-form').addEventListener")}
({ handleFormSubmit, setForm(row = null) {
  activeForm = { kind: row ? 'fixed-edit' : 'fixed', row,
    returnFocus: { isConnected: true, focus() {} }, confirmed: false, payload: null };
} })`, { document: fixedModalDocument, Date, Number, Math, fetch,
  FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values); } } });
const fixedSubmit = (values) => ({ preventDefault() {}, currentTarget: { values } });
for (const bad of ['', '-1', '100.001', 'false', false, true]) {
  fixedModalApi.setForm();
  const count = calls.length;
  await fixedModalApi.handleFormSubmit(fixedSubmit({ ...fixedValues,
    fixed_tipo_proporcion: 'custom', proporcion_jd: bad }));
  assert.equal(calls.length, count, `No debe haber request con ${String(bad)}`);
}
fixedModalApi.setForm();
const validFixedSubmit = fixedSubmit({ ...fixedValues, fixed_tipo_proporcion: 'custom', proporcion_jd: '0' });
const countBeforeConfirm = calls.length;
await fixedModalApi.handleFormSubmit(validFixedSubmit);
assert.equal(calls.length, countBeforeConfirm, 'Revisar todavía no escribe');
assert.match(fixedModalElement('form-confirm').textContent, /0% JD \/ 100% Pinki.*desde 2026-10-15/);
reply('/api/fixed', 201, { fixed: { ...fixed, id: 51, tipo_proporcion: 'custom', proporcion_jd: 0 } });
await fixedModalApi.handleFormSubmit(validFixedSubmit);
assert.equal(calls.length, countBeforeConfirm + 1);
assert.equal(JSON.parse(calls.at(-1).options.body).proporcion_jd, 0);

// El formulario salarial debe mostrar el impacto y mover el foco antes de escribir.
let confirmedWrites = 0;
let focused = null;
const modalElements = new Map();
const modalElement = (id) => {
  if (!modalElements.has(id)) modalElements.set(id, { textContent: '', hidden: false, disabled: false,
    focus() { focused = id; } });
  return modalElements.get(id);
};
const modalDocument = { getElementById: modalElement, querySelectorAll: () => [] };
const modalApi = runInNewContext(`
function fmtARSExact(value) { return '$' + Number(value).toFixed(2); }
function cuotaLabel(row) { return row.cuota_nro + '/' + row.cuotas_total; }
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
let currentView = 'ingresos';
let activeForm = { kind: 'income-edit', row: salaryRow, returnFocus, confirmed: false, payload: null };
function updateAvailability() {}
function showWriteNotice() {}
async function saveAndReload() { confirmedWrites.count++; return { saved: true, reloaded: true }; }
${slice('function closeForm(', 'function validMoney(')}
${slice('function validMoney(', 'function routeForForm(')}
${slice('async function handleFormSubmit(', "document.getElementById('life-form').addEventListener")}
({ handleFormSubmit, get form() { return activeForm; },
   setLive(value) { liveMode = value; },
   resetForm() { activeForm = { kind: 'income-edit', row: salaryRow, returnFocus, confirmed: false, payload: null }; } })`, {
  document: modalDocument, Date, Number, Math, salaryRow: income,
  returnFocus: { isConnected: true, focus() { focused = 'return-focus'; } },
  confirmedWrites: { get count() { return confirmedWrites; }, set count(value) { confirmedWrites = value; } },
  FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values); } },
});
const submitEvent = { preventDefault() {}, currentTarget: { values: incomeValues } };
await modalApi.handleFormSubmit(submitEvent);
assert.equal(confirmedWrites, 0);
assert.equal(modalApi.form.confirmed, true);
assert.match(modalElement('form-confirm').textContent, /proporciones.*deudas/);
assert.equal(modalElement('form-fields').hidden, true);
assert.equal(focused, 'form-submit');
await modalApi.handleFormSubmit(submitEvent);
assert.equal(confirmedWrites, 1);
assert.equal(modalApi.form, null);
assert.equal(focused, 'return-focus');
modalApi.resetForm();
modalApi.setLive(false);
await modalApi.handleFormSubmit(submitEvent);
assert.equal(confirmedWrites, 1, 'Sin sesión live el modal no inicia escrituras');

// El ciclo completo del modal (abrir → confirmar → guardar/cancelar → cerrar → reabrir)
// debe dejar siempre #form-fields visible, sin depender de cómo se salió la vez anterior.
const modalCycleElements = new Map();
const modalCycleElement = (id) => {
  if (!modalCycleElements.has(id)) modalCycleElements.set(id, { textContent: '', innerHTML: '',
    hidden: false, disabled: false, value: '', focus() {}, addEventListener() {},
    querySelector: () => ({ focus() {} }), querySelectorAll: () => [] });
  return modalCycleElements.get(id);
};
const modalCycleDocument = { getElementById: modalCycleElement, querySelectorAll: () => [], activeElement: null };
const modalCycleApi = runInNewContext(`
function todayLocalISO() { return '2026-10-17'; }
function fmtARSExact(value) { return '$' + Number(value).toFixed(2); }
function cuotaLabel(row) { return (row.cuota_nro || 1) + '/' + (row.cuotas_total || 1); }
${slice('const escapeHtml = ', 'const fmtARS = ')}
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
let currentView = 'fijos';
let activeForm = null, categoriesGastoCache = null, activeExpenseCatalog = null;
const DATA = { gastos: [], ingresos: [], fijos: [] };
function updateAvailability() {}
function showWriteNotice() {}
async function saveAndReload() { return { saved: true, reloaded: true }; }
// Catálogo disponible (no es el foco de este ciclo de modal): sin esto,
// openForm('fixed') tomaría el camino fail-closed (brief t_38a7253f
// F1b-fix2 #1) y nunca llegaría a pintar los campos que este test ejercita.
async function loadCategoriasGasto() { return [{ categoria: 'Hogar', subcategorias: ['Alquiler'] }]; }
${slice('function formField(', 'function routeForForm(')}
${slice('async function handleFormSubmit(', "document.getElementById('life-form').addEventListener")}
({ openForm, closeForm, handleFormSubmit })`,
  { document: modalCycleDocument, Date, Number, Math,
    FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values); } } });

const modalFixedValues = { nombre: 'Prueba ciclo', monto_estimado: '50', periodicidad: 'mensual',
  responsable: 'Común', fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-10-15' };
const modalSubmit = () => ({ preventDefault() {}, currentTarget: { values: modalFixedValues } });

// Ciclo 1: abrir → confirmar → guardar (closeForm se dispara dentro de handleFormSubmit) → reabrir.
// openForm() es async (carga el catálogo de categorías antes de pintar los
// campos reales, ver fail-closed de fijos): si no se espera acá, su
// continuación pendiente queda encolada como microtask y puede resolverse
// DESPUÉS del handleFormSubmit siguiente, repintando #form-fields con el
// catálogo recién llegado y pisando el estado de confirmación que
// handleFormSubmit ya había dejado (hidden=true). Awaitear openForm() antes
// de interactuar con el form evita esa carrera.
await modalCycleApi.openForm('fixed');
assert.equal(modalCycleElement('form-fields').hidden, false);
assert.equal(modalCycleElement('form-confirm').hidden, true);
assert.equal(modalCycleElement('form-back').hidden, true);
await modalCycleApi.handleFormSubmit(modalSubmit());
assert.equal(modalCycleElement('form-fields').hidden, true, 'La confirmación oculta los campos');
assert.equal(modalCycleElement('form-confirm').hidden, false);
await modalCycleApi.handleFormSubmit(modalSubmit());
await modalCycleApi.openForm('fixed');
assert.equal(modalCycleElement('form-fields').hidden, false, 'openForm debe dejar #form-fields visible tras guardar');
assert.equal(modalCycleElement('form-confirm').hidden, true, 'openForm debe ocultar #form-confirm al reabrir');
assert.equal(modalCycleElement('form-back').hidden, true, 'openForm debe ocultar #form-back al reabrir');
assert.equal(modalCycleElement('form-submit').disabled, false);

// Ciclo 2: abrir → confirmar → cancelar desde la confirmación (closeForm manual, como Escape) → reabrir.
await modalCycleApi.handleFormSubmit(modalSubmit());
assert.equal(modalCycleElement('form-fields').hidden, true);
modalCycleApi.closeForm();
assert.equal(modalCycleElement('form-fields').hidden, false, 'Cancelar desde la confirmación debe revertir el estado');
assert.equal(modalCycleElement('form-confirm').hidden, true);
assert.equal(modalCycleElement('form-back').hidden, true);
await modalCycleApi.openForm('fixed');
assert.equal(modalCycleElement('form-fields').hidden, false, 'Reabrir tras cancelar deja #form-fields visible');
assert.equal(modalCycleElement('form-errors').textContent, '');

// XSS: una periodicidad maliciosa no debe llegar sin escapar al detalle de fijos (innerHTML).
const fijosXssElements = new Map();
const fijosXssElement = (id) => {
  if (!fijosXssElements.has(id)) fijosXssElements.set(id, { innerHTML: '' });
  return fijosXssElements.get(id);
};
const fijosXssDocument = { getElementById: fijosXssElement };
const fijosXssApi = runInNewContext(`
function fmtARS(value) { return '$' + value; }
let fijosPersonaFiltro = 'comun', personaFiltro = 'comun';
${slice('const capitalize = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function allocationAmount(', 'function setPersonaFiltro(')}
${slice('function fixedAllocation(', 'function computeFixedForPersona(')}
${slice('function getMonthsInPeriod(', 'function selectPeriodType(')}
${slice('function fijosLastDay(', 'function fijosEvolutionData(')}
${slice('function fixedCutoffDate(', 'function fixedMonthCutoff(')}
${slice('function fixedMonthCutoff(', 'function creditFixedItems(')}
${slice('function fijosDateLabel(', 'function fijosResponsable(')}
${slice('function renderFijosDetail(', 'function renderCuotasDetail(')}
({ renderFijosDetail })`, {
  document: fijosXssDocument,
  DATA: { loadErrors: {}, fijos: [{ id: 1, fijo_grupo_id: 1, nombre: '<svg onload=alert(1)>', categoria: 'Hogar',
    subcategoria: '', vigente_desde: '2026-10-01', monto_mensual: 100, monto_estimado: 100,
    periodicidad: '<img src=x onerror=alert(1)>', responsable: 'Común',
    tipo_proporcion: '50/50', activo: 1 }] },
  period: { from: '2026-10-01', to: '2026-10-31' },
  Date, Number, String, Math, Set });
fijosXssApi.renderFijosDetail();
const fijosDetailHtml = fijosXssElement('fijos-detail-inner').innerHTML;
assert.doesNotMatch(fijosDetailHtml, /<img/i, 'No debe generarse un elemento <img> sin escapar en el detalle de fijos');
assert.match(fijosDetailHtml, /&lt;img/, 'La periodicidad maliciosa debe llegar escapada al innerHTML');
assert.doesNotMatch(fijosDetailHtml, /<svg/i, 'El nombre del fijo no debe crear elementos');
assert.match(fijosDetailHtml, /&lt;svg/, 'El nombre del fijo debe quedar escapado');

// Revisor d2efc768 #1: el fallback de proporción debe usar el último mes
// anterior (o igual) con salarios, nunca uno posterior al mes consultado.
// Caso exacto: 60/40 en agosto, septiembre sin ingresos, 20/80 en octubre
// (dos meses después de agosto) → septiembre debe heredar agosto (60/40).
const resumenBackup = api.DATA.resumen;
api.DATA.resumen = [
  { mes: '2026-08', proporcion_jd: 60, proporcion_pinki: 40, total_ingresos: 100 },
  { mes: '2026-10', proporcion_jd: 20, proporcion_pinki: 80, total_ingresos: 100 },
];
const fallbackEntry = api.getMonthProportion('2026-09');
assert.equal(fallbackEntry.mes, '2026-08');
assert.equal(fallbackEntry.proporcion_jd, 60);
assert.equal(fallbackEntry.proporcion_pinki, 40);
api.DATA.resumen = resumenBackup;

// Revisor d2efc768 #2: monthsWithData, filterGastosPeriod y filterCuotasComprometidas
// deben ser coherentes para meses futuros con cuotas pendientes.
const gastosBackup = api.DATA.gastos;
const futureCuota = { id: 98, fecha: '2027-03-05', monto: 50, categoria: 'Comida',
  subcategoria: 'Almacén', medio_pago: 'Crédito', pagado_por: 'JD',
  tipo_proporcion: 'dinamico', cuota_nro: 2, cuotas_total: 4, descripcion_original: 'Cuota futura' };
const futureSingle = { id: 97, fecha: '2027-03-10', monto: 20, categoria: 'Comida',
  subcategoria: 'Almacén', medio_pago: 'Efectivo', pagado_por: 'JD',
  tipo_proporcion: 'dinamico', cuota_nro: 1, cuotas_total: 1, descripcion_original: 'Gasto futuro simple' };
api.DATA.gastos = [...gastosBackup, futureCuota, futureSingle];
assert.ok(api.monthsWithData().includes('2027-03'),
  'monthsWithData debe incluir meses futuros con cuotas pendientes');
const futurePeriodIds = Array.from(api.filterGastosPeriod('2027-03-01', '2027-03-31'), (r) => r.id).sort();
assert.deepEqual(futurePeriodIds, [97, 98]);
const futureCuotasIds = Array.from(api.filterCuotasComprometidas('2027-03-01', '2027-03-31'), (r) => r.id);
assert.deepEqual(futureCuotasIds, [98],
  'filterCuotasComprometidas solo debe incluir la fila con cuota_nro > 1');
api.DATA.gastos = gastosBackup;

// Revisor d2efc768 #4: income-delete no debe disparar el DELETE hasta confirmar,
// y el DELETE final debe ir exactamente al ID canónico del ingreso.
const incomeDeleteElements = new Map();
const incomeDeleteElement = (id) => {
  if (!incomeDeleteElements.has(id)) incomeDeleteElements.set(id, { textContent: '', innerHTML: '',
    hidden: false, disabled: false, value: '', focus() {}, addEventListener() {},
    querySelector: () => ({ focus() {} }), querySelectorAll: () => [] });
  return incomeDeleteElements.get(id);
};
const incomeDeleteDocument = { getElementById: incomeDeleteElement, querySelectorAll: () => [], activeElement: null };
const incomeDeleteApi = runInNewContext(`
function todayLocalISO() { return '2026-10-17'; }
function fmtARSExact(value) { return '$' + Number(value).toFixed(2); }
function cuotaLabel(row) { return (row.cuota_nro || 1) + '/' + (row.cuotas_total || 1); }
${slice('const escapeHtml = ', 'const fmtARS = ')}
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
let currentView = 'ingresos';
let activeForm = null;
const DATA = { gastos: [], ingresos: [incomeRow], fijos: [] };
function updateAvailability() {}
function showWriteNotice() {}
async function loadLive() {}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function formField(', 'function routeForForm(')}
${slice('function routeForForm(', 'function showWriteNotice(')}
${slice('async function handleFormSubmit(', "document.getElementById('life-form').addEventListener")}
({ openForm, closeForm, handleFormSubmit })`,
  { document: incomeDeleteDocument, Date, Number, Math, fetch, incomeRow: income,
    FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values); } } });

const incomeDeletePath = `/api/income/${income.id}`;
const deletesBeforeIncomeCycle = calls.filter((call) => call.options.method === 'DELETE' && call.path === incomeDeletePath).length;
incomeDeleteApi.openForm('income-delete', income.id);
assert.equal(incomeDeleteElement('form-fields').hidden, false);
const reviewEvent = { preventDefault() {}, currentTarget: { values: {} } };
await incomeDeleteApi.handleFormSubmit(reviewEvent);
assert.equal(incomeDeleteElement('form-fields').hidden, true, 'Revisar debe ocultar los campos y mostrar la confirmación');
assert.match(incomeDeleteElement('form-confirm').textContent, /Baja del ingreso de JD/);
assert.equal(calls.filter((call) => call.options.method === 'DELETE' && call.path === incomeDeletePath).length,
  deletesBeforeIncomeCycle, 'Revisar todavía no debe disparar el DELETE');
reply(incomeDeletePath, 200, { deleted: true, id: income.id });
await incomeDeleteApi.handleFormSubmit(reviewEvent);
const incomeDeleteCalls = calls.filter((call) => call.options.method === 'DELETE' && call.path === incomeDeletePath);
assert.equal(incomeDeleteCalls.length, deletesBeforeIncomeCycle + 1, 'Confirmar debe disparar exactamente un DELETE');
assert.equal(incomeDeleteCalls.at(-1).path, incomeDeletePath);
assert.equal('body' in incomeDeleteCalls.at(-1).options, false, 'La baja no debe enviar body');

// Revisor d2efc768 #4 (continuación): el botón de baja de un ingreso debe
// quedar deshabilitado en modo snapshot (sin sesión en vivo).
const ingresosTableElements = new Map();
const ingresosTableElement = (id) => {
  if (!ingresosTableElements.has(id)) ingresosTableElements.set(id, { textContent: '', innerHTML: '' });
  return ingresosTableElements.get(id);
};
const ingresosTableDocument = { getElementById: ingresosTableElement };
const ingresosTableApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
function fmtARS(value) { return '$' + value; }
${slice('function pillClassFor(', 'function sum(')}
function sum(rows, field) { return rows.reduce((acc, r) => acc + (parseFloat(r[field]) || 0), 0); }
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function getMonthProportion(', '// ── ESTADO')}
function mesLabel(m) { return m; }
function renderIncomeLines() {}
const P1 = 'JD', P2 = 'Pinki';
const DATA = { ingresos: [incomeRow], resumen: [] };
let period = { from: '2026-10-01', to: '2026-10-31', refMonth: '2026-10' };
let incomePersonaFiltro = 'all';
let liveMode = false, writePending = false, reloadPending = false, reloadFailed = false;
${slice('function filterGastosPeriod(', 'function fijosLastDay(')}
${slice('function renderIngresosView(', 'function renderIncomeLines(')}
({ renderIngresosView, setLive(value) { liveMode = value; } })`,
  { document: ingresosTableDocument, incomeRow: income, Date, Number, Math });

ingresosTableApi.renderIngresosView();
const ingresosSnapshotHtml = ingresosTableElement('tabla-ingresos-body').innerHTML;
assert.match(ingresosSnapshotHtml, /openForm\('income-delete', this\.dataset\.id\)/);
assert.match(ingresosSnapshotHtml, /aria-label="Dar de baja ingreso 31 de JD" disabled>Dar de baja<\/button>/,
  'En modo snapshot el botón de baja de ingreso debe quedar deshabilitado');
ingresosTableApi.setLive(true);
ingresosTableApi.renderIngresosView();
const ingresosLiveHtml = ingresosTableElement('tabla-ingresos-body').innerHTML;
assert.match(ingresosLiveHtml, /aria-label="Dar de baja ingreso 31 de JD" >Dar de baja<\/button>/,
  'En modo en vivo el botón de baja de ingreso debe estar habilitado');

// Relative periods end today even when future installments exist. The bar chart
// uses movements through the reference month, including months before the
// selected period, so this harness supplies synthetic source rows.
const gastosBarApi = runInNewContext(`
let capturedConfig = null;
function destroyChart(key) { delete charts[key]; }
function renderChart(key, canvas, config) { capturedConfig = config; }
${source.slice(0, source.indexOf('function fijosDateLabel('))}
${slice('function gastosBarMonthCutoff(', 'function drillDownToSubcat(')}
({ DATA, computePeriod, renderGastosBar, setPeriod(value) { period = value; },
   setFilter(value) { personaFiltro = value; },
   getConfig() { return capturedConfig; } })`, {
  document: { getElementById: () => ({}) },
  Date: class extends Date { constructor(...args) { super(...(args.length ? args : ['2026-10-16T12:00:00Z'])); } },
});
gastosBarApi.DATA.gastos = [500, 600, 550, 300, 300, 300, 999, 1234]
  .map((monto, index) => ({ fecha: `2026-${String(index + 5).padStart(2, '0')}-10`,
    monto, cuota_nro: index > 5 ? 2 : 1, tipo_proporcion: '50/50' }));
gastosBarApi.DATA.ingresos = [4000, 4200, 4300, 4600, 4600, 0, 0, 0]
  .map((monto, index) => ({ fecha: `2026-${String(index + 5).padStart(2, '0')}-10`,
    monto, persona: 'JD' }));
gastosBarApi.setPeriod(gastosBarApi.computePeriod('semester'));
gastosBarApi.renderGastosBar();
const gastosBarConfig = gastosBarApi.getConfig();
assert.deepEqual(Array.from(gastosBarConfig.data.labels), ["may '26", "jun '26", "jul '26", "ago '26", "sep '26", "oct '26"],
  'Las barras deben mostrar los últimos 6 meses hasta hoy, nunca meses futuros');
assert.deepEqual(Array.from(gastosBarConfig.data.datasets[0].data), [500, 600, 550, 300, 300, 300],
  'Los montos de gasto deben variar mes a mes, no quedar todos iguales por meses futuros duplicados');
assert.deepEqual(Array.from(gastosBarConfig.data.datasets[1].data), [4000, 4200, 4300, 4600, 4600, 0],
  'El ingreso debe verse en los meses que lo tienen cargado, no solo ceros');
gastosBarApi.setPeriod(gastosBarApi.computePeriod('month', { month: '2026-11' }));
gastosBarApi.renderGastosBar();
const futureMonthConfig = gastosBarApi.getConfig();
assert.deepEqual(Array.from(futureMonthConfig.data.labels),
  ["jun '26", "jul '26", "ago '26", "sep '26", "oct '26", "nov '26"],
  'El mes futuro elegido es el extremo derecho de los seis meses, aunque el período global sea de un mes');
assert.deepEqual(Array.from(futureMonthConfig.data.datasets[0].data), [600, 550, 300, 300, 300, 999],
  'Los cinco meses previos conservan sus gastos y noviembre incluye la cuota comprometida');
assert.deepEqual(Array.from(futureMonthConfig.data.datasets[1].data), [4200, 4300, 4600, 4600, 0, 0],
  'Los ingresos históricos permanecen en su mes y los futuros sin ingreso quedan en cero');
assert.equal(futureMonthConfig.data.labels.includes("dic '26"), false,
  'La cuota distinta de diciembre no agrega un mes posterior al elegido');

// A partial range clips only its final month. Earlier months remain complete,
// including those before the start of the selected period.
gastosBarApi.setPeriod(gastosBarApi.computePeriod('range', { from: '2026-10-16', to: '2026-11-09' }));
gastosBarApi.renderGastosBar();
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[0].data), [600, 550, 300, 300, 300, 0],
  'El corte del 9 de noviembre excluye la cuota del día 10 sin recortar octubre');
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[1].data), [4200, 4300, 4600, 4600, 0, 0]);
gastosBarApi.setPeriod(gastosBarApi.computePeriod('range', { from: '2026-10-16', to: '2026-11-10' }));
gastosBarApi.renderGastosBar();
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[0].data), [600, 550, 300, 300, 300, 999],
  'El día final del rango es inclusivo');

gastosBarApi.setFilter('jd_comun');
gastosBarApi.renderGastosBar();
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[0].data), [300, 275, 150, 150, 150, 499.5],
  'JD+Común aplica la proporción 50/50 a cada mes, incluida la cuota futura');
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[1].data), [4200, 4300, 4600, 4600, 0, 0],
  'El filtro JD conserva solo sus ingresos');
gastosBarApi.setFilter('pinki_comun');
gastosBarApi.renderGastosBar();
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[0].data), [300, 275, 150, 150, 150, 499.5]);
assert.deepEqual(Array.from(gastosBarApi.getConfig().data.datasets[1].data), [0, 0, 0, 0, 0, 0],
  'El filtro Pinki excluye los ingresos de JD sin alterar los límites mensuales');

console.log('Formularios: rutas, payloads y lectura posterior verificados con fixture de API sintética');
console.log('Modal: ciclo completo (guardar/cancelar/reabrir) y escape de XSS en detalle de fijos verificados');
console.log('Revisor d2efc768: fallback de proporción, meses futuros con cuotas, historial de fijos e income-delete verificados');

// ── CATÁLOGO DE CATEGORÍAS DE GASTO (t_ce790609 #2) ─────────────────────────
// GET /api/categories?tipo=Gasto lo implementa otra tarea en paralelo; acá se
// prueba el consumo: select de categoría + select dependiente de subcategoría,
// caché en memoria durante la sesión, fallback a texto libre sin romper el
// formulario, y escape de nombres maliciosos del catálogo.

const expenseFormSliceSetup = `
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('function todayLocalISO(', 'function firstAvailableDate(')}
${slice('async function fetchJSON(', 'function requireList(')}
${slice('function requireList(', 'const MAX_SQLITE_ID = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('async function loadCategoriasGasto(', 'async function loadAll(')}
${slice('function formField(', 'function routeForForm(')}
${slice('function routeForForm(', 'function showWriteNotice(')}
`;
// El listener real de Escape/Tab del modal (atado a #form-modal, no a una
// función): se aparta en un slice propio para que solo lo use el harness de
// carrera, que sí simula addEventListener/dispatch de verdad.
const modalKeydownSlice = slice("document.getElementById('form-modal').addEventListener('keydown'", '// ── VISTA GASTOS');
const raceExpenseFormSliceSetup = expenseFormSliceSetup + modalKeydownSlice;
function makeExpenseFormHarness() {
  const calls = [];
  const postQueue = [];
  let categoriesReply = null; // null/'throw' → sin red; { status, body } → respuesta mockeada
  const mockFetch = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/categories?tipo=Gasto') {
      if (!categoriesReply || categoriesReply === 'throw') throw new Error('Sin red en prueba sintética');
      const { status, body } = categoriesReply;
      return { ok: status >= 200 && status < 300, status, json: async () => body };
    }
    const next = postQueue.shift();
    if (!next) throw new Error(`Mock sin respuesta: ${path}`);
    return { ok: next.status >= 200 && next.status < 300, status: next.status, json: async () => next.body };
  };
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', hidden: false, disabled: false,
      value: '', focus() {}, addEventListener() {}, querySelector: () => ({ focus() {} }), querySelectorAll: () => [] });
    return elements.get(id);
  };
  const document = { getElementById: element, querySelectorAll: () => [], activeElement: null };
  const api = runInNewContext(`'use strict';
    let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
    let activeForm = null, categoriesGastoCache = null, activeExpenseCatalog = null, currentView = 'gastos';
    const DATA = { gastos: [], ingresos: [], fijos: [] };
    ${expenseFormSliceSetup}
    ({ openForm, closeForm, formMarkup, onExpenseCategoriaChange, collectForm, writeForm, retryFixedCatalog,
       get activeForm() { return activeForm; } })`,
    { document, fetch: mockFetch, Date, Number, Math, String, Array, Set,
      FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values || {}); } } });
  return { api, calls, postQueue, element, setCategoriesReply(reply) { categoriesReply = reply; } };
}

// 1) Catálogo disponible: <select> poblado desde la fixture real, y caché en
//    memoria (una sola llamada al endpoint aunque el form se abra dos veces).
const successForm = makeExpenseFormHarness();
successForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
await successForm.api.openForm('expense');
const categoriasHtml = successForm.element('form-fields').innerHTML;
assert.match(categoriasHtml, /<select id="field-categoria"/);
assert.doesNotMatch(categoriasHtml, /list="expense-categories"/, 'Con catálogo disponible no debe quedar el datalist de texto libre');
for (const entry of categoriesGastoFixture.categories) {
  assert.match(categoriasHtml, new RegExp(`<option value="${entry.categoria}">${entry.categoria}</option>`),
    `Falta la categoría "${entry.categoria}" del catálogo en el select`);
}
assert.equal(successForm.calls.filter((c) => c.path === '/api/categories?tipo=Gasto').length, 1);
await successForm.api.openForm('expense');
assert.equal(successForm.calls.filter((c) => c.path === '/api/categories?tipo=Gasto').length, 1,
  'Una segunda apertura del form no debe repetir el fetch: caché en memoria durante la sesión');

// 2) Subcategoría dependiente: solo muestra las de la categoría elegida, y se
//    repuebla (no acumula) al cambiar de categoría.
successForm.element('field-categoria').value = 'Hogar';
successForm.api.onExpenseCategoriaChange();
let subcatHtml = successForm.element('field-subcategoria').innerHTML;
const hogarEntry = categoriesGastoFixture.categories.find((c) => c.categoria === 'Hogar');
for (const sub of hogarEntry.subcategorias) assert.match(subcatHtml, new RegExp(`>${sub}<`));
assert.doesNotMatch(subcatHtml, />Supermercado</, 'No debe mezclar subcategorías de otra categoría');

successForm.element('field-categoria').value = 'Comida';
successForm.api.onExpenseCategoriaChange();
subcatHtml = successForm.element('field-subcategoria').innerHTML;
assert.match(subcatHtml, />Supermercado</);
assert.doesNotMatch(subcatHtml, />Alquiler</, 'Cambiar de categoría repuebla la subcategoría en vez de acumularla');
assert.match(subcatHtml, /<option value="">Sin subcategoría<\/option>/);

// 3) El payload de POST /api/expenses sigue igual: categoria/subcategoria
//    elegidas desde el catálogo viajan como texto plano, sin tocar el contrato.
const chosenExpenseValues = { fecha: '2026-10-05', monto: '45.50', categoria: 'Hogar',
  subcategoria: 'Alquiler', descripcion_original: 'Alquiler de octubre', medio_pago: 'Transferencia',
  pagado_por: 'Común', tarjeta_id: '', tipo_proporcion: 'dinamico', proporcion_jd: '50',
  proporcion_pinki: '50', cuotas_total: '1' };
const { payload: chosenPayload, errors: chosenErrors } = successForm.api.collectForm('expense', null, chosenExpenseValues);
assert.equal(Object.keys(chosenErrors).length, 0);
assert.equal(chosenPayload.categoria, 'Hogar');
assert.equal(chosenPayload.subcategoria, 'Alquiler');
successForm.postQueue.push({ status: 201, body: { expenses: [{ id: 501, ...chosenPayload }] } });
await successForm.api.writeForm('expense', null, chosenPayload);
const expensePostCall = successForm.calls.at(-1);
assert.equal(expensePostCall.path, '/api/expenses');
const expensePostBody = JSON.parse(expensePostCall.options.body);
assert.equal(expensePostBody.categoria, 'Hogar');
assert.equal(expensePostBody.subcategoria, 'Alquiler');

// 4) Fallback a texto libre si el catálogo no carga (red/HTTP) o viene vacío:
//    el formulario sigue usable, con un aviso breve, sin romperse.
const fallbackForm = makeExpenseFormHarness();
fallbackForm.setCategoriesReply('throw');
await fallbackForm.api.openForm('expense');
let fallbackHtml = fallbackForm.element('form-fields').innerHTML;
assert.doesNotMatch(fallbackHtml, /<select id="field-categoria"/);
assert.match(fallbackHtml, /id="field-categoria"[^>]*list="expense-categories"/);
assert.match(fallbackHtml, /No se pudo cargar el catálogo de categorías/);

fallbackForm.setCategoriesReply({ status: 200, body: { categories: [] } });
await fallbackForm.api.openForm('expense');
fallbackHtml = fallbackForm.element('form-fields').innerHTML;
assert.doesNotMatch(fallbackHtml, /<select id="field-categoria"/, 'Un catálogo vacío también debe caer al texto libre');
assert.match(fallbackHtml, /No se pudo cargar el catálogo de categorías/);

// 5) Escape de XSS: nombres maliciosos de categoría/subcategoría del catálogo
//    no deben crear elementos al pintarse en los <select>.
const xssForm = makeExpenseFormHarness();
const maliciousCategoria = '<img src=x onerror=alert(1)>';
const maliciousSubcategoria = '<svg onload=alert(2)>';
xssForm.setCategoriesReply({ status: 200, body: { categories: [{ categoria: maliciousCategoria, subcategorias: [maliciousSubcategoria] }] } });
await xssForm.api.openForm('expense');
const xssFieldsHtml = xssForm.element('form-fields').innerHTML;
assert.doesNotMatch(xssFieldsHtml, /<img/i);
assert.match(xssFieldsHtml, /&lt;img src=x onerror=alert\(1\)&gt;/);
xssForm.element('field-categoria').value = maliciousCategoria;
xssForm.api.onExpenseCategoriaChange();
const xssSubHtml = xssForm.element('field-subcategoria').innerHTML;
assert.doesNotMatch(xssSubHtml, /<svg/i);
assert.match(xssSubHtml, /&lt;svg onload=alert\(2\)&gt;/);

console.log('Categorías de gasto: select dependiente, caché en memoria, payload POST, fallback a texto y escape de XSS verificados');

// ── CATÁLOGO DE CATEGORÍAS EN EL FORM DE FIJO (brief t_38a7253f F1b, hallazgo A) ──
// Mismo mecanismo que el form de gasto (mismo endpoint, misma caché en
// memoria vía makeExpenseFormHarness), con dos diferencias a propósito:
// categoría/subcategoría quedan OPCIONALES (sin `required`), y el fallback
// de texto libre sugiere desde los fijos ya cargados, no desde los gastos.
const fixedCatalogForm = makeExpenseFormHarness();
fixedCatalogForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
await fixedCatalogForm.api.openForm('fixed');
const fixedCatalogHtml = fixedCatalogForm.element('form-fields').innerHTML;
assert.match(fixedCatalogHtml, /<select id="field-categoria"/);
assert.doesNotMatch(fixedCatalogHtml, /<select id="field-categoria" name="categoria" required/,
  'A diferencia de gasto, la categoría de un fijo no debe ser obligatoria');
assert.doesNotMatch(fixedCatalogHtml, /list="fixed-categorias"/,
  'Con catálogo disponible no debe quedar el datalist de texto libre');
for (const entry of categoriesGastoFixture.categories) {
  assert.match(fixedCatalogHtml, new RegExp(`<option value="${entry.categoria}">${entry.categoria}</option>`),
    `Falta la categoría "${entry.categoria}" del catálogo en el select de fijo`);
}
assert.equal(fixedCatalogForm.calls.filter((c) => c.path === '/api/categories?tipo=Gasto').length, 1);

// Subcategoría dependiente: mismo onExpenseCategoriaChange() que gasto, ya
// que ambos formularios comparten los ids #field-categoria/#field-subcategoria.
fixedCatalogForm.element('field-categoria').value = 'Hogar';
fixedCatalogForm.api.onExpenseCategoriaChange();
const fixedSubcatHtml = fixedCatalogForm.element('field-subcategoria').innerHTML;
assert.match(fixedSubcatHtml, />Alquiler</);
assert.doesNotMatch(fixedSubcatHtml, />Supermercado</, 'No debe mezclar subcategorías de otra categoría');

// Payload de alta con catálogo: categoria/subcategoria viajan como texto plano.
const chosenFixedValues = { nombre: 'Alquiler', monto_estimado: '200000', periodicidad: 'mensual',
  responsable: 'Común', fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-10-15',
  categoria: 'Hogar', subcategoria: 'Alquiler' };
const { payload: chosenFixedPayload, errors: chosenFixedErrors } = fixedCatalogForm.api.collectForm('fixed', null, chosenFixedValues);
assert.equal(Object.keys(chosenFixedErrors).length, 0);
assert.equal(chosenFixedPayload.categoria, 'Hogar');
assert.equal(chosenFixedPayload.subcategoria, 'Alquiler');

// ── SEMÁNTICA OMITIDO/NULL EN EDICIÓN DE FIJO (brief t_38a7253f F1b-fix2,
// hallazgo 2 del revisor): campo AUSENTE del form = heredar; "Sin
// categoría/subcategoría" elegido sobre un valor existente = null explícito.
const fixedConAmbas = { categoria: 'Hogar', subcategoria: 'Alquiler' };

// Heredar: el <select> sigue mostrando el valor vigente, sin tocarlo -- se omite.
const heredarValues = { nombre: 'Alquiler', monto_estimado: '200000', periodicidad: 'mensual',
  responsable: 'Común', fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-10-15',
  categoria: 'Hogar', subcategoria: 'Alquiler' };
const heredar = fixedCatalogForm.api.collectForm('fixed-edit', fixedConAmbas, heredarValues);
assert.equal(Object.keys(heredar.errors).length, 0);
assert.equal('categoria' in heredar.payload, false, 'Sin cambios, categoria se omite (hereda)');
assert.equal('subcategoria' in heredar.payload, false, 'Sin cambios, subcategoria se omite (hereda)');
assert.match(api.describeForm('fixed-edit', fixedConAmbas, heredar.payload),
  /categoría: Hogar; subcategoría: Alquiler/, 'Revisar debe mostrar los valores heredados');

// Cambiar: un valor nuevo viaja explícito.
const cambiarValues = { ...heredarValues, categoria: 'Comida', subcategoria: 'Supermercado' };
const cambiar = fixedCatalogForm.api.collectForm('fixed-edit', fixedConAmbas, cambiarValues);
assert.equal(Object.keys(cambiar.errors).length, 0);
assert.equal(cambiar.payload.categoria, 'Comida');
assert.equal(cambiar.payload.subcategoria, 'Supermercado');
assert.match(api.describeForm('fixed-edit', fixedConAmbas, cambiar.payload),
  /categoría: Comida; subcategoría: Supermercado/, 'Revisar debe mostrar ambos valores cambiados');

// Vaciar categoría ("Sin categoría" elegido sobre un fijo que la tenía):
// el <select> de subcategoría ya quedó resetado por onExpenseCategoriaChange
// (simulado acá con subcategoria: '') -- ambas viajan null explícito.
const vaciarCategoriaValues = { ...heredarValues, categoria: '', subcategoria: '' };
const vaciarCategoria = fixedCatalogForm.api.collectForm('fixed-edit', fixedConAmbas, vaciarCategoriaValues);
assert.equal(Object.keys(vaciarCategoria.errors).length, 0);
assert.equal(vaciarCategoria.payload.categoria, null);
assert.equal(vaciarCategoria.payload.subcategoria, null);
assert.match(api.describeForm('fixed-edit', fixedConAmbas, vaciarCategoria.payload),
  /categoría: Sin categoría; subcategoría: Sin subcategoría/, 'Revisar debe mostrar la limpieza explícita');

// Vaciar sólo subcategoría: la categoría no cambió (se omite), subcategoria viaja null.
const vaciarSubcategoriaValues = { ...heredarValues, categoria: 'Hogar', subcategoria: '' };
const vaciarSubcategoria = fixedCatalogForm.api.collectForm('fixed-edit', fixedConAmbas, vaciarSubcategoriaValues);
assert.equal(Object.keys(vaciarSubcategoria.errors).length, 0);
assert.equal('categoria' in vaciarSubcategoria.payload, false);
assert.equal(vaciarSubcategoria.payload.subcategoria, null);
assert.match(api.describeForm('fixed-edit', fixedConAmbas, vaciarSubcategoria.payload),
  /categoría: Hogar; subcategoría: Sin subcategoría/, 'Revisar combina categoría heredada y limpieza de subcategoría');
const asignarLegacy = fixedCatalogForm.api.collectForm('fixed-edit', { categoria: null, subcategoria: null }, heredarValues);
assert.match(api.describeForm('fixed-edit', { categoria: null, subcategoria: null }, asignarLegacy.payload),
  /categoría: Hogar; subcategoría: Alquiler/, 'Revisar muestra la asignación a un fijo legacy');
assert.match(api.describeForm('fixed-edit', { categoria: 'Hogar', subcategoria: 'Alquiler' },
  { ...heredar.payload, categoria: null }), /categoría: Sin categoría; subcategoría: Sin subcategoría/,
  'Si solo se envía categoría null, Revisar debe reflejar la limpieza en cascada del backend');

// Cambio de categoría limpia la subcategoría vieja: simulado de punta a
// punta con el <select> dependiente real (onExpenseCategoriaChange), no a
// mano -- así se prueba que el flujo de UI completo (no solo collectForm)
// termina mandando subcategoria: null cuando la vieja no pertenece a la nueva.
const cambioCategoriaForm = makeExpenseFormHarness();
cambioCategoriaForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
await cambioCategoriaForm.api.openForm('fixed-edit');
cambioCategoriaForm.element('field-categoria').value = 'Comida';
cambioCategoriaForm.api.onExpenseCategoriaChange();
assert.equal(cambioCategoriaForm.element('field-subcategoria').value, '',
  'Cambiar de categoría debe resetear la subcategoría elegida');
const cambioCategoriaValues = { ...heredarValues, categoria: 'Comida', subcategoria: '' };
const cambioCategoria = cambioCategoriaForm.api.collectForm('fixed-edit', fixedConAmbas, cambioCategoriaValues);
assert.equal(cambioCategoria.payload.categoria, 'Comida');
assert.equal(cambioCategoria.payload.subcategoria, null,
  'La subcategoria vieja ("Alquiler", de Hogar) no pertenece a la nueva categoría ("Comida") -- debe viajar null, no heredarse');

// Defensa en profundidad en el propio form: subcategoria sin categoria se
// rechaza aunque alguien fuerce ese estado salteando el <select> dependiente.
const subcatSinCategoriaValues = { ...heredarValues, categoria: '', subcategoria: 'Forzada' };
const subcatSinCategoria = fixedCatalogForm.api.collectForm('fixed-edit', fixedConAmbas, subcatSinCategoriaValues);
assert.ok(subcatSinCategoria.errors.subcategoria, 'No puede quedar subcategoria sin categoria, ni en el form');
const subcatSinCategoriaAlta = fixedCatalogForm.api.collectForm('fixed', null,
  { ...heredarValues, categoria: '', subcategoria: 'Forzada' });
assert.ok(subcatSinCategoriaAlta.errors.subcategoria, 'La misma regla aplica en alta');

console.log('Fijo: semántica omitido/null en edición (heredar, cambiar, vaciar, cascada, cambio de categoría) verificada');

// Combinación pedida por QA (brief t_38a7253f F1b-fix2, punto 3): categoría
// EN el catálogo pero subcategoría FUERA de él (no en la lista de esa
// categoría) en el form de edición -- a diferencia de la #345, donde ambas
// estaban afuera, acá solo la subcategoría quedó obsoleta.
const fixedCategoriaEnCatalogoSubFuera = { categoria: 'Hogar', subcategoria: 'Sub vieja ya no vigente' };
const mixtoHtml = markupApi.formMarkup('fixed-edit', fixedCategoriaEnCatalogoSubFuera, categoriesGastoFixture.categories);
assert.match(mixtoHtml, /<option value="Hogar" selected>Hogar<\/option>/, 'La categoría sigue en el catálogo, sin agregarse como extra');
assert.equal(mixtoHtml.match(/<option value="Hogar"/g).length, 1, 'La categoría del catálogo no debe duplicarse como extra');
assert.match(mixtoHtml, /<option value="Sub vieja ya no vigente" selected>Sub vieja ya no vigente<\/option>/,
  'La subcategoría fuera de catálogo se preserva como opción extra seleccionada');
for (const sub of categoriesGastoFixture.categories.find((c) => c.categoria === 'Hogar').subcategorias) {
  assert.match(mixtoHtml, new RegExp(`<option value="${sub}">${sub}</option>`),
    'Las subcategorías reales de Hogar deben seguir disponibles junto a la extra');
}

console.log('Fijo: combinación categoría-en-catálogo + subcategoría-fuera-de-catálogo en edición verificada');

// Fail-closed si el catálogo no carga (brief t_38a7253f F1b-fix2, hallazgo 1
// del revisor): a diferencia de gasto, NO hay texto libre de respaldo -- el
// form queda bloqueado (sin ningún campo, ni siquiera nombre/monto) con un
// aviso y un botón "Reintentar"; "Revisar" queda oculto e inalcanzable.
const fixedBlockedForm = makeExpenseFormHarness();
fixedBlockedForm.setCategoriesReply('throw');
await fixedBlockedForm.api.openForm('fixed');
const fixedBlockedHtml = fixedBlockedForm.element('form-fields').innerHTML;
assert.doesNotMatch(fixedBlockedHtml, /<select id="field-categoria"/);
assert.doesNotMatch(fixedBlockedHtml, /id="field-categoria"/, 'Sin catálogo no debe quedar ningún campo del form, ni siquiera texto libre');
assert.doesNotMatch(fixedBlockedHtml, /id="field-nombre"/, 'Nombre tampoco debe quedar editable: el form entero está bloqueado');
assert.match(fixedBlockedHtml, /No se pudo cargar el catálogo de categorías/);
assert.match(fixedBlockedHtml, /id="fixed-catalog-retry"/);
assert.equal(fixedBlockedForm.element('form-submit').hidden, true, '"Revisar" debe quedar oculto mientras el catálogo no cargó');
assert.equal(fixedBlockedForm.element('form-submit').disabled, true);
assert.equal(fixedBlockedForm.api.activeForm.catalogBlocked, true);

// Reintentar con la misma falla: se mantiene bloqueado, sin fallback.
fixedBlockedForm.setCategoriesReply('throw');
await fixedBlockedForm.api.retryFixedCatalog();
assert.equal(fixedBlockedForm.api.activeForm.catalogBlocked, true, 'Un segundo fallo debe seguir bloqueado');
assert.match(fixedBlockedForm.element('form-fields').innerHTML, /No se pudo cargar el catálogo de categorías/);
assert.equal(fixedBlockedForm.element('form-submit').hidden, true);

// Reintentar con éxito: recién ahí se pinta el form real con el catálogo.
fixedBlockedForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
await fixedBlockedForm.api.retryFixedCatalog();
assert.equal(fixedBlockedForm.api.activeForm.catalogBlocked, false);
const fixedRecoveredHtml = fixedBlockedForm.element('form-fields').innerHTML;
assert.match(fixedRecoveredHtml, /<select id="field-categoria"/);
assert.equal(fixedBlockedForm.element('form-submit').hidden, false);
assert.equal(fixedBlockedForm.element('form-submit').disabled, false);
assert.equal(fixedBlockedForm.element('form-submit').textContent, 'Revisar');

// Un catálogo vacío cae en el mismo bloqueo (no en texto libre).
const fixedEmptyCatalogForm = makeExpenseFormHarness();
fixedEmptyCatalogForm.setCategoriesReply({ status: 200, body: { categories: [] } });
await fixedEmptyCatalogForm.api.openForm('fixed');
assert.equal(fixedEmptyCatalogForm.api.activeForm.catalogBlocked, true, 'Un catálogo vacío también debe bloquear, no caer a texto libre');
assert.doesNotMatch(fixedEmptyCatalogForm.element('form-fields').innerHTML, /id="field-nombre"/);

// Un array no vacío puede estar malformado. Ninguna entrada inválida debe
// activar el formulario ni poblar la caché; el reintento usa el catálogo real.
for (const invalidCategories of [
  [{}],
  [{ categoria: 'Hogar' }],
  [{ categoria: '   ', subcategorias: [] }],
  [{ categoria: 7, subcategorias: [] }],
  [{ categoria: 'Hogar', subcategorias: 'Alquiler' }],
  [{ categoria: 'Hogar', subcategorias: [''] }],
  [{ categoria: 'Hogar', subcategorias: [null] }],
]) {
  const malformedForm = makeExpenseFormHarness();
  malformedForm.setCategoriesReply({ status: 200, body: { categories: invalidCategories } });
  await malformedForm.api.openForm('fixed');
  assert.equal(malformedForm.api.activeForm.catalogBlocked, true, 'Un catálogo inválido debe bloquear el fijo');
  assert.equal(malformedForm.element('form-submit').hidden, true);
  assert.doesNotMatch(malformedForm.element('form-fields').innerHTML, /undefined|id="field-nombre"/);
  malformedForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
  await malformedForm.api.retryFixedCatalog();
  assert.equal(malformedForm.api.activeForm.catalogBlocked, false, 'El catálogo válido debe permitir el reintento');
  assert.match(malformedForm.element('form-fields').innerHTML, /<select id="field-categoria"/);
  assert.equal(malformedForm.calls.filter((call) => call.path === '/api/categories?tipo=Gasto').length, 2,
    'La respuesta inválida no debe quedar cacheada');
}
const malformedExpense = makeExpenseFormHarness();
malformedExpense.setCategoriesReply({ status: 200, body: { categories: [{}] } });
await malformedExpense.api.openForm('expense');
assert.match(malformedExpense.element('form-fields').innerHTML, /list="expense-categories"/,
  'Gastos conserva su fallback de texto libre ante un catálogo malformado');
assert.doesNotMatch(malformedExpense.element('form-fields').innerHTML, /undefined/);

console.log('Categorías de fijo: select opcional dependiente, caché compartida con gasto y fail-closed con reintento verificados');

// Regresión (revisor, t_38a7253f F1b-fix4 hallazgo 1): el bloqueo fail-closed
// de fijos oculta "Revisar" (renderFixedCatalogBlocked), pero openForm/closeForm
// no restauraban `hidden` -- quedaba oculto para cualquier formulario abierto
// después, aunque su catálogo cargara bien.
const hiddenLeakForm = makeExpenseFormHarness();
hiddenLeakForm.setCategoriesReply('throw');
await hiddenLeakForm.api.openForm('fixed');
assert.equal(hiddenLeakForm.element('form-submit').hidden, true, 'Catálogo fallido: "Revisar" oculto (fail-closed)');
hiddenLeakForm.api.closeForm();
hiddenLeakForm.setCategoriesReply({ status: 200, body: categoriesGastoFixture });
await hiddenLeakForm.api.openForm('expense');
assert.equal(hiddenLeakForm.element('form-submit').hidden, false,
  '"Revisar" debe volver a mostrarse al abrir otro formulario, aunque el anterior haya quedado bloqueado');
assert.equal(hiddenLeakForm.element('form-submit').disabled, false);

hiddenLeakForm.api.closeForm();
await hiddenLeakForm.api.openForm('fixed');
assert.equal(hiddenLeakForm.element('form-submit').hidden, false,
  'Lo mismo al reabrir un fijo con catálogo OK tras un fijo bloqueado previo');
assert.equal(hiddenLeakForm.element('form-submit').disabled, false);

console.log('Fail-closed de fijos: "Revisar" no queda oculto para formularios posteriores (regresión t_38a7253f F1b-fix4)');

// ── CARRERA ASYNC EN openForm (revisor 3f12e4c8, t_ce790609 #1) ─────────────
// openForm('expense') espera el catálogo con `await`. Si dos aperturas se
// superponen, el modal se cierra antes de resolver, o se abre otro formulario
// mientras el catálogo sigue pendiente, una resolución tardía (éxito o fallo)
// nunca debe reconstruir el DOM ni tocar activeForm de una apertura que ya no
// es la vigente. A diferencia de makeExpenseFormHarness, acá el fetch de
// categorías queda deliberadamente pendiente hasta que el test lo resuelve,
// para poder ordenar las resoluciones fuera de orden.
function makeRaceExpenseHarness() {
  const calls = [];
  const deferredCategories = [];
  const mockFetch = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/categories?tipo=Gasto') {
      return new Promise((resolve, reject) => { deferredCategories.push({ resolve, reject }); });
    }
    throw new Error(`Mock sin respuesta: ${path}`);
  };
  const elements = new Map();
  // addEventListener REAL (no-op descartado): guarda los handlers para poder
  // despachar un keydown 'Escape' de verdad sobre #form-modal, en vez de
  // llamar closeForm() directamente desde el test.
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', hidden: false, disabled: false,
      value: '', isConnected: true, listeners: {}, focus() { document.activeElement = this; },
      addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); },
      querySelector: () => ({ focus() { document.activeElement = this; } }), querySelectorAll: () => [] });
    return elements.get(id);
  };
  const document = { getElementById: element, querySelectorAll: () => [], activeElement: null };
  const api = runInNewContext(`'use strict';
    let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
    let activeForm = null, categoriesGastoCache = null, activeExpenseCatalog = null, currentView = 'gastos';
    const DATA = { gastos: [], ingresos: [], fijos: [] };
    ${raceExpenseFormSliceSetup}
    ({ openForm, closeForm, formMarkup, onExpenseCategoriaChange, collectForm, writeForm,
       get activeForm() { return activeForm; },
       get activeExpenseCatalog() { return activeExpenseCatalog; } })`,
    { document, fetch: mockFetch, Date, Number, Math, String, Array, Set,
      FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values || {}); } } });
  return {
    api, calls, element, document,
    categoriesRequests() { return deferredCategories.length; },
    resolveAt(index, body) { deferredCategories[index].resolve({ ok: true, status: 200, json: async () => body }); },
    rejectAt(index, err) { deferredCategories[index].reject(err || new Error('Sin red en prueba sintética (tardía)')); },
    // Despacha un keydown 'Escape' real sobre #form-modal usando el handler
    // que app.js registró de verdad vía addEventListener.
    dispatchEscape() {
      const modal = element('form-modal');
      const event = { key: 'Escape', preventDefault() {}, currentTarget: modal };
      (modal.listeners.keydown || []).forEach((handler) => handler(event));
    },
  };
}

// 1) Doble apertura de 'expense' con resoluciones fuera de orden: la segunda
//    resuelve OK primero; después, la primera falla tarde. La UI y el
//    activeForm de la segunda deben quedar intactos, sin caer al fallback.
const race1 = makeRaceExpenseHarness();
const open1 = race1.api.openForm('expense');
const open2 = race1.api.openForm('expense');
assert.equal(race1.categoriesRequests(), 2, 'Dos aperturas en carrera deben disparar dos pedidos de catálogo');

race1.resolveAt(1, categoriesGastoFixture);
await open2;
const htmlAfterSecond = race1.element('form-fields').innerHTML;
assert.match(htmlAfterSecond, /<select id="field-categoria"/, 'La segunda apertura debe pintar el catálogo recibido');
assert.equal(race1.element('form-modal').hidden, false);
assert.equal(race1.api.activeForm.kind, 'expense');
assert.equal(race1.api.activeForm.confirmed, false);
assert.equal(Array.from(race1.api.activeExpenseCatalog).length, categoriesGastoFixture.categories.length);
const activeFormSnapshotAfterSecond = JSON.stringify(race1.api.activeForm);
const focusAfterSecond = race1.document.activeElement;
assert.ok(focusAfterSecond, 'La segunda apertura exitosa debe mover el foco dentro del modal');

race1.rejectAt(0, new Error('Sin red en prueba sintética (tardía)'));
await open1;
assert.equal(race1.element('form-fields').innerHTML, htmlAfterSecond,
  'El fallo tardío de la primera apertura no debe reemplazar el formulario de la segunda por el fallback de texto libre');
assert.doesNotMatch(race1.element('form-fields').innerHTML, /No se pudo cargar el catálogo/,
  'No debe aparecer el aviso de fallback por una apertura que ya no es la vigente');
assert.equal(race1.element('form-modal').hidden, false);
assert.equal(JSON.stringify(race1.api.activeForm), activeFormSnapshotAfterSecond,
  'activeForm de la segunda apertura debe quedar intacto ante el fallo tardío de la primera');
assert.equal(race1.document.activeElement, focusAfterSecond, 'Un fallo tardío no debe robar el foco de la apertura vigente');

// 2) Cancelar (closeForm(), como hace el click real de #form-close) antes de
//    que resuelva el catálogo: la resolución tardía no debe reabrirlo ni
//    modificar nada, y el foco debe haber vuelto al disparador original.
const race2 = makeRaceExpenseHarness();
const trigger = race2.element('add-expense-btn');
race2.document.activeElement = trigger;
const open3 = race2.api.openForm('expense');
assert.equal(race2.categoriesRequests(), 1);
assert.equal(race2.api.activeForm.returnFocus, trigger, 'openForm debe recordar el foco de origen');
race2.api.closeForm();
assert.equal(race2.element('form-modal').hidden, true);
assert.equal(race2.api.activeForm, null);
assert.equal(race2.document.activeElement, trigger, 'Cerrar (Escape) antes de resolver el catálogo debe devolver el foco al disparador');
const fieldsHtmlBeforeLateResolve = race2.element('form-fields').innerHTML;

race2.resolveAt(0, categoriesGastoFixture);
await open3;
assert.equal(race2.element('form-modal').hidden, true, 'Una resolución tardía no debe reabrir el modal');
assert.equal(race2.element('form-fields').innerHTML, fieldsHtmlBeforeLateResolve,
  'Una resolución tardía no debe reconstruir el formulario tras cerrar el modal');
assert.equal(race2.api.activeForm, null, 'activeForm sigue en null: la apertura cerrada no se reinstala');
assert.equal(race2.document.activeElement, trigger, 'La resolución tardía no debe robar el foco tras cerrar');

// 3) Abrir otro formulario (ingreso) mientras el catálogo de gasto sigue
//    pendiente: la resolución tardía no debe pisar el formulario vigente.
const race3 = makeRaceExpenseHarness();
const open4 = race3.api.openForm('expense');
assert.equal(race3.categoriesRequests(), 1);
race3.api.openForm('income');
assert.equal(race3.element('form-title').textContent, 'Agregar ingreso');
const incomeHtml = race3.element('form-fields').innerHTML;
assert.match(incomeHtml, /id="field-persona"/);
assert.equal(race3.api.activeForm.kind, 'income');

race3.resolveAt(0, categoriesGastoFixture);
await open4;
assert.equal(race3.element('form-title').textContent, 'Agregar ingreso',
  'El título debe seguir siendo el del formulario vigente (ingreso)');
assert.equal(race3.element('form-fields').innerHTML, incomeHtml,
  'El formulario de ingreso no debe reemplazarse por el de gasto cuando el catálogo resuelve tarde');
assert.equal(race3.api.activeForm.kind, 'income');

// 4) Escape REAL (keydown, no closeForm() directo) con el catálogo pendiente:
//    el modal debe estar visible en estado de carga desde el primer instante
//    (antes de que el catálogo resuelva), con foco dentro del modal y sin
//    campos ni submit habilitados. El keydown debe pasar por el listener que
//    app.js registró de verdad sobre #form-modal.
const race4 = makeRaceExpenseHarness();
const trigger4 = race4.element('add-expense-btn');
race4.document.activeElement = trigger4;
const open5 = race4.api.openForm('expense');
assert.equal(race4.element('form-modal').hidden, false,
  'El modal debe mostrarse de inmediato en estado de carga, sin esperar el catálogo');
assert.match(race4.element('form-fields').innerHTML, /Cargando categorías/);
assert.doesNotMatch(race4.element('form-fields').innerHTML, /<select|<input/,
  'Durante la carga no debe haber campos editables');
assert.equal(race4.element('form-submit').disabled, true, 'Sin submit habilitado durante la carga');
assert.equal(race4.element('form-close').disabled, false, 'Cancelar debe quedar habilitado durante la carga');
assert.equal(race4.document.activeElement, race4.element('form-close'),
  'El foco debe quedar dentro del modal (en Cancelar) mientras carga el catálogo');

race4.dispatchEscape();
assert.equal(race4.element('form-modal').hidden, true, 'Escape real debe cerrar el modal con el catálogo pendiente');
assert.equal(race4.api.activeForm, null, 'Escape invalida la apertura pendiente (activeForm = null)');
assert.equal(race4.document.activeElement, trigger4, 'Escape debe devolver el foco al disparador original');
const fieldsHtmlAfterEscape = race4.element('form-fields').innerHTML;

race4.resolveAt(0, categoriesGastoFixture);
await open5;
assert.equal(race4.element('form-modal').hidden, true,
  'La resolución tardía exitosa de una apertura cancelada con Escape no debe reabrir el modal');
assert.equal(race4.element('form-fields').innerHTML, fieldsHtmlAfterEscape,
  'No debe reconstruir el formulario tras un Escape real');
assert.equal(race4.api.activeForm, null);
assert.equal(race4.document.activeElement, trigger4, 'La resolución tardía no debe robar el foco tras Escape');

// 5) Igual, pero el catálogo falla tarde después del Escape real: tampoco
//    debe reabrir el modal ni mostrar el aviso de fallback.
const race5 = makeRaceExpenseHarness();
const trigger5 = race5.element('add-expense-btn');
race5.document.activeElement = trigger5;
const open6 = race5.api.openForm('expense');
race5.dispatchEscape();
assert.equal(race5.element('form-modal').hidden, true);
const fieldsHtmlAfterEscape5 = race5.element('form-fields').innerHTML;

race5.rejectAt(0, new Error('Sin red en prueba sintética (tardía)'));
await open6;
assert.equal(race5.element('form-modal').hidden, true, 'Un fallo tardío tras Escape no debe reabrir el modal');
assert.equal(race5.element('form-fields').innerHTML, fieldsHtmlAfterEscape5,
  'Un fallo tardío tras Escape no debe reconstruir el DOM');
assert.doesNotMatch(race5.element('form-fields').innerHTML, /No se pudo cargar el catálogo/,
  'No debe aparecer el aviso de fallback por una apertura ya cancelada');
assert.equal(race5.api.activeForm, null);
assert.equal(race5.document.activeElement, trigger5, 'El fallo tardío no debe robar el foco tras Escape');

// 6) Doble apertura con catálogo pendiente (revisor bdc70c13, t_ce790609): la
//    primera apertura mueve el foco a Cancelar mientras carga; una segunda
//    openForm('expense') disparada en ese estado NO debe tomar Cancelar como
//    disparador. El returnFocus debe seguir siendo "Agregar gasto", y Escape
//    real debe devolver el foco ahí.
const race6 = makeRaceExpenseHarness();
const trigger6 = race6.element('add-expense-btn');
race6.document.activeElement = trigger6;
const open7 = race6.api.openForm('expense');
assert.equal(race6.api.activeForm.returnFocus, trigger6, 'Primera apertura debe recordar el disparador original');
assert.equal(race6.document.activeElement, race6.element('form-close'), 'La primera apertura mueve el foco a Cancelar mientras carga');

const open8 = race6.api.openForm('expense');
assert.equal(race6.categoriesRequests(), 2, 'La segunda apertura dispara un segundo pedido de catálogo');
assert.equal(race6.api.activeForm.returnFocus, trigger6,
  'Una segunda apertura con el modal ya abierto debe conservar el returnFocus original, no Cancelar');

race6.dispatchEscape();
assert.equal(race6.element('form-modal').hidden, true, 'Escape real debe cerrar el modal con dos aperturas pendientes');
assert.equal(race6.api.activeForm, null);
assert.equal(race6.document.activeElement, trigger6, 'Escape con dos aperturas pendientes debe devolver el foco al disparador original');

race6.resolveAt(0, categoriesGastoFixture);
race6.resolveAt(1, categoriesGastoFixture);
await open7;
await open8;
assert.equal(race6.element('form-modal').hidden, true, 'Resoluciones tardías de ambas aperturas no deben reabrir el modal');
assert.equal(race6.document.activeElement, trigger6, 'El foco sigue en el disparador original tras las resoluciones tardías');

// 7) Igual, pero cerrando con Cancelar (closeForm()) en vez de Escape.
const race7 = makeRaceExpenseHarness();
const trigger7 = race7.element('add-expense-btn');
race7.document.activeElement = trigger7;
const open9 = race7.api.openForm('expense');
const open10 = race7.api.openForm('expense');
assert.equal(race7.api.activeForm.returnFocus, trigger7,
  'Una segunda apertura con el modal ya abierto debe conservar el returnFocus original ante Cancelar también');

race7.api.closeForm();
assert.equal(race7.element('form-modal').hidden, true);
assert.equal(race7.api.activeForm, null);
assert.equal(race7.document.activeElement, trigger7, 'Cancelar con dos aperturas pendientes debe devolver el foco al disparador original');

race7.resolveAt(0, categoriesGastoFixture);
race7.resolveAt(1, categoriesGastoFixture);
await open9;
await open10;
assert.equal(race7.element('form-modal').hidden, true, 'Resoluciones tardías tras Cancelar no deben reabrir el modal');
assert.equal(race7.document.activeElement, trigger7, 'El foco sigue en el disparador original tras las resoluciones tardías');

console.log('openForm: carrera entre aperturas de gasto resuelta por identidad (no por kind); cierre/Cancelar y apertura de otro formulario durante el await del catálogo, Escape real con estado de carga, y preservación del returnFocus original ante doble apertura, verificados');

// ── INVENTARIO (S4 cierre) ───────────────────────────────────────────────
// inventoryAvailable es independiente de liveMode: si /api/health no declara
// la capability 'inventory', el resto del dashboard sigue en vivo y solo la
// pestaña Inventario queda en solo lectura/aviso (ver updateAvailability).
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies();
await api.loadAll();
assert.equal(api.state.liveMode, true, 'Sin la capability inventory el resto del dashboard debe seguir en vivo');
assert.equal(api.state.inventoryAvailable, false);
assert.equal(api.DATA.inventario.length, 0);
assert.equal(element('inventario-notice').hidden, false);
assert.match(element('inventario-notice').textContent, /inventory/);
assert.equal(calls.filter((call) => call.path === '/api/inventory').length, 0,
  'Sin la capability inventory no debe pedirse /api/inventory');

const inventoryItem = { id: 101, nombre: 'Notebook ThinkPad', categoria: 'Electrónica',
  ubicacion: 'Living', valor_estimado: 450000, fecha_adquisicion: '2024-03-01', notas: 'Comprada usada' };
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed', 'inventory'] });
liveReplies();
reply('/api/inventory', 200, { inventory: [inventoryItem] });
await api.loadAll();
assert.equal(api.state.liveMode, true);
assert.equal(api.state.inventoryAvailable, true);
assert.equal(api.DATA.inventario.length, 1);
assert.equal(api.DATA.inventario[0].id, '101');
assert.equal(element('inventario-notice').hidden, true);

// Restablecer el estado "sin inventory" para no afectar al resto de las pruebas de api.loadAll.
reply('/api/health', 200, { ok: true, mode: 'live', capabilities: ['expenses', 'income', 'fixed'] });
liveReplies();
await api.loadAll();

// Payloads (POST/PATCH/DELETE) con funciones reales de collectForm/describeForm/routeForForm/writeForm.
// Campos de paridad con el legacy (t_0e38e74e): precio_ars, cotizacion_usd_compra,
// precio_usd_compra, proporcion_jd, precio_venta_estimado_usd, estado.
const inventoryValues = { nombre: 'Notebook ThinkPad', categoria: 'Electrónica', ubicacion: 'Living',
  valor_estimado: '450000', fecha_adquisicion: '2024-03-01', notas: 'Comprada usada',
  precio_ars: '450000', cotizacion_usd_compra: '900', precio_usd_compra: '500',
  precio_venta_estimado_usd: '400', proporcion_jd: '60', estado: 'Activo' };
const collectedInventory = api.collectForm('inventory', null, inventoryValues);
assert.equal(Object.keys(collectedInventory.errors).length, 0);
assert.equal(collectedInventory.payload.nombre, 'Notebook ThinkPad');
assert.equal(collectedInventory.payload.valor_estimado, 450000);
assert.equal(collectedInventory.payload.precio_ars, 450000);
assert.equal(collectedInventory.payload.cotizacion_usd_compra, 900);
assert.equal(collectedInventory.payload.precio_usd_compra, 500);
assert.equal(collectedInventory.payload.precio_venta_estimado_usd, 400);
assert.equal(collectedInventory.payload.proporcion_jd, 60);
assert.equal(collectedInventory.payload.estado, 'Activo');
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, nombre: '  ' }).errors.nombre);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, valor_estimado: '-5' }).errors.valor_estimado);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, valor_estimado: '0' }).errors.valor_estimado);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, fecha_adquisicion: 'no-es-fecha' }).errors.fecha_adquisicion);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, estado: 'Perdido' }).errors.estado,
  'Un estado fuera de INVENTARIO_ESTADOS debe rechazarse');
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, proporcion_jd: '150' }).errors.proporcion_jd);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, proporcion_jd: '-1' }).errors.proporcion_jd);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, precio_ars: '-1' }).errors.precio_ars);
assert.ok(api.collectForm('inventory', null, { ...inventoryValues, cotizacion_usd_compra: 'no-es-numero' }).errors.cotizacion_usd_compra);
// Los montos opcionales de paridad admiten 0 (a diferencia de valor_estimado, que no).
const zeroMoney = api.collectForm('inventory', null, { ...inventoryValues, precio_usd_compra: '0' });
assert.equal(Object.keys(zeroMoney.errors).length, 0);
assert.equal(zeroMoney.payload.precio_usd_compra, 0);
const collectedInventoryNoFecha = api.collectForm('inventory', null,
  { ...inventoryValues, fecha_adquisicion: '', precio_ars: '', cotizacion_usd_compra: '', precio_usd_compra: '',
    precio_venta_estimado_usd: '', proporcion_jd: '', estado: '' });
assert.equal(Object.keys(collectedInventoryNoFecha.errors).length, 0);
for (const field of ['fecha_adquisicion', 'precio_ars', 'cotizacion_usd_compra', 'precio_usd_compra',
  'precio_venta_estimado_usd', 'proporcion_jd', 'estado']) {
  assert.equal(field in collectedInventoryNoFecha.payload, false,
    `${field} es opcional: vacío no debe viajar en el payload`);
}

// Edición (t_0e38e74e, hallazgo 3 del revisor 46d4f3d5): vaciar un campo
// opcional en 'inventory-edit' debe mandar `null` explícito para que el
// PATCH lo borre, a diferencia del alta (arriba), que sigue omitiéndolo.
const inventoryRowParaEdicion = { id: largeId, nombre: 'Notebook ThinkPad' };
const collectedInventoryEditVaciado = api.collectForm('inventory-edit', inventoryRowParaEdicion,
  { ...inventoryValues, categoria: '', ubicacion: '', fecha_adquisicion: '', notas: '',
    precio_ars: '', cotizacion_usd_compra: '', precio_usd_compra: '',
    precio_venta_estimado_usd: '', proporcion_jd: '' });
assert.equal(Object.keys(collectedInventoryEditVaciado.errors).length, 0);
for (const field of ['categoria', 'ubicacion', 'fecha_adquisicion', 'notas', 'precio_ars',
  'cotizacion_usd_compra', 'precio_usd_compra', 'precio_venta_estimado_usd', 'proporcion_jd']) {
  assert.equal(collectedInventoryEditVaciado.payload[field], null,
    `${field} vaciado en una edición debe mandar null explícito, no omitirse`);
}
// 'estado' no tiene forma de quedar vacío en la UI (es un <select> con default
// 'Activo'); se sigue mandando tal cual, sin lógica de null para este campo.
assert.equal(collectedInventoryEditVaciado.payload.estado, 'Activo');

const inventoryRow = { id: largeId, nombre: 'Notebook ThinkPad', categoria: 'Electrónica',
  ubicacion: 'Living', valor_estimado: 450000, fecha_adquisicion: '2024-03-01', notas: 'Comprada usada',
  estado: 'Vendido' };
assert.match(api.describeForm('inventory', null, collectedInventory.payload), /Notebook ThinkPad/);
assert.match(api.describeForm('inventory', null, collectedInventory.payload), /Estado Activo/);
assert.match(api.describeForm('inventory', null, collectedInventory.payload), /U\$D 500 de compra/);
assert.match(api.describeForm('inventory', null, collectedInventory.payload), /60% JD \/ 40% Pinki/);
assert.match(api.describeForm('inventory-delete', inventoryRow, null), /Notebook ThinkPad/);
assert.match(api.describeForm('inventory-delete', inventoryRow, null), /450000/);
assert.match(api.describeForm('inventory-delete', inventoryRow, null), /estado Vendido/);
assert.equal(api.routeForForm('inventory', null)[0], 'POST');
assert.equal(api.routeForForm('inventory', null)[1], '/api/inventory');
assert.equal(api.routeForForm('inventory-edit', { id: largeId })[1], `/api/inventory/${encodeURIComponent(largeId)}`);
assert.equal(api.routeForForm('inventory-delete', { id: maxId })[1], `/api/inventory/${encodeURIComponent(maxId)}`);
assert.throws(() => api.routeForForm('inventory-delete', { id: 9007199254740992 }), /inseguro/,
  'El ID como string debe pasar por canonicalId también para inventario');

reply('/api/inventory', 201, { inventory: { ...inventoryRow, id: largeId } });
await api.writeForm('inventory', null, collectedInventory.payload);
let inventoryCall = calls.at(-1);
assert.equal(inventoryCall.path, '/api/inventory');
assert.equal(inventoryCall.options.method, 'POST');
assert.equal(inventoryCall.options.credentials, 'same-origin');
assert.deepEqual(JSON.parse(inventoryCall.options.body), JSON.parse(JSON.stringify(collectedInventory.payload)));
const sentInventoryBody = JSON.parse(inventoryCall.options.body);
assert.equal(typeof sentInventoryBody.precio_ars, 'number');
assert.equal(typeof sentInventoryBody.proporcion_jd, 'number');
assert.equal(sentInventoryBody.estado, 'Activo');

const collectedInventoryEdit = api.collectForm('inventory-edit', inventoryRow,
  { ...inventoryValues, valor_estimado: '500000', estado: 'Vendido', proporcion_jd: '25' });
reply(`/api/inventory/${largeId}`, 200, { inventory: { ...inventoryRow, valor_estimado: 500000, estado: 'Vendido' } });
await api.writeForm('inventory-edit', inventoryRow, collectedInventoryEdit.payload);
inventoryCall = calls.at(-1);
assert.equal(inventoryCall.path, `/api/inventory/${largeId}`);
assert.equal(inventoryCall.options.method, 'PATCH');
assert.equal(JSON.parse(inventoryCall.options.body).valor_estimado, 500000);
assert.equal(JSON.parse(inventoryCall.options.body).estado, 'Vendido');
assert.equal(JSON.parse(inventoryCall.options.body).proporcion_jd, 25);

reply(`/api/inventory/${largeId}`, 200, { inventory: { ...inventoryRow, fecha_adquisicion: null, precio_ars: null } });
await api.writeForm('inventory-edit', inventoryRow, collectedInventoryEditVaciado.payload);
inventoryCall = calls.at(-1);
const vaciadoBody = JSON.parse(inventoryCall.options.body);
assert.equal(vaciadoBody.fecha_adquisicion, null, 'El PATCH debe mandar null explícito, no omitir el campo vaciado');
assert.equal(vaciadoBody.precio_ars, null);

reply(`/api/inventory/${largeId}`, 200, { deleted: true, id: largeId });
await api.writeForm('inventory-delete', inventoryRow, null);
inventoryCall = calls.at(-1);
assert.equal(inventoryCall.path, `/api/inventory/${largeId}`);
assert.equal(inventoryCall.options.method, 'DELETE');
assert.equal('body' in inventoryCall.options, false);

console.log('Inventario: campos de paridad con el legacy (precio_ars, cotizacion_usd_compra, precio_usd_compra, proporcion_jd, precio_venta_estimado_usd, estado), validaciones de rango y escritura (POST/PATCH/DELETE) verificados con las funciones reales de app.js');

// Sugerencia de USD de compra = ARS / cotización: no debe pisar un valor
// ingresado a mano (t_0e38e74e, hallazgo 4 del revisor 46d4f3d5). Funciones
// REALES de app.js (onInventoryUsdSugerido/onInventoryUsdEdited), con el
// flag `inventoryUsdEditedManually` expuesto para asertar su estado.
const usdFields = new Map([
  ['field-precio_ars', { value: '' }],
  ['field-cotizacion_usd_compra', { value: '' }],
  ['field-precio_usd_compra', { value: '' }],
]);
const usdSugeridoApi = runInNewContext(`
let inventoryUsdEditedManually = false;
${slice('function onInventoryUsdSugerido(', 'function validFixedPercent(')}
({ onInventoryUsdSugerido, onInventoryUsdEdited,
   get manual() { return inventoryUsdEditedManually; },
   set manual(v) { inventoryUsdEditedManually = v; } })`,
  { document: { getElementById: (id) => usdFields.get(id) || null }, Number });

usdFields.get('field-precio_ars').value = '1000';
usdFields.get('field-cotizacion_usd_compra').value = '1000';
usdSugeridoApi.onInventoryUsdSugerido();
assert.equal(usdFields.get('field-precio_usd_compra').value, '1.00',
  'Con el campo USD vacío, debe sugerir ARS / cotización');
assert.equal(usdSugeridoApi.manual, false);

// El usuario edita el USD a mano: no debe pisarse aunque cambien ARS/cotización.
usdSugeridoApi.onInventoryUsdEdited();
assert.equal(usdSugeridoApi.manual, true);
usdFields.get('field-precio_usd_compra').value = '500';
usdFields.get('field-precio_ars').value = '2000';
usdSugeridoApi.onInventoryUsdSugerido();
assert.equal(usdFields.get('field-precio_usd_compra').value, '500',
  'Un USD editado a mano no debe pisarse al cambiar ARS/cotización, aunque el campo tenga contenido');

// Si el usuario vacía el USD después de haberlo editado a mano, la
// sugerencia vuelve a completarlo (campo vacío siempre dispara la sugerencia).
usdFields.get('field-precio_usd_compra').value = '';
usdSugeridoApi.onInventoryUsdSugerido();
assert.equal(usdFields.get('field-precio_usd_compra').value, '2.00');

console.log('Inventario: la sugerencia de USD de compra no pisa un valor editado a mano (onInventoryUsdSugerido/onInventoryUsdEdited) verificado con las funciones reales de app.js');

// Fix al hallazgo 3 del revisor fc195491: si el bien ya tiene
// precio_usd_compra != null al abrir el formulario de edición,
// inventoryUsdEditedManually debe iniciar en `true` (no se autosugiere).
// Solo se parte de `false` si el campo está vacío. Funciones REALES de
// app.js (openForm/onInventoryUsdSugerido), con el flag expuesto.
const usdPrefillElements = new Map();
const usdPrefillElement = (id) => {
  if (!usdPrefillElements.has(id)) usdPrefillElements.set(id, { textContent: '', innerHTML: '',
    hidden: false, disabled: false, value: '', focus() {}, addEventListener() {},
    querySelector: () => ({ focus() {} }), querySelectorAll: () => [] });
  return usdPrefillElements.get(id);
};
const usdPrefillDocument = { getElementById: usdPrefillElement, querySelectorAll: () => [], activeElement: null };
const bienConUsdPrecargado = { id: 201, nombre: 'Bien con USD precargado', categoria: 'Hogar',
  precio_usd_compra: 500, precio_ars: 450000, cotizacion_usd_compra: 900, proporcion_jd: 50 };
const bienSinUsd = { id: 202, nombre: 'Bien sin USD', categoria: 'Hogar',
  precio_usd_compra: null, precio_ars: 450000, cotizacion_usd_compra: 900, proporcion_jd: 50 };
const usdPrefillApi = runInNewContext(`
let activeForm = null;
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false, inventoryAvailable = true;
const DATA = { gastos: [], ingresos: [], fijos: [], inventario: [bienConUsdPrecargado, bienSinUsd] };
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('const INVENTARIO_ESTADOS = ', 'const iconFor = ')}
${slice('const escapeHtml = ', 'const fmtARS = ')}
let inventoryUsdEditedManually = false;
${slice('function formField(', 'function closeForm(')}
${slice('function syncCustomProportion(', 'function validMoney(')}
({ openForm, onInventoryUsdSugerido,
   get manual() { return inventoryUsdEditedManually; } })`,
  { document: usdPrefillDocument, bienConUsdPrecargado, bienSinUsd, Number });

await usdPrefillApi.openForm('inventory-edit', 201);
assert.equal(usdPrefillApi.manual, true,
  'Con precio_usd_compra != null precargado, inventoryUsdEditedManually debe iniciar en true');
usdPrefillElement('field-precio_ars').value = '999999';
usdPrefillElement('field-cotizacion_usd_compra').value = '1';
usdPrefillElement('field-precio_usd_compra').value = '500';
usdPrefillApi.onInventoryUsdSugerido();
assert.equal(usdPrefillElement('field-precio_usd_compra').value, '500',
  'Un USD precargado al abrir el formulario no debe pisarse al cambiar ARS/cotización');

await usdPrefillApi.openForm('inventory-edit', 202);
assert.equal(usdPrefillApi.manual, false,
  'Con el campo vacío (precio_usd_compra=null), inventoryUsdEditedManually debe iniciar en false y sí autosugerir');

console.log('Inventario: inventoryUsdEditedManually se inicializa según precio_usd_compra precargado al editar (hallazgo 3 del revisor fc195491) verificado con openForm real de app.js');

// Fix al hallazgo 4 del revisor fc195491: proporcion_jd=null en edición debe
// quedar vacío con placeholder, nunca precargado en 50 — en el alta sigue el
// default 50. Verificado directamente sobre formMarkup (función pura).
const inventoryMarkupApi = runInNewContext(`
function todayLocalISO() { return '2026-10-17'; }
const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
${slice('const INVENTARIO_ESTADOS = ', 'const iconFor = ')}
${slice('function formField(', 'async function openForm(')}
({ formMarkup })`, { DATA: { inventario: [] } });

const bienSinProporcion = { id: 55, nombre: 'Bien sin dato', categoria: 'Hogar', proporcion_jd: null };
const markupSinProporcion = inventoryMarkupApi.formMarkup('inventory-edit', bienSinProporcion);
assert.match(markupSinProporcion, /id="field-proporcion_jd"[^>]*value=""/,
  'proporcion_jd=null en edición no debe precargarse en 50');
assert.match(markupSinProporcion, /placeholder="sin dato, 50\/50 por defecto en cálculos"/);

const bienConProporcion = { id: 56, nombre: 'Bien con dato', categoria: 'Hogar', proporcion_jd: 30 };
const markupConProporcion = inventoryMarkupApi.formMarkup('inventory-edit', bienConProporcion);
assert.match(markupConProporcion, /id="field-proporcion_jd"[^>]*value="30"/);
assert.doesNotMatch(markupConProporcion, /placeholder="sin dato/);

const markupAlta = inventoryMarkupApi.formMarkup('inventory', null);
assert.match(markupAlta, /id="field-proporcion_jd"[^>]*value="50"/,
  'El alta sigue precargando el default 50, solo la edición respeta el null');

console.log('Inventario: proporcion_jd=null en edición queda vacío con placeholder en vez de 50 (hallazgo 4 del revisor fc195491) verificado con formMarkup real de app.js');

// ── INVENTARIO: cards (cotización + reparto JD/Pinki), filtro de estado y
// escape de XSS en descripción/notas ────────────────────────────────────────
// renderInventarioView y sus helpers (renderInventarioOptions, renderInventarioCards,
// getInventarioCotizacion/setInventarioCotizacion, setInventarioFiltroEstado) se
// verifican con las funciones REALES de app.js, no copias.
// Identidad de nodo (revisor 7d63437e, hallazgo 3): en un DOM real, reasignar
// innerHTML de #inventario-content destruye y recrea TODOS sus hijos —
// incluidos los <input> de cotización inline y las celdas de Reventa/Venta
// JD/Pinki de cada fila. El stub simula eso invalidando esos nodos "de fila"
// cada vez que se reescribe el innerHTML del contenedor, para que un test
// pueda detectar un re-render completo comparando identidad de objeto
// (===) antes/después, no solo el valor textual.
const inventarioRowScopedPrefixes = ['inv-cot-', 'inv-reventa-', 'inv-venta-jd-', 'inv-venta-pinki-'];
const isInventarioRowScoped = (id) => inventarioRowScopedPrefixes.some((prefix) => id.startsWith(prefix));
const inventarioElements = new Map();
const inventarioElement = (id) => {
  if (!inventarioElements.has(id)) {
    if (id === 'inventario-content') {
      inventarioElements.set(id, { hidden: false, value: '', _html: '',
        get innerHTML() { return this._html; },
        set innerHTML(html) {
          this._html = html;
          for (const key of [...inventarioElements.keys()]) {
            if (isInventarioRowScoped(key)) inventarioElements.delete(key);
          }
        } });
    } else {
      inventarioElements.set(id, { textContent: '', innerHTML: '', hidden: false, value: '' });
    }
  }
  return inventarioElements.get(id);
};
const estadoFilterButtons = ['Activo', 'Vendido', 'Donado', 'Desechado', ''].map((estado) => ({
  dataset: { estado }, active: false,
  classList: { toggle(name, value) { if (name === 'active') this.owner.active = value; } },
  setAttribute() {},
}));
estadoFilterButtons.forEach((b) => { b.classList.owner = b; });
const inventarioDocument = {
  getElementById: inventarioElement,
  querySelectorAll: (selector) => selector === '#inventario-estado-filter .persona-btn' ? estadoFilterButtons : [],
  activeElement: null,
};
const inventarioData = { inventario: [] };
let inventarioStore = {};
const inventarioLocalStorage = {
  getItem: (key) => (key in inventarioStore ? inventarioStore[key] : null),
  setItem: (key, value) => { inventarioStore[key] = String(value); },
};
const inventarioApi = runInNewContext(`
let liveMode = true, inventoryAvailable = true, writePending = false, reloadPending = false, reloadFailed = false;
let currentView = 'inventario', inventarioFiltroEstado = 'Activo', inventarioRowsRendered = [];
function fmtARS(value) { return '$' + value; }
function fmtUSD(value) { return 'U$D ' + value; }
${slice('const INVENTARIO_ESTADOS = ', 'const iconFor = ')}
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function getInventarioCotizacion(', '// ── IMPRIMIR')}
({ renderInventarioView, renderInventarioCards, setInventarioCotizacion, setInventarioFiltroEstado,
   getInventarioCotizacion, setLive(v) { liveMode = v; }, setInventoryAvailable(v) { inventoryAvailable = v; },
   get filtroEstado() { return inventarioFiltroEstado; } })`,
  { document: inventarioDocument, DATA: inventarioData, localStorage: inventarioLocalStorage });

// invItemJD: USD derivado (sin precio_usd_compra) + proporcion_jd ausente
// (default 50/50) — con precio_ars=138000 y cotizacion_usd_compra=1465,
// usdCompra = 94.19795... Con cotHoy=1223 y 50%, Venta JD/Pinki = 57.602.077
// redondeado = 57602 (brief t_0e38e74e v2, punto 4: "94,198 USD · 1223 · 50% = 57.602").
const invItemJD = { id: 101, nombre: 'Notebook ThinkPad', categoria: 'Electrónica', ubicacion: 'Living',
  valor_estimado: 450000, fecha_adquisicion: '2024-03-01', notas: 'Comprada usada',
  precio_ars: 138000, cotizacion_usd_compra: 1465, proporcion_jd: null, estado: 'Activo' };
// invItemXss: USD explícito (precio_usd_compra) + reparto declarado 60/40,
// sin precio_ars (ARS JD/Pinki deben mostrar "—") + payloads XSS en
// nombre/ubicación/notas.
const invItemXss = { id: '102', nombre: 'Bicicleta <img src=x onerror=alert(1)>', categoria: 'Deporte',
  ubicacion: '<svg onload=alert(2)>Garage', valor_estimado: 120000, fecha_adquisicion: '',
  notas: '<script>alert(3)</script> cuidado con el freno',
  precio_usd_compra: 200, proporcion_jd: 60, estado: 'Vendido' };
// invItemDonado: sin ningún dato de USD (ni precio_usd_compra ni
// precio_ars/cotizacion_usd_compra) — USD compra y Venta JD/Pinki deben
// mostrar "—" (brief: "valores faltantes: —"), nunca inventar un monto.
const invItemDonado = { id: 103, nombre: 'Silla rota', categoria: 'Hogar', ubicacion: 'Depósito',
  valor_estimado: 30000, estado: 'Donado' };
inventarioData.inventario = [invItemJD, invItemXss, invItemDonado];

inventarioApi.setInventarioCotizacion('1223');
assert.equal(inventarioApi.getInventarioCotizacion(), 1223);
inventarioApi.renderInventarioView();

const usdNotebook = 138000 / 1465;
const ventaJdNotebook = Math.round(usdNotebook * 1223 * 0.5);
assert.equal(ventaJdNotebook, 57602, 'Venta JD con usd≈94,198 · cotHoy 1223 · 50% debe dar 57.602 (ejemplo del brief)');

// Barra de cotización (editable, persistida) + 4 cards con el reparto JD/Pinki,
// filtro de estado "Activo" por defecto.
assert.equal(inventarioApi.filtroEstado, 'Activo');
assert.equal(inventarioElement('inv-total-usd').textContent, `U$D ${Math.round(usdNotebook)}`);
assert.equal(inventarioElement('inv-total-ars').textContent, `≈ $${Math.round(usdNotebook * 1223)} ARS hoy`);
assert.equal(inventarioElement('inv-jd-usd').textContent, `U$D ${Math.round(usdNotebook * 0.5)}`);
assert.equal(inventarioElement('inv-pinki-usd').textContent, `U$D ${Math.round(usdNotebook * 0.5)}`);
assert.equal(inventarioElement('inv-count-activos').textContent, '1');
assert.match(inventarioElement('inv-count-sub').textContent, /1 bien activo/);
assert.equal(inventarioElement('inventario-cotizacion-input').value, 1223);

const inventarioHtml = inventarioElement('inventario-content').innerHTML;
// Columnas y orden exactos del legacy (brief punto 1).
const headerOrder = ['Descripción', 'Categoría', 'Fecha', 'ARS pagado', 'Cot. compra', 'USD compra',
  '% JD', '% Pinki', 'ARS JD', 'ARS Pinki', 'Cot. hoy', 'Reventa (ARS hoy)', 'Venta JD', 'Venta Pinki', 'Estado', 'Acciones'];
const headerPositions = headerOrder.map((h) => inventarioHtml.indexOf(`>${h}<`));
assert.ok(headerPositions.every((p) => p >= 0), 'Deben estar las 16 columnas del legacy más Reventa (ARS hoy)');
assert.deepEqual(headerPositions, [...headerPositions].sort((a, b) => a - b), 'Las columnas deben respetar el orden exacto, con Reventa (ARS hoy) entre Cot. hoy y Venta JD');

assert.match(inventarioHtml, /Notebook ThinkPad/);
assert.doesNotMatch(inventarioHtml, /Bicicleta/, 'El filtro Activo por defecto debe excluir los bienes Vendidos/Donados');
assert.match(inventarioHtml, new RegExp(`U\\$D ${Math.round(usdNotebook)}`), 'USD compra derivado de precio_ars/cotizacion_usd_compra');
assert.match(inventarioHtml, />50%</, 'proporcion_jd ausente debe asumir 50/50, sin anotación "(sin dato)"');
assert.doesNotMatch(inventarioHtml, /sin dato/);
assert.match(inventarioHtml, new RegExp(`\\$${ventaJdNotebook}`), 'Venta JD debe listarse con la fórmula del legacy');
// Reventa (ARS hoy) = USD de compra (el mismo derivado que usan Venta JD/Pinki) × cotización de hoy, sin repartir por persona (brief t_0e38e74e, ajuste final).
const reventaNotebook = Math.round(usdNotebook * 1223);
assert.match(inventarioHtml, new RegExp(`id="inv-reventa-101">\\$${reventaNotebook}<`),
  'Reventa (ARS hoy) debe ser USD compra × cotización de hoy');
assert.match(inventarioHtml, />2024-03</, 'La fecha debe truncarse a YYYY-MM');
assert.doesNotMatch(inventarioHtml, />2024-03-01</, 'La fecha no debe mostrar el día completo');
assert.match(inventarioHtml, /class="badge badge-activo">ACTIVO</);

// Cambiar la cotización global (sin foco en ningún input de fila) recalcula
// en vivo las cards Y la celda Venta JD/Pinki de la fila por id, sin
// reconstruir la tabla (brief punto 1).
inventarioApi.setInventarioCotizacion('2000');
assert.equal(inventarioElement('inv-total-usd').textContent, `U$D ${Math.round(usdNotebook)}`, 'El USD no depende de la cotización de hoy');
assert.equal(inventarioElement('inv-total-ars').textContent, `≈ $${Math.round(usdNotebook * 2000)} ARS hoy`);
assert.equal(inventarioElement('inventario-cotizacion-input').value, 2000);
const ventaJdTras2000 = Math.round(usdNotebook * 2000 * 0.5);
assert.equal(inventarioElement('inv-venta-jd-101').textContent, `$${ventaJdTras2000}`,
  'La celda Venta JD de la fila se recalcula por id al cambiar la cotización, sin re-render de la tabla');
assert.equal(inventarioElement('inv-venta-pinki-101').textContent, `$${ventaJdTras2000}`);
assert.equal(inventarioElement('inv-reventa-101').textContent, `$${Math.round(usdNotebook * 2000)}`,
  'La celda Reventa (ARS hoy) de la fila también se recalcula por id al cambiar la cotización');

// El input inline de una fila sincroniza el input global.
inventarioElement('inv-cot-101').value = '1500';
inventarioApi.setInventarioCotizacion('1500');
assert.equal(inventarioElement('inventario-cotizacion-input').value, 1500,
  'El input global debe sincronizarse con el valor tipeado en la fila');

// Mientras una fila tiene el foco a mitad de tipeo (ej. ya escribió "15", va
// a seguir escribiendo "1500"), un cambio disparado por OTRO input (la barra
// global, en este caso) no debe pisarle lo que lleva tipeado — ahí es donde
// un re-render completo de la tabla rompería el foco/cursor (brief punto 1).
const cotInputBefore = inventarioElement('inv-cot-101');
inventarioDocument.activeElement = cotInputBefore;
cotInputBefore.value = '15';
inventarioApi.setInventarioCotizacion('3000');
assert.equal(inventarioElement('inventario-cotizacion-input').value, 3000, 'El input global sí se sincroniza');
assert.equal(inventarioElement('inv-cot-101'), cotInputBefore,
  'El nodo del input de cotización de la fila debe ser el mismo objeto antes y después del cambio: setInventarioCotizacion no debe reconstruir la tabla (revisor 7d63437e, hallazgo 3)');
assert.equal(cotInputBefore.value, '15',
  'El input de la fila con foco conserva lo que el usuario está tipeando, sin pisarlo');
inventarioDocument.activeElement = null;
inventarioElement('inv-cot-101').value = 1500;
inventarioApi.setInventarioCotizacion('1500');

// Una cotización inválida se ignora y conserva la anterior.
inventarioApi.setInventarioCotizacion('-5');
assert.equal(inventarioApi.getInventarioCotizacion(), 1500);
inventarioApi.setInventarioCotizacion('no es un número');
assert.equal(inventarioApi.getInventarioCotizacion(), 1500);
inventarioApi.setInventarioCotizacion('1223');

// Filtro por estado: Vendidos, Donados y Todos.
inventarioApi.setInventarioFiltroEstado('Vendido');
assert.equal(inventarioApi.filtroEstado, 'Vendido');
let invFiltered = inventarioElement('inventario-content').innerHTML;
assert.match(invFiltered, /Bicicleta/);
assert.doesNotMatch(invFiltered, /Notebook ThinkPad/);
assert.equal(inventarioElement('inv-count-activos').textContent, '1',
  'El card de ítems activos cuenta TODO el inventario en Activo, sin importar el filtro de estado elegido');
assert.equal(estadoFilterButtons.find((b) => b.dataset.estado === 'Vendido').active, true);
assert.equal(estadoFilterButtons.find((b) => b.dataset.estado === 'Activo').active, false);
// Reparto declarado 60/40 (Bicicleta) y sin ARS pagado: ARS JD/Pinki en "—".
assert.match(invFiltered, />60%</);
assert.match(invFiltered, />40%</);
assert.match(invFiltered, /class="td-amount inv-color-jd">—</, 'Sin precio_ars, ARS JD debe mostrar "—"');

// Revisor 7d63437e, hallazgo 2: el caso 60/40 debe verificar los importes
// EXACTOS de Reventa, Venta JD, Venta Pinki y las cards con una cotización
// dada (1223, fijada más arriba) — no alcanza con comprobar que aparezcan
// "60%"/"40%", porque un reparto roto 50/50 también deja pasar eso.
const usdBici = 200;
const reventaBici1223 = Math.round(usdBici * 1223);
const ventaJdBici1223 = Math.round(usdBici * 1223 * 0.6);
const ventaPinkiBici1223 = Math.round(usdBici * 1223 * 0.4);
assert.match(invFiltered, new RegExp(`id="inv-reventa-102">\\$${reventaBici1223}<`));
assert.match(invFiltered, new RegExp(`id="inv-venta-jd-102">\\$${ventaJdBici1223}<`));
assert.match(invFiltered, new RegExp(`id="inv-venta-pinki-102">\\$${ventaPinkiBici1223}<`));
// Cards: con filtro "Vendido", Bicicleta es el único ítem (USD 200, 60/40).
assert.equal(inventarioElement('inv-total-usd').textContent, `U$D ${usdBici}`);
assert.equal(inventarioElement('inv-total-ars').textContent, `≈ $${reventaBici1223} ARS hoy`);
assert.equal(inventarioElement('inv-jd-usd').textContent, `U$D ${Math.round(usdBici * 0.6)}`);
assert.equal(inventarioElement('inv-jd-ars').textContent, `≈ $${ventaJdBici1223} ARS hoy`);
assert.equal(inventarioElement('inv-pinki-usd').textContent, `U$D ${Math.round(usdBici * 0.4)}`);
assert.equal(inventarioElement('inv-pinki-ars').textContent, `≈ $${ventaPinkiBici1223} ARS hoy`);

// Y también después de cambiar la cotización: Reventa/Venta JD/Venta Pinki y
// las 3 cards de USD-a-ARS deben recalcularse con el nuevo valor (1500), sin
// que el USD total en dólares cambie.
inventarioApi.setInventarioCotizacion('1500');
const reventaBici1500 = Math.round(usdBici * 1500);
const ventaJdBici1500 = Math.round(usdBici * 1500 * 0.6);
const ventaPinkiBici1500 = Math.round(usdBici * 1500 * 0.4);
assert.equal(inventarioElement('inv-reventa-102').textContent, `$${reventaBici1500}`);
assert.equal(inventarioElement('inv-venta-jd-102').textContent, `$${ventaJdBici1500}`);
assert.equal(inventarioElement('inv-venta-pinki-102').textContent, `$${ventaPinkiBici1500}`);
assert.equal(inventarioElement('inv-total-usd').textContent, `U$D ${usdBici}`, 'El USD total no depende de la cotización de hoy');
assert.equal(inventarioElement('inv-total-ars').textContent, `≈ $${reventaBici1500} ARS hoy`);
assert.equal(inventarioElement('inv-jd-ars').textContent, `≈ $${ventaJdBici1500} ARS hoy`);
assert.equal(inventarioElement('inv-pinki-ars').textContent, `≈ $${ventaPinkiBici1500} ARS hoy`);
// Se restablece la cotización para no afectar las secciones siguientes.
inventarioApi.setInventarioCotizacion('1223');

inventarioApi.setInventarioFiltroEstado('Donado');
invFiltered = inventarioElement('inventario-content').innerHTML;
assert.match(invFiltered, /Silla rota/);
assert.doesNotMatch(invFiltered, /Notebook ThinkPad|Bicicleta/);
// Silla rota no tiene ningún dato de USD: USD compra y Venta JD/Pinki en "—".
assert.match(invFiltered, /class="td-amount">—</, 'Sin precio_usd_compra ni precio_ars/cotizacion_usd_compra, USD compra debe mostrar "—"');

inventarioApi.setInventarioFiltroEstado('');
assert.equal(inventarioApi.filtroEstado, '');
invFiltered = inventarioElement('inventario-content').innerHTML;
assert.match(invFiltered, /Notebook ThinkPad/);
assert.match(invFiltered, /Bicicleta/);
assert.match(invFiltered, /Silla rota/);
assert.equal(inventarioElement('inventario-count').textContent, '3 de 3');
// Las cards suman USD de Notebook (derivado) + Bicicleta (explícito 200); Silla
// rota no aporta nada por no tener USD conocido (ni inventado ni excluido con aviso).
const totalUsdTodos = usdNotebook + 200;
assert.equal(inventarioElement('inv-total-usd').textContent, `U$D ${Math.round(totalUsdTodos)}`);
assert.doesNotMatch(inventarioElement('inv-count-sub').textContent, /sin USD/,
  'La captura de Juan no muestra un aviso de "N sin USD", solo "N bienes activos"');

// XSS: nombre, ubicación y notas deben llegar escapados al innerHTML (filtro "Todos" vigente).
assert.doesNotMatch(invFiltered, /<img/i, 'El nombre con XSS no debe crear un <img>');
assert.match(invFiltered, /&lt;img src=x onerror=alert\(1\)&gt;/);
assert.doesNotMatch(invFiltered, /<svg/i, 'La ubicación con XSS no debe crear un <svg>');
assert.match(invFiltered, /&lt;svg onload=alert\(2\)&gt;/);
assert.doesNotMatch(invFiltered, /<script/i, 'Las notas con XSS no deben crear un <script>');
assert.match(invFiltered, /&lt;script&gt;alert\(3\)&lt;\/script&gt;/);

// Filtros de categoría/ubicación/búsqueda se aplican sobre el estado ya filtrado.
inventarioElement('inventario-filtro-categoria').value = 'Deporte';
inventarioApi.renderInventarioView();
invFiltered = inventarioElement('inventario-content').innerHTML;
assert.doesNotMatch(invFiltered, /Notebook ThinkPad|Silla rota/, 'El filtro de categoría debe excluir los bienes de otra categoría');
assert.match(invFiltered, /Bicicleta/);
assert.match(inventarioElement('inventario-count').textContent, /1 de 3/);
inventarioElement('inventario-filtro-categoria').value = '';

inventarioElement('inventario-filtro-ubicacion').value = invItemXss.ubicacion;
inventarioApi.renderInventarioView();
invFiltered = inventarioElement('inventario-content').innerHTML;
assert.doesNotMatch(invFiltered, /Notebook ThinkPad|Silla rota/, 'El filtro de ubicación debe excluir los bienes de otra ubicación');
assert.match(invFiltered, /Bicicleta/);
inventarioElement('inventario-filtro-ubicacion').value = '';

inventarioElement('inventario-search').value = 'freno';
inventarioApi.renderInventarioView();
invFiltered = inventarioElement('inventario-content').innerHTML;
assert.match(invFiltered, /Bicicleta/, 'La búsqueda por notas debe filtrar aunque no coincida el nombre');
assert.doesNotMatch(invFiltered, /Notebook ThinkPad|Silla rota/);
inventarioElement('inventario-search').value = 'esto no existe en ningún bien';
inventarioApi.renderInventarioView();
assert.match(inventarioElement('inventario-content').innerHTML, /Sin bienes que coincidan/);
inventarioElement('inventario-search').value = '';
inventarioApi.setInventarioFiltroEstado('Activo');

// Botones de escritura (Editar / borrar, como el legacy): habilitados en
// vivo, deshabilitados si falta la capability inventory.
inventarioData.inventario = [invItemJD];
inventarioApi.renderInventarioView();
let invButtonsHtml = inventarioElement('inventario-content').innerHTML;
assert.match(invButtonsHtml, /aria-label="Editar bien Notebook ThinkPad" >Editar<\/button>/);
assert.match(invButtonsHtml, /aria-label="Borrar bien Notebook ThinkPad" >borrar<\/button>/);
assert.match(invButtonsHtml, /data-requires="inventory"/);
inventarioApi.setInventoryAvailable(false);
inventarioApi.renderInventarioView();
invButtonsHtml = inventarioElement('inventario-content').innerHTML;
assert.match(invButtonsHtml, /aria-label="Editar bien Notebook ThinkPad" disabled>Editar<\/button>/,
  'Sin la capability inventory los botones de escritura deben quedar deshabilitados aunque el resto esté en vivo');
inventarioApi.setInventoryAvailable(true);

// Modo snapshot: sin datos (no hay data/inventario.json) y en solo lectura.
inventarioData.inventario = [];
inventarioApi.renderInventarioView();
assert.equal(inventarioElement('inv-total-usd').textContent, 'U$D 0');
assert.equal(inventarioElement('inv-count-activos').textContent, '0');
assert.match(inventarioElement('inventario-content').innerHTML, /Todavía no hay bienes cargados/);
inventarioApi.setLive(false);
inventarioApi.renderInventarioView();
assert.match(inventarioElement('inventario-content').innerHTML, /Snapshot de solo lectura/,
  'En modo snapshot debe avisar que no hay datos sin conexión autenticada, no "todavía no hay bienes"');

console.log('Inventario: tabla idéntica al legacy más Reventa (ARS hoy) (columnas y orden, USD derivado, reparto 60/40, importes exactos de Reventa/Venta JD/Venta Pinki y cards antes y después de cambiar la cotización), recalculo en vivo de filas y cards sin perder el foco del input de cotización (verificado también por identidad de nodo), cards con cotización editable (localStorage), filtro por estado (default Activo) y escape de XSS en nombre/ubicación/notas verificados con las funciones reales de app.js');

// ── Atajos de iPhone: deep links ?accion= (S5, t_a60a2f67) ─────────────────
// Usa la función real consumeAccionDeepLink de app.js, con window/openForm/
// switchView simulados. No hay navegador real: se verifica que open/switch se
// invoquen con los argumentos correctos y que la URL quede limpia.
function runDeepLink({ search = '?accion=gasto', hash = '', liveMode = true }) {
  const openFormCalls = [];
  const switchViewCalls = [];
  const alerts = [];
  const historyCalls = [];
  const sandboxWindow = {
    location: { pathname: '/', search, hash },
    alert(message) { alerts.push(message); },
    history: { replaceState(_state, _title, url) { historyCalls.push(url); } },
  };
  const deepLinkApi = runInNewContext(`
    let liveMode = ${liveMode};
    function openForm(kind) { openFormCalls.push(kind); }
    function switchView(view) { switchViewCalls.push(view); }
    ${slice('const DEEP_LINK_FORM_KIND = ', 'loadAll().then')}
    ({ consumeAccionDeepLink })`,
    { window: sandboxWindow, URLSearchParams, openFormCalls, switchViewCalls });
  deepLinkApi.consumeAccionDeepLink();
  return { openFormCalls, switchViewCalls, alerts, historyCalls };
}

for (const [accion, expectedKind] of [['gasto', 'expense'], ['ingreso', 'income'], ['fijo', 'fixed']]) {
  const result = runDeepLink({ search: `?accion=${accion}`, liveMode: true });
  assert.deepEqual(result.openFormCalls, [expectedKind], `?accion=${accion} debe abrir el alta de ${expectedKind}`);
  assert.equal(result.switchViewCalls.length, 0);
  assert.equal(result.alerts.length, 0);
  assert.equal(result.historyCalls.length, 1);
  assert.doesNotMatch(result.historyCalls[0], /accion=/, 'el parámetro accion debe limpiarse de la URL');
}

const fijosLive = runDeepLink({ search: '?accion=fijos', liveMode: true });
assert.deepEqual(fijosLive.switchViewCalls, ['fijos'], '?accion=fijos debe ir a la pestaña Fijos');
assert.equal(fijosLive.openFormCalls.length, 0);
assert.equal(fijosLive.alerts.length, 0);
assert.doesNotMatch(fijosLive.historyCalls[0], /accion=/);

// Snapshot o sin capability (liveMode=false cubre ambos casos en app.js): aviso,
// no se abre ni cambia nada, pero el parámetro igual se limpia.
for (const accion of ['gasto', 'ingreso', 'fijo', 'fijos']) {
  const result = runDeepLink({ search: `?accion=${accion}`, liveMode: false });
  assert.equal(result.openFormCalls.length, 0, `?accion=${accion} en snapshot no debe abrir nada`);
  assert.equal(result.switchViewCalls.length, 0, `?accion=${accion} en snapshot no debe cambiar de pestaña`);
  assert.equal(result.alerts.length, 1, `?accion=${accion} en snapshot debe avisar`);
  assert.equal(result.historyCalls.length, 1);
  assert.doesNotMatch(result.historyCalls[0], /accion=/);
}

// Valor desconocido: se ignora por completo, sin tocar la URL.
const unknownAccion = runDeepLink({ search: '?accion=lo-que-sea', liveMode: true });
assert.equal(unknownAccion.openFormCalls.length, 0);
assert.equal(unknownAccion.switchViewCalls.length, 0);
assert.equal(unknownAccion.alerts.length, 0);
assert.equal(unknownAccion.historyCalls.length, 0, 'un valor desconocido no debe generar history.replaceState');

// Claves heredadas del prototipo de Object (constructor, toString, __proto__,
// hasOwnProperty): el allowlist debe ignorarlas igual que cualquier valor
// desconocido, sin lanzar una excepción al llegar a openForm().
for (const accion of ['constructor', 'toString', '__proto__', 'hasOwnProperty', 'valueOf']) {
  const result = runDeepLink({ search: `?accion=${accion}`, liveMode: true });
  assert.equal(result.openFormCalls.length, 0, `?accion=${accion} (clave heredada) no debe abrir nada`);
  assert.equal(result.switchViewCalls.length, 0, `?accion=${accion} (clave heredada) no debe cambiar de pestaña`);
  assert.equal(result.alerts.length, 0, `?accion=${accion} (clave heredada) no debe avisar`);
  assert.equal(result.historyCalls.length, 0, `?accion=${accion} (clave heredada) no debe generar history.replaceState`);
}

// Sin ?accion en absoluto: tampoco pasa nada.
const noAccion = runDeepLink({ search: '?mes=2026-10', liveMode: true });
assert.equal(noAccion.openFormCalls.length, 0);
assert.equal(noAccion.historyCalls.length, 0);

// Otros parámetros y el hash se preservan al limpiar accion.
const preserved = runDeepLink({ search: '?foo=bar&accion=fijos', hash: '#ancla', liveMode: true });
assert.deepEqual(preserved.switchViewCalls, ['fijos']);
assert.equal(preserved.historyCalls[0], '/?foo=bar#ancla');

console.log('Atajos de iPhone: ?accion=gasto|ingreso|fijo|fijos abre el alta/pestaña correspondiente en vivo, avisa sin abrir nada en snapshot, ignora valores desconocidos (incluidas claves heredadas del prototipo: constructor, toString, __proto__, hasOwnProperty, valueOf) sin tocar la URL ni lanzar excepción, y siempre limpia el parámetro conocido preservando el resto de la query y el hash — verificado con la función real consumeAccionDeepLink de app.js');
