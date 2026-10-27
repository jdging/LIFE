import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const pureSource = source.slice(0, source.indexOf('function fijosDateLabel('));
assert.ok(pureSource.includes('function fijosTotalMes('), 'No se encontró el bloque de lógica pura');
class FrozenDate extends Date {
  constructor(...args) { super(...(args.length ? args : ['2026-10-16T12:00:00Z'])); }
}
const api = runInNewContext(`${pureSource}\n({
  fijosVersionVigente, fijosVigentes, fijosHistorial, fijosTramos, fijosTotalMes,
  fijosEvolutionData, gastosTotalState, fixedAllocation, computePeriod,
  getMonthsInPeriod, computeFixedForPersona, fixedMonths,
  setData(gastos, ingresos, fijos, resumen) {
    DATA.gastos = gastos; DATA.ingresos = ingresos; DATA.fijos = fijos; DATA.resumen = resumen;
  },
  setPeriod(value) { period = value; },
})`, { Date: FrozenDate });
const rows = JSON.parse(readFileSync(new URL('./fixtures/gastos_fijos.synthetic.json', import.meta.url), 'utf8'));

assert.equal(new Set(rows.map((row) => row.fijo_grupo_id)).size, 8);
assert.equal(api.fijosVersionVigente(rows, 101, '2025-12-31'), null);
assert.equal(api.fijosVersionVigente(rows, 101, '2026-05-10').id, 5, 'En el mismo día gana el id mayor');
assert.equal(api.fijosVersionVigente(rows, 101, '2026-06-01').nombre, 'Fibra Nube');
assert.equal(api.fijosVersionVigente(rows, 102, '2026-07-01').activo, 0);
assert.equal(api.fijosVigentes(rows, '2026-07-01').some((row) => row.fijo_grupo_id === 102), false);
assert.equal(api.fijosVigentes(rows, '2026-10-16').length, 7);

const history = api.fijosHistorial(rows, 101);
assert.equal(history.length, 6);
assert.equal(history[0].vigente_hasta, '2026-02-28');
assert.equal(history[3].vigente_hasta, null, 'Una versión reemplazada el mismo día no termina antes de empezar');
assert.equal(history[3].tiene_intervalo_vigencia, false);
assert.equal(history[3].supersedida_mismo_dia, true);
assert.equal(history[4].tiene_intervalo_vigencia, true);
assert.equal(history.at(-1).vigente_hasta, null);

// Historial visible: cada versión conserva sus dos etiquetas, incluso si la
// serie empezó antes de que existieran categoría y subcategoría.
const versionBase = { fijo_grupo_id: 99, nombre: 'Servicio', monto_mensual: 100,
  periodicidad: 'mensual', responsable: 'Común', tipo_proporcion: 'dinamica', activo: 1 };
