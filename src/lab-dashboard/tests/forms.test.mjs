import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Todos los registros de este archivo son SINTÉTICOS. No se llama a una API real.
const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const summaryFixture = JSON.parse(readFileSync(new URL('./fixtures/api-summary-synthetic.json', import.meta.url), 'utf8'));
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
`;
// computePeriod, monthsWithData, mesLabel y los filtros de período son las
// funciones REALES de app.js (no copias): loadLive() las llama de verdad al
// armar el selector de meses y el panel, así que si faltan en el VM, un
// ReferenceError real se traga el try/catch de loadAll() y el test lee un
// falso "quedó en snapshot" en vez de ver la causa.
const api = runInNewContext(`${prelude}
${slice('const MESES_LARGO = ', 'const MESES_CORTO = ')}
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
   get state() { return { liveMode, authState, reloadFailed, snapshotCount, renderCount, period }; } })`,
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
${slice('function formField(', 'function openForm(')}
({ formMarkup })`, { DATA: { gastos: [] } });
const fixedMarkup = markupApi.formMarkup('fixed-edit', customFixed);
assert.match(fixedMarkup, /id="field-responsable"/);
assert.match(fixedMarkup, /id="field-fixed_tipo_proporcion"/);
assert.match(fixedMarkup, /value="custom" selected/);
assert.match(fixedMarkup, /id="field-proporcion_jd"[^>]*value="0"/);
assert.match(fixedMarkup, /id="fixed-pinki-percent"/);
assert.doesNotMatch(fixedMarkup, /API.*no.*reparto/i);
const expenseTableApi = runInNewContext(`
${slice('const escapeHtml = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
const TABLE_KEY_MAP = { monto_total: 'monto', pago: 'pagado_por' };
let tableFiltroCat = '', sortState = { key: 'fecha', dir: 'desc' };
let gastosTableRows = [{ ...expenseRow, id: bigId, categoria: '<img src=x onerror=alert(1)>',
  descripcion_original: '<svg onload=alert(2)>' }];
let liveMode = true, writePending = false, reloadPending = false, reloadFailed = false;
function iconFor() { return '🔸'; }
function fmtARS(value) { return '$' + value; }
function pillClassFor() { return 'pill-jd'; }
function cuotaLabel() { return '2/3'; }
${slice('function renderGastosTable()', "document.querySelectorAll('#tabla-gastos thead th[data-key]')")}
({ renderGastosTable })`, { document, expenseRow: expense, bigId: largeId });
expenseTableApi.renderGastosTable();
const expenseTableHtml = element('tabla-body').innerHTML;
assert.match(expenseTableHtml, new RegExp(`data-id="${largeId}"`));
assert.match(expenseTableHtml, /openForm\('expense-delete', this\.dataset\.id\)/);
assert.doesNotMatch(expenseTableHtml, /<img/i);
assert.match(expenseTableHtml, /&lt;img/);
// Columna Descripción (BRIEF.md #4): visible, con data-label para la vista mobile, y escapada.
assert.match(expenseTableHtml, /data-label="Descripción"/);
assert.doesNotMatch(expenseTableHtml, /<svg/i, 'Un payload XSS en descripcion_original no debe crear un elemento');
assert.match(expenseTableHtml, /&lt;svg onload=alert\(2\)&gt;/, 'La descripción maliciosa debe llegar escapada al innerHTML');
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

const writes = [
  ['expense', null, collectedExpense.payload, '/api/expenses', 201, { expenses: [expense] }],
  ['expense-delete', expense, null, '/api/expenses/21', 200, { deleted: true, id: 21 }],
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
let activeForm = null;
const DATA = { gastos: [], ingresos: [], fijos: [] };
function updateAvailability() {}
function showWriteNotice() {}
async function saveAndReload() { return { saved: true, reloaded: true }; }
${slice('function formField(', 'function routeForForm(')}
${slice('async function handleFormSubmit(', "document.getElementById('life-form').addEventListener")}
({ openForm, closeForm, handleFormSubmit })`,
  { document: modalCycleDocument, Date, Number, Math,
    FormData: class { constructor(target) { this.target = target; } entries() { return Object.entries(this.target.values); } } });

const modalFixedValues = { nombre: 'Prueba ciclo', monto_estimado: '50', periodicidad: 'mensual',
  responsable: 'Común', fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-10-15' };
const modalSubmit = () => ({ preventDefault() {}, currentTarget: { values: modalFixedValues } });

// Ciclo 1: abrir → confirmar → guardar (closeForm se dispara dentro de handleFormSubmit) → reabrir.
modalCycleApi.openForm('fixed');
assert.equal(modalCycleElement('form-fields').hidden, false);
assert.equal(modalCycleElement('form-confirm').hidden, true);
assert.equal(modalCycleElement('form-back').hidden, true);
await modalCycleApi.handleFormSubmit(modalSubmit());
assert.equal(modalCycleElement('form-fields').hidden, true, 'La confirmación oculta los campos');
assert.equal(modalCycleElement('form-confirm').hidden, false);
await modalCycleApi.handleFormSubmit(modalSubmit());
modalCycleApi.openForm('fixed');
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
modalCycleApi.openForm('fixed');
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
${slice('const capitalize = ', 'const fmtARS = ')}
${slice('const MAX_SQLITE_ID = ', 'function adaptLiveMovement(')}
${slice('function getMonthsInPeriod(', 'function selectPeriodType(')}
${slice('function fijosLastDay(', 'function fijosEvolutionData(')}
${slice('function fixedCutoffDate(', 'function fixedMonthCutoff(')}
${slice('function fijosDateLabel(', 'function fijosResponsable(')}
${slice('function renderFijosDetail(', 'function renderCuotasDetail(')}
({ renderFijosDetail })`, {
  document: fijosXssDocument,
  DATA: { loadErrors: {}, fijos: [{ id: 1, fijo_grupo_id: 1, nombre: '<svg onload=alert(1)>', categoria: 'Hogar',
    subcategoria: '', vigente_desde: '2026-10-01', monto_mensual: 100, monto_estimado: 100,
    periodicidad: '<img src=x onerror=alert(1)>', activo: 1 }] },
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

console.log('Formularios: rutas, payloads y lectura posterior verificados con fixture de API sintética');
console.log('Modal: ciclo completo (guardar/cancelar/reabrir) y escape de XSS en detalle de fijos verificados');
console.log('Revisor d2efc768: fallback de proporción, meses futuros con cuotas, historial de fijos e income-delete verificados');
