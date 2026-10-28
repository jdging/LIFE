import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Ejecutar desde la raíz del candidato: node --test src/lab-dashboard/tests/f3.test.mjs
// Límite: DOM y Chart.js simulados; la lectura con tecnología asistiva y el
// aspecto visual requieren revisión manual en navegador, sin servicios reales.

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const pure = source.slice(0, source.indexOf('function fijosDateLabel('));
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    id, hidden: true, style: {}, innerHTML: '', textContent: '', attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  return elements.get(id);
}
const document = {
  getElementById: element,
  querySelector: () => element('composicion-bar'),
  querySelectorAll: () => [],
};
const api = runInNewContext(`${pure}
${source.slice(source.indexOf('function renderComposicion('), source.indexOf('function destroyChart('))}
${source.slice(source.indexOf('function renderGastosPie('), source.indexOf('function renderGastosBar('))}
${source.slice(source.indexOf('function renderGastosBar('), source.indexOf('function drillDownToSubcat('))}
${source.slice(source.indexOf('function drillDownToSubcat('), source.indexOf('function setupTablaCategSelect('))}
${source.slice(source.indexOf('function renderIncomeLines('), source.indexOf('// ── VISTA SUPERMERCADO'))}
${source.slice(source.indexOf('function renderFijosDetail('), source.indexOf('function renderCuotasDetail('))}
${source.slice(source.indexOf('function renderCuotasDetail('), source.indexOf('// Detalle de deuda:'))}
({ DATA, computePeriod, getRowPct, applyPersonaFiltro, expenseAmount, fixedAmount,
  computeFixedForPersona, filterCuotasComprometidas, filterGastosPeriod, getMonthsInPeriod,
  setFilter(value) { personaFiltro = value; fijosPersonaFiltro = value; },
  setIncomeFilter(value) { incomePersonaFiltro = value; },
  setPeriod(value) { period = value; },
  renderComposicion, toggleChartPanel, renderGastosPie, renderGastosBar, renderSubcatChart, renderIncomeLines,
  renderFijosDetail, renderCuotasDetail, renderCreditoDetail })`, {
  document,
  renderChart(key, canvas, config) { element('chart-config-' + key).config = config; },
  destroyChart(key) { element('destroy-' + key).called = true; },
  fmtARS,
  Date,
});