const versionsWithCategories = [
  { ...versionBase, id: 201, vigente_desde: '2026-01-01', categoria: null, subcategoria: null },
  { ...versionBase, id: 202, vigente_desde: '2026-02-01', categoria: 'Hogar', subcategoria: null },
  { ...versionBase, id: 203, vigente_desde: '2026-03-01', categoria: 'Hogar', subcategoria: 'Alquiler' },
  { ...versionBase, id: 204, vigente_desde: '2026-04-01', categoria: 'Comida', subcategoria: 'Supermercado' },
  { ...versionBase, id: 205, vigente_desde: '2026-05-01', categoria: 'Comida', subcategoria: null },
  { ...versionBase, id: 206, vigente_desde: '2026-06-01', categoria: null, subcategoria: null },
];
const detail = { hidden: true, innerHTML: '' };
const historyRenderApi = runInNewContext(`
const DATA = { fijos: versionsWithCategories };
let fijosChart = null;
function fijosHistorial(rows) { return rows; }
function canonicalId(value) { return String(value); }
function escapeHtml(value) { return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
function fijosDateLabel(value) { return value; }
function fmtARS(value) { return '$' + value; }
function pillClassFor() { return ''; }
function fijosResponsable(row) { return row.responsable; }
function fijosRepartoLabel() { return 'Dinámico'; }
function fijosEvolutionData() { return { dates: [], amounts: [] }; }
${source.slice(source.indexOf('function renderFijosSeriesDetail('), source.indexOf('function openFijosInfo('))}
({ renderFijosSeriesDetail })`, {
  versionsWithCategories, document: { getElementById(id) { return id === 'fijos-series-detail' ? detail : {}; } },
  Chart: class { destroy() {} },
});
historyRenderApi.renderFijosSeriesDetail('99');
assert.match(detail.innerHTML, /<th>Categoría<\/th><th>Subcategoría<\/th>/);
const versionBody = detail.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1] || '';
const versionRows = Array.from(versionBody.matchAll(/<tr>[\s\S]*?<\/tr>/g), (match) => match[0]);
assert.equal(versionRows.length, 6);
const rowById = (id) => versionRows.find((html) => html.includes(`data-label="Desde">2026-0${id - 200}-01`));
assert.match(rowById(201), /data-label="Categoría">Sin categoría<\/td>[\s\S]*data-label="Subcategoría">Sin subcategoría<\/td>/);
assert.match(rowById(202), /data-label="Categoría">Hogar<\/td>[\s\S]*data-label="Cambios"[^>]*>Categoría<\/td>/);
assert.match(rowById(203), /data-label="Subcategoría">Alquiler<\/td>[\s\S]*data-label="Cambios"[^>]*>Subcategoría<\/td>/);
assert.match(rowById(204), /data-label="Categoría">Comida<\/td>[\s\S]*data-label="Subcategoría">Supermercado<\/td>[\s\S]*data-label="Cambios"[^>]*>Categoría, Subcategoría<\/td>/);
assert.match(rowById(205), /data-label="Subcategoría">Sin subcategoría<\/td>[\s\S]*data-label="Cambios"[^>]*>Subcategoría<\/td>/);
assert.match(rowById(206), /data-label="Categoría">Sin categoría<\/td>[\s\S]*data-label="Cambios"[^>]*>Categoría<\/td>/);
for (const versionRow of versionRows.slice(0, 5)) {
  assert.doesNotMatch(versionRow, /Sin cambio en los campos mostrados/);
}

const tramos = api.fijosTramos(rows, '2026-04-01', '2026-06-30').filter((row) => row.fijo_grupo_id === '101');
assert.equal(tramos.length, 3, 'El rango conserva cada tramo visible');
assert.deepEqual(Array.from(tramos, (row) => [row.id, row.tramo_desde, row.tramo_hasta]), [
  [2, '2026-04-01', '2026-04-14'],
  [3, '2026-04-15', '2026-05-09'],
  [5, '2026-05-10', '2026-06-30'],
]);
assert.equal(api.fijosTramos(rows, '2026-08-01', '2026-08-31').some((row) => row.fijo_grupo_id === '102' && row.activo === 0), true);
assert.equal(api.fijosTramos(rows, '2026-06-01', '2026-05-01').length, 0);

assert.equal(api.fijosTotalMes(rows, '2026-01'), 16500, 'Incluye el bimestral prorrateado');
assert.equal(api.fijosTotalMes(rows, '2026-06'), 46400);
assert.equal(api.fijosTotalMes(rows, '2026-07'), 42200, 'La baja deja de sumar');
assert.equal(api.fijosTotalMes(rows, '2026-10'), 53400);

const evolution = api.fijosEvolutionData(history);
assert.deepEqual(Array.from(evolution.dates), ['2026-01-01', '2026-03-01', '2026-04-15', '2026-05-10', '2026-08-01']);
assert.deepEqual(Array.from(evolution.amounts), [12000, 13500, 13500, 15500, 18000]);
assert.match(source, /stepped: 'after'/, 'El valor anterior debe persistir hasta la fecha del punto nuevo');
assert.deepEqual(Array.from(api.fijosEvolutionData(api.fijosHistorial(rows, 102)).amounts), [4200, 0], 'La baja empieza en cero en su fecha');

const base = { activo: 1, periodicidad: 'mensual', responsable: 'Común', tipo_proporcion: 'dinamico' };
const makeFixed = (id, group, date, amount, extra = {}) => ({
  ...base, id, fijo_grupo_id: group, vigente_desde: date, monto_mensual: amount, ...extra,
});
const maxId = '9223372036854775807';
const largeGroup = [
  makeFixed('9007199254740993', maxId, '2026-05-10', 300),
  makeFixed(maxId, maxId, '2026-05-10', 400),
  makeFixed('9007199254740992', maxId, '2026-05-10', 200),
  makeFixed('1', maxId, '2026-04-01', 100),
];
const largeHistory = api.fijosHistorial(largeGroup, maxId);
assert.deepEqual(Array.from(largeHistory, (row) => row.id), [
  '1', '9007199254740992', '9007199254740993', maxId,
], 'Las versiones del mismo día se ordenan por ID decimal exacto');
assert.equal(api.fijosVersionVigente(largeGroup, maxId, '2026-05-10').id, maxId);
assert.deepEqual(Array.from(api.fijosTramos(largeGroup, '2026-04-01', '2026-05-31'),
  (row) => [row.id, row.fijo_grupo_id, row.tramo_desde, row.tramo_hasta]), [
  ['1', maxId, '2026-04-01', '2026-05-09'],
  [maxId, maxId, '2026-05-10', '2026-05-31'],
]);
const series = [
  makeFixed(1, 1, '2026-01-20', 100),
  makeFixed(2, 1, '2026-03-01', 200),
  makeFixed(3, 1, '2026-06-01', 300),
  makeFixed(4, 1, '2026-10-20', 999),
  makeFixed(5, 2, '2026-04-01', 60, { periodicidad: 'bimestral', monto_estimado: 120 }),
  makeFixed(6, 3, '2026-11-01', 800),
];
api.setData([{ fecha: '2026-02-02' }, { fecha: '2026-12-01' }], [{ fecha: '2026-01-15' }], series, []);
const all = api.computePeriod('all');
assert.equal(all.from, '2026-01-15');
assert.equal(all.to, '2026-10-16');
api.setPeriod(all);
assert.equal(api.fixedMonths().length, 10);
assert.equal(api.computeFixedForPersona('comun'), 2720, 'Todo suma las versiones mes a mes, sin cambios futuros');
api.setPeriod(api.computePeriod('quarter'));
assert.equal(api.computeFixedForPersona('comun'), 1080);
api.setPeriod(api.computePeriod('year'));
assert.equal(api.computeFixedForPersona('comun'), 2720);
api.setPeriod(api.computePeriod('range', { from: '2026-04-15', to: '2026-07-10' }));
assert.equal(api.computeFixedForPersona('comun'), 1240, 'Rango parcial conserva cuatro meses y el corte de julio');
api.setPeriod(api.computePeriod('range', { from: '2026-10-01', to: '2026-10-16' }));
assert.equal(api.computeFixedForPersona('comun'), 360, 'El cambio del 20/10 queda fuera del corte explícito del rango');

// Mes y Rango pueden ser futuros: muestran el mes completo (y sus fijos vigentes
// a esa fecha) en vez de quedar vacíos por el recorte a "hoy".
const novPeriod = api.computePeriod('month', { month: '2026-11' });
assert.equal(novPeriod.from, '2026-11-01');
assert.equal(novPeriod.to, '2026-11-30');
assert.equal(novPeriod.from < novPeriod.to, true);
const futureRange = api.computePeriod('range', { from: '2026-11-01', to: '2026-12-31' });
assert.equal(futureRange.from, '2026-11-01');
assert.equal(futureRange.to, '2026-12-31', 'Range no se recorta a hoy cuando el "to" es explícito y futuro');
// "3 meses", "6 meses", "Año" y "Todo" siguen recortados a hoy.
assert.equal(api.computePeriod('quarter').to, '2026-10-16');
assert.equal(api.computePeriod('semester').to, '2026-10-16');
assert.equal(api.computePeriod('year').to, '2026-10-16');
assert.equal(api.computePeriod('all').to, '2026-10-16');
assert.equal(api.getMonthsInPeriod('2026-11-01', '2026-10-16').length, 0);