function fmtARS(value) { return '$' + Number(value).toFixed(2); }
const summaries = [
  { mes: '2026-01', proporcion_jd: 69, proporcion_pinki: 31, total_ingresos: 1000 },
  { mes: '2026-02', proporcion_jd: 20, proporcion_pinki: 80, total_ingresos: 1000 },
];
const shared = (fecha, monto, cuota_nro = 1, extra = {}) => ({
  fecha, monto, cuota_nro, cuotas_total: cuota_nro > 1 ? 3 : 1,
  categoria: 'Hogar', subcategoria: 'Alquiler', tipo_proporcion: 'dinamico', ...extra,
});
api.DATA.resumen = summaries;
api.DATA.gastos = [
  shared('2026-01-05', 100),
  shared('2026-01-06', 60, 2, { medio_pago: 'Crédito' }),
  shared('2026-02-05', 100),
  shared('2026-01-07', 50, 1, { tipo_proporcion: 'custom', proporcion_jd: 0 }),
];
api.DATA.fijos = [
  { id: '1', fijo_grupo_id: '1', vigente_desde: '2026-01-01', activo: 1,
    nombre: 'Alquiler', categoria: 'Hogar', periodicidad: 'mensual', responsable: 'Común',
    tipo_proporcion: 'dinamico', medio_pago: 'Crédito', monto_mensual: 100 },
];
api.DATA.ingresos = Array.from({ length: 9 }, (_, i) => ({
  fecha: `2026-${String(i + 1).padStart(2, '0')}-10`, persona: 'JD', monto: 100 + i,
}));
api.setPeriod(api.computePeriod('month', { month: '2026-01' }));
api.setFilter('pinki_comun');
assert.equal(api.getRowPct(api.DATA.gastos[3]).pct1, 0, 'Cero custom se conserva');
assert.equal(api.expenseAmount(api.DATA.gastos[0]), 31, 'Pinki: $31 de $100');
assert.equal(api.expenseAmount(api.DATA.gastos[1]), 18.6, 'Cuota mensual usa reparto del mes');
assert.equal(api.fixedAmount(api.DATA.fijos[0], '2026-01'), 31);
assert.equal(api.fixedAmount(api.DATA.fijos[0], '2026-02'), 80, 'Fijo dinámico cambia de mes');
assert.equal(api.fixedAmount({ ...api.DATA.fijos[0], tipo_proporcion: 'custom', proporcion_jd: 0 }, '2026-01'), 100);
assert.equal(api.expenseAmount(api.DATA.gastos[2]), 80, 'Gasto dinámico cambia de mes');
assert.equal(api.computeFixedForPersona('pinki_comun'), 31);
assert.equal(api.filterCuotasComprometidas('2026-01-01', '2026-01-31').length, 1);
assert.equal(api.filterCuotasComprometidas('2026-02-01', '2026-02-28').length, 0);
assert.equal(api.expenseAmount(api.DATA.gastos[3]), 50, 'Custom 0% JD deja 100% a Pinki');
api.setFilter('jd');
assert.equal(api.applyPersonaFiltro(api.DATA.gastos).length, 0, 'JD puro excluye gastos compartidos');
api.setFilter('jd_comun');
assert.equal(api.expenseAmount(api.DATA.gastos[0]), 69);
assert.equal(api.applyPersonaFiltro(api.DATA.gastos).length, 3, 'JD+Común excluye personal de Pinki');
api.setFilter('pinki');
assert.equal(api.applyPersonaFiltro(api.DATA.gastos).length, 1, 'Pinki pura muestra solo 100% personal');
api.setFilter('comun');
assert.equal(api.applyPersonaFiltro(api.DATA.gastos).length, 3, 'Comunes excluye gasto personal');

api.renderComposicion(31, 31, 18.6);
assert.match(element('comp-total').textContent, /Total.*80,6/);
assert.equal(Number(element('comp-seg-cuotas').style.width.slice(0, -1)).toFixed(2), (18.6 / 80.6 * 100).toFixed(2));
assert.match(element('comp-legend').innerHTML, /Cuotas/);
assert.match(element('composicion-bar').attributes['aria-label'], /Cuotas.*18,6/);
api.renderComposicion(999, 0, 1);
assert.equal(element('comp-seg-cuotas').style.width, '1%', 'Una cuota pequeña sigue visible en la barra');
assert.equal(element('comp-seg-var').style.width, '99%', 'La barra conserva ancho total de 100%');

api.setFilter('pinki_comun');
api.renderFijosDetail();
assert.match(element('fijos-detail-inner').innerHTML, /31[^<]* de [^<]*100/);
assert.match(element('fijos-detail-inner').innerHTML, /2026-01/);
api.renderCuotasDetail();
assert.match(element('cuotas-detail-inner').innerHTML, /18,6[^<]* de [^<]*60/);
api.renderCreditoDetail();
assert.match(element('credito-detail-inner').innerHTML, /18,6[^<]* de [^<]*60/);
assert.match(element('credito-detail-inner').innerHTML, /Alquiler · fijo[\s\S]*31[^<]* de [^<]*100/);

assert.match(html, /id="gastos-pie-body" hidden/);
assert.match(html, /id="gastos-bar-body" hidden/);
assert.match(html, /id="inc-lines-body" hidden/);
assert.match(source, /id="fijos-evolution-body" hidden/);
for (const name of ['gastosPie', 'gastosBar', 'incLines']) {
  assert.match(html, new RegExp(`toggleChartPanel\\('${name}'\\)`));
}
assert.match(source, /function setFijosPersonaFiltro\(/);
assert.match(source, /function setIncomePersonaFiltro\(/);
assert.match(source, /function toggleFijosEvolutionChart\(/);
for (const label of ['Filtrar tabla de gastos', 'Filtrar gráfico por categoría', 'Filtrar gráfico de gastos']) {
  assert.ok(html.includes(label));
}
for (const id of ['chart-gastos-pie', 'chart-gastos-bar', 'chart-gastos-subcat', 'chart-inc-lines']) {
  assert.match(html, new RegExp(`<canvas id="${id}"[^>]*role="img"[^>]*aria-label="[^"]+"[^>]*aria-describedby="${id}-data"`));
  assert.match(html, new RegExp(`<details class="chart-data" id="${id}-data"><summary>`));
}
assert.match(source, /id="fijos-evolution-chart"[^>]*aria-describedby="fijos-evolution-chart-data"/);
assert.match(source, /id="fijos-evolution-chart-data"><summary>/);
assert.match(html, /id="categ-pie-toggle"[^>]*aria-label="Cambiar tipo de gráfico/);
assert.match(html, /id="subcat-toggle"[^>]*aria-label="Cambiar tipo de gráfico/);
api.toggleChartPanel('incLines');
assert.equal(element('inc-lines-body').hidden, false);
assert.equal(element('inc-lines-show').attributes['aria-expanded'], 'true');
api.toggleChartPanel('incLines');
assert.equal(element('inc-lines-body').hidden, true);
assert.equal(element('inc-lines-show').attributes['aria-expanded'], 'false');

api.setPeriod({ from: '2026-01-01', to: '2026-09-30' });
element('inc-lines-body').hidden = false;
api.renderIncomeLines();
assert.equal(element('chart-config-inc-lines').config.data.labels.length, 9, 'La evolución acepta más de seis meses');
assert.equal(element('inc-lines-range-note').textContent, '9 meses del período seleccionado');
assert.match(element('chart-inc-lines-data').innerHTML, /2026-09-30/);
assert.match(element('chart-inc-lines-data').innerHTML, /<th scope="col">JD<\/th>/);
assert.match(element('chart-inc-lines-data').innerHTML, /<th scope="col">Pinki<\/th>/);
assert.match(element('chart-inc-lines-data').innerHTML, /\$\s*108/);
api.setIncomeFilter('jd');
api.renderIncomeLines();
assert.equal(element('chart-config-inc-lines').config.data.datasets.length, 1, 'Filtro de ingresos reduce la serie visible');
assert.doesNotMatch(element('chart-inc-lines-data').innerHTML, /<th scope="col">Pinki<\/th>/);
assert.match(element('chart-inc-lines').attributes['aria-label'], /Persona: JD/);
api.setIncomeFilter('pinki');
api.setPeriod({ from: '2026-01-01', to: '2026-01-31' });
api.renderIncomeLines();
assert.match(element('chart-inc-lines-data').innerHTML, /<th scope="col">Pinki<\/th>/);
assert.doesNotMatch(element('chart-inc-lines-data').innerHTML, /2026-09/);
assert.match(element('chart-inc-lines-data').innerHTML, /\$\s*0/);
api.setPeriod({ from: '2026-01-01', to: '2026-02-28' });
api.renderGastosBar();
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 2, 'Gráfico de gastos respeta el período');
assert.equal(element('chart-config-gastos-bar').config.data.datasets[0].data[0], 130.6, 'La barra suma variable, cuota y fijo una vez');
assert.match(element('chart-gastos-bar-data').innerHTML, /2026-01[\s\S]*\$\s*130,6/);
assert.match(element('chart-gastos-bar-data').innerHTML, /2026-02/);
api.setFilter('jd');
api.renderGastosBar();
assert.match(element('chart-gastos-bar-data').innerHTML, /Persona: JD/);
assert.doesNotMatch(element('chart-gastos-bar-data').innerHTML, /\$\s*130,6/);
api.setPeriod({ from: '2026-02-01', to: '2026-02-28' });
api.renderGastosBar();
assert.doesNotMatch(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-01<\/th>/);
assert.match(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-02<\/th>/);
api.setPeriod({ from: '2026-01-01', to: '2026-01-31' });
api.setFilter('comun');
api.renderGastosPie(api.filterGastosPeriod('2026-01-01', '2026-01-31'));
assert.match(element('chart-gastos-pie-data').innerHTML, /Hogar[\s\S]*\$\s*160/);
assert.match(element('chart-gastos-pie').attributes['aria-label'], /2026-01-31/);
api.setFilter('jd_comun');
api.renderGastosPie(api.filterGastosPeriod('2026-01-01', '2026-01-31'));
assert.match(element('chart-gastos-pie-data').innerHTML, /\$\s*110,4/);
api.renderSubcatChart('Hogar');
assert.match(element('chart-gastos-subcat-data').innerHTML, /Alquiler[\s\S]*\$\s*110,4/);
assert.match(element('chart-gastos-subcat').attributes['aria-label'], /Persona: JD\+Común/);
api.setPeriod({ from: '2026-02-01', to: '2026-02-28' });
api.renderGastosPie(api.filterGastosPeriod('2026-02-01', '2026-02-28'));
api.renderSubcatChart('Hogar');
assert.match(element('chart-gastos-pie-data').innerHTML, /Hogar[\s\S]*\$\s*20/);
assert.match(element('chart-gastos-subcat-data').innerHTML, /Alquiler[\s\S]*\$\s*20/);
assert.doesNotMatch(element('chart-gastos-pie-data').innerHTML, /\$\s*110,4/);

api.DATA.resumen = [summaries[0], { mes: '2026-02', proporcion_jd: 50, proporcion_pinki: 50, total_ingresos: 0 }];
assert.equal(api.getRowPct(api.DATA.gastos[2]).pct2, 31, 'Mes sin salarios hereda último mes con ingresos');

// La evolución desplegable usa la proporción de cada mes y debe caer a cero
// desde la baja; una versión inactiva conserva el monto histórico en la fila.
let fixedEvolutionConfig;
class MarchDate extends Date {
  constructor(...args) { super(...(args.length ? args : ['2026-03-16T12:00:00Z'])); }
}
const fixedEvolutionApi = runInNewContext(`${pure}
function fijosDateLabel(date) { return date; }
${source.slice(source.indexOf('function renderChartData('), source.indexOf('function drillDownToSubcat('))}
${source.slice(source.indexOf('function toggleFijosEvolutionChart('), source.indexOf('function openFijosInfo('))}
({ DATA, toggleFijosEvolutionChart, selectGroup(id) { fijosSelectedGroup = id; },
   selectFilter(value) { fijosPersonaFiltro = value; } })`, {
  Date: MarchDate,
  document,
  Chart: class { constructor(_canvas, config) { fixedEvolutionConfig = config; } destroy() {} },
});
fixedEvolutionApi.DATA.fijos = [
  { id: '41', fijo_grupo_id: '41', vigente_desde: '2026-01-01', activo: 1,
    monto_mensual: 100, responsable: 'Común', tipo_proporcion: 'dinamico' },
  { id: '42', fijo_grupo_id: '41', vigente_desde: '2026-03-01', activo: 0,
    monto_mensual: 100, responsable: 'Común', tipo_proporcion: 'dinamico' },
];
fixedEvolutionApi.DATA.resumen = [
  { mes: '2026-01', proporcion_jd: 60, proporcion_pinki: 40, total_ingresos: 1000 },
  { mes: '2026-02', proporcion_jd: 20, proporcion_pinki: 80, total_ingresos: 1000 },
];
fixedEvolutionApi.selectGroup('41');
fixedEvolutionApi.selectFilter('jd_comun');
fixedEvolutionApi.toggleFijosEvolutionChart();
assert.deepEqual(Array.from(fixedEvolutionConfig.data.datasets[0].data), [60, 20, 0]);
assert.equal(element('fijos-evolution-show').attributes['aria-expanded'], 'true');
assert.match(element('fijos-evolution-chart-data').innerHTML, /2026-01[\s\S]*\$\s*60/);
assert.match(element('fijos-evolution-chart-data').innerHTML, /2026-02[\s\S]*\$\s*20/);
assert.match(element('fijos-evolution-chart-data').innerHTML, /2026-03[\s\S]*\$\s*0/);
assert.match(element('fijos-evolution-chart').attributes['aria-label'], /JD\+Común/);

console.log('F3: cuotas, filtros, reparto mensual, controles y rango: OK');