const custom = [
  makeFixed(10, 10, '2026-01-01', 50, { tipo_proporcion: 'custom', proporcion_jd: 0 }),
  makeFixed(11, 11, '2026-01-01', 80, { tipo_proporcion: 'custom', proporcion_jd: 100 }),
  makeFixed(12, 12, '2026-01-01', 200, { tipo_proporcion: 'custom', proporcion_jd: 25 }),
  makeFixed(13, 13, '2026-01-01', 45, { tipo_proporcion: 'custom', proporcion_jd: 25, periodicidad: 'bimestral', monto_estimado: 90 }),
  makeFixed(14, 14, '2026-01-01', 30, { responsable: 'JD' }),
  makeFixed(15, 15, '2026-01-01', 40, { responsable: 'Pinki' }),
  makeFixed(16, 16, '2026-01-01', 70, { responsable: null }),
];
api.setData([], [], custom, []);
api.setPeriod(api.computePeriod('month', { month: '2026-01' }));
assert.equal(api.fixedAllocation(custom[0], '2026-01').pct1, 0);
assert.equal(api.fixedAllocation(custom[1], '2026-01').pct1, 100);
assert.equal(api.computeFixedForPersona('comun'), 515);
assert.equal(api.computeFixedForPersona('jd_comun'), 171.25);
assert.equal(api.computeFixedForPersona('pinki_comun'), 273.75);
assert.equal(api.computeFixedForPersona('jd'), 110);
assert.equal(api.computeFixedForPersona('pinki'), 90);
assert.equal(api.fixedAllocation({ ...custom[0], proporcion_jd: null }, '2026-01').pct1, 0, 'Un custom vacío no inventa 50%');

const dynamic = [makeFixed(20, 20, '2026-01-01', 100, { periodicidad: 'bimestral', monto_estimado: 200 })];
api.setData([], [], dynamic, [
  { mes: '2026-01', total_ingresos: 100, proporcion_jd: 60, proporcion_pinki: 40 },
  { mes: '2026-02', total_ingresos: 100, proporcion_jd: 20, proporcion_pinki: 80 },
]);
api.setPeriod(api.computePeriod('range', { from: '2026-01-01', to: '2026-02-28' }));
assert.equal(api.computeFixedForPersona('jd_comun'), 80);
assert.equal(api.computeFixedForPersona('pinki_comun'), 120);

assert.equal(api.gastosTotalState(100, 25, 5, true).total, 130);
assert.equal(api.gastosTotalState(100, null, 5, false).total, null);
assert.equal(api.gastosTotalState(100, null, 5, false).partial, 105);
assert.match(source, /total === null \? 'no disponible' : fmtARS\(total\)/);
assert.match(source, /document\.getElementById\('g-total'\)\.textContent = total === null/);

const chartSource = source.slice(source.indexOf('function destroyChart('), source.indexOf('function renderGastosPie('));
const canvas = { hidden: false, parentElement: { querySelector: () => canvas.error || null }, insertAdjacentElement(_where, el) { this.error = el; } };
const chartsApi = runInNewContext(`const charts = {}; ${chartSource}\n({ renderChart })`, {
  document: { createElement: () => ({ dataset: {}, setAttribute() {}, hidden: true }) },
});
chartsApi.renderChart('gastos-bar', canvas, {});
assert.equal(canvas.hidden, true);
assert.match(canvas.error.textContent, /Chart\.js no cargó/);
assert.equal((source.match(/new Chart\(/g) || []).length, 2, 'Sólo el helper y Fijos instancian Chart.js');

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
assert.equal((html.match(/role="tab"/g) || []).length, 6);
assert.equal((html.match(/role="tab"[^>]*tabindex="-1"/g) || []).length, 5);
assert.match(source, /event\.key === 'ArrowRight'/);
assert.match(source, /event\.key === 'ArrowLeft'/);
assert.match(source, /event\.key === 'Home'/);
assert.match(source, /event\.key === 'End'/);
assert.match(source, /event\.key === 'Escape'/);

console.log('Fijos, períodos, reparto, fallback y accesibilidad: OK');
