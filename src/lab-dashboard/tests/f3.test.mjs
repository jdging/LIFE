import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Ejecutar desde la raíz del candidato: node --test src/lab-dashboard/tests/f3.test.mjs
// Límite: DOM y Chart.js simulados; la lectura con tecnología asistiva y el
// aspecto visual requieren revisión manual en navegador, sin servicios reales.

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../style.css', import.meta.url), 'utf8');
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
  renderComposicion, toggleChartPanel, renderGastosPie, renderGastosBar, handleGastosBarMonthsChange,
  renderSubcatChart, renderIncomeLines,
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
assert.equal((element('comp-legend').innerHTML.match(/Cuotas/g) || []).length, 1, 'Cuotas se rotula una sola vez');
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*18,6/);
assert.match(html, /class="composicion-bar" aria-hidden="true"/);
assert.match(html, /id="comp-legend" role="list" aria-label="Desglose de la composición del gasto"/);
assert.doesNotMatch(html, /id="comp-labels-row"/, 'No hay una segunda fila de rótulos');
assert.equal(element('composicion-bar').attributes['aria-label'], undefined, 'La barra visual no duplica los datos accesibles');
api.renderComposicion(999, 0, 1);
assert.equal(element('comp-seg-cuotas').style.width, '1%', 'Una cuota pequeña sigue visible en la barra');
assert.equal(element('comp-seg-var').style.width, '99%', 'La barra conserva ancho total de 100%');
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*\$\s*1</, 'La etiqueta y monto de cuotas pequeñas se leen en la leyenda');
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*menos de 1%/, 'Una proporción pequeña no se anuncia como cero');
assert.equal((element('comp-legend').innerHTML.match(/Cuotas/g) || []).length, 1);
assert.equal(element('comp-seg-cuotas').attributes['aria-label'], undefined);
assert.match(element('comp-total').textContent, /1\.000/, 'El mínimo visual no altera el total');
api.renderComposicion(1000, 0, 0);
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*\$\s*0</);
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*\(0%\)/);
assert.equal((element('comp-legend').innerHTML.match(/Cuotas/g) || []).length, 1, 'Cero sigue rotulado una vez');
assert.equal(element('comp-seg-cuotas').style.width, '0%', 'Cero no se transforma en monto positivo');
api.renderComposicion(0, 0, 0);
assert.match(element('comp-legend').innerHTML, /Cuotas[\s\S]*\$\s*0</);
assert.match(element('comp-total').textContent, /\$\s*0/);
assert.match(css, /\.composicion-legend\s*\{[^}]*display:\s*flex/s);

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
assert.match(html, /<h2 id="gastos-bar-title">Últimos 6 meses<\/h2>/, 'El título conserva su semántica de encabezado sin anunciar cambios');
assert.doesNotMatch(html, /<h2 id="gastos-bar-title"[^>]*aria-live=/, 'El título no duplica la región viva');
assert.match(html, /<p id="gastos-bar-range" class="chart-range-note">Calculando rango…<\/p>/, 'El rango tiene un subtítulo visible');
assert.equal((html.slice(html.indexOf('id="gastos-bar-title"'), html.indexOf('id="gastos-bar-body"')).match(/aria-live=/g) || []).length,
  1, 'El control de meses conserva una sola región viva');
assert.match(html, /<label[^>]*for="gastos-bar-months"[^>]*>Meses a comparar <input type="number" id="gastos-bar-months"[^>]*min="1" max="24" step="1" value="6"[^>]*aria-describedby="gastos-bar-months-help gastos-bar-months-status"/);
assert.match(html, /id="gastos-bar-months-status" role="status" aria-live="polite"/);
assert.match(css, /\.chart-filter-label \.chart-months-input:focus-visible/);
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
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-01-01 a 2026-02-28.');
assert.equal(element('chart-config-gastos-bar').config.data.datasets[0].data[0], 130.6, 'La barra suma variable, cuota y fijo una vez');
assert.match(element('chart-gastos-bar-data').innerHTML, /2026-01[\s\S]*\$\s*130,6/);
assert.match(element('chart-gastos-bar-data').innerHTML, /2026-02/);
element('gastos-bar-body').hidden = false;
const monthsInput = element('gastos-bar-months');
const monthsStatus = element('gastos-bar-months-status');
const statusWrites = [];
let statusText = monthsStatus.textContent;
Object.defineProperty(monthsStatus, 'textContent', {
  get() { return statusText; },
  set(value) { statusText = value; statusWrites.push(value); },
});
monthsInput.value = '1';
api.handleGastosBarMonthsChange(monthsInput);
assert.equal(statusWrites.length, 1, 'Un cambio válido con el gráfico abierto anuncia el estado una sola vez');
assert.equal(element('gastos-bar-title').textContent, 'Último mes');
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 1);
assert.doesNotMatch(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-01<\/th>/);
assert.match(element('chart-gastos-bar-data').innerHTML, /2026-02/);
assert.match(element('chart-gastos-bar').attributes['aria-label'], /1 mes/);
assert.match(element('gastos-bar-months-status').textContent, /1 mes/);
api.renderGastosBar();
assert.equal(statusWrites.length, 1, 'Volver a renderizar el mismo rango no repite el anuncio');
api.setPeriod({ from: '2026-01-15', to: '2026-09-20' });
for (const [quantity, expected] of [[3, 3], [6, 6], [9, 9], [24, 9]]) {
  monthsInput.value = String(quantity);
  api.handleGastosBarMonthsChange(monthsInput);
  assert.equal(element('chart-config-gastos-bar').config.data.labels.length, expected);
  assert.equal(element('gastos-bar-title').textContent,
    `Últimos ${quantity} meses${quantity === expected ? '' : ` (${expected} meses mostrados)`}`);
  assert.match(element('chart-gastos-bar-data').innerHTML,
    new RegExp(`Se solicitaron ${quantity} meses y se muestran ${expected} meses`));
  assert.match(element('chart-gastos-bar').attributes['aria-label'], /2026-01-15 a 2026-09-20/);
}
assert.match(element('chart-gastos-bar').attributes['aria-label'], /Rango mostrado: 2026-01-15 a 2026-09-20/);
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-01-15 a 2026-09-20.');
monthsInput.value = '3';
api.handleGastosBarMonthsChange(monthsInput);
assert.doesNotMatch(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-06<\/th>/, 'Tres meses recortan los anteriores');
assert.match(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-07<\/th>/);
assert.match(element('chart-gastos-bar').attributes['aria-label'], /Rango mostrado: 2026-07-01 a 2026-09-20/);
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-07-01 a 2026-09-20.');
monthsInput.value = '24';
api.handleGastosBarMonthsChange(monthsInput);
assert.doesNotMatch(element('chart-gastos-bar-data').innerHTML, /2026-01-10/, 'El corte de inicio excluye ingresos anteriores');
assert.match(element('chart-gastos-bar-data').innerHTML, /<th scope="row">2026-01<\/th>/);
assert.equal(element('chart-config-gastos-bar').config.data.datasets[1].data[0], 0, 'El inicio parcial excluye ingresos previos al día 15');
api.setPeriod({ from: '2026-01-15', to: '2026-09-05' });
api.renderGastosBar();
assert.equal(element('chart-config-gastos-bar').config.data.datasets[1].data.at(-1), 0, 'El fin parcial excluye ingresos posteriores al día 5');
const previousConfig = element('chart-config-gastos-bar').config;
for (const invalid of ['0', '25', '2.5', '1e2', '']) {
  monthsInput.value = invalid;
  const writesBeforeInvalid = statusWrites.length;
  api.handleGastosBarMonthsChange(monthsInput);
  assert.equal(statusWrites.length, writesBeforeInvalid + 1, 'Cada entrada inválida recibe feedback en la única región viva');
  assert.equal(monthsInput.value, '24', 'Un valor inválido vuelve al último valor válido');
  assert.equal(element('chart-config-gastos-bar').config, previousConfig, 'No se recalcula con cantidad inválida');
  assert.match(element('gastos-bar-months-status').textContent, /Cantidad inválida/);
}
monthsInput.value = '6';
api.handleGastosBarMonthsChange(monthsInput);
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 6);
api.setPeriod({ from: '2026-01-15', to: '2026-06-20' });
api.renderGastosBar();
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 6);
assert.equal(element('gastos-bar-title').textContent, 'Últimos 6 meses');
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-01-15 a 2026-06-20.');
api.setPeriod({ from: '2026-04-10', to: '2026-09-05' });
api.renderGastosBar();
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 6, 'Dos períodos distintos muestran la misma cantidad de meses');
assert.equal(element('gastos-bar-title').textContent, 'Últimos 6 meses');
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-04-10 a 2026-09-05.', 'El subtítulo distingue los períodos');
api.setFilter('pinki');
api.renderGastosBar();
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-04-10 a 2026-09-05.', 'La selección de persona conserva el rango efectivo');
api.setPeriod({ from: '2026-01-01', to: '2026-02-28' });
api.renderGastosBar();
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

api.setFilter('comun');
api.setPeriod({ from: '2026-02-01', to: '2026-02-28' });
element('gastos-bar-body').hidden = false;
for (const quantity of [1, 6, 24]) {
  monthsInput.value = String(quantity);
  api.handleGastosBarMonthsChange(monthsInput);
  assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 1);
  assert.equal(element('gastos-bar-title').textContent,
    quantity === 1 ? 'Último mes' : `Últimos ${quantity} meses (1 mes mostrado)`);
  assert.match(element('chart-gastos-bar').attributes['aria-label'],
    new RegExp(`Se ${quantity === 1 ? 'solicitó' : 'solicitaron'} ${quantity} ${quantity === 1 ? 'mes' : 'meses'} y se muestra 1 mes`));
  assert.match(element('chart-gastos-bar').attributes['aria-label'], /Rango mostrado: 2026-02-01 a 2026-02-28/);
}

const originalGastos = api.DATA.gastos;
const originalFijos = api.DATA.fijos;
const originalIngresos = api.DATA.ingresos;
api.DATA.gastos = [];
api.DATA.fijos = [];
api.DATA.ingresos = [];
api.setPeriod({ from: '2026-04-01', to: '2026-09-30' });
monthsInput.value = '6';
api.handleGastosBarMonthsChange(monthsInput);
assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 6, 'Meses sin movimientos conservan barras con cero');
assert.ok(element('chart-config-gastos-bar').config.data.datasets.every((dataset) => dataset.data.every((amount) => amount === 0)));
assert.equal(element('gastos-bar-title').textContent, 'Últimos 6 meses');
assert.equal(element('gastos-bar-range').textContent, 'Rango mostrado: 2026-04-01 a 2026-09-30.');
api.DATA.gastos = originalGastos;
api.DATA.fijos = originalFijos;
api.DATA.ingresos = originalIngresos;

api.setPeriod({ from: null, to: null });
for (const quantity of [1, 6, 24]) {
  monthsInput.value = String(quantity);
  api.handleGastosBarMonthsChange(monthsInput);
  assert.equal(element('chart-config-gastos-bar').config.data.labels.length, 0);
  assert.equal(element('gastos-bar-title').textContent,
    quantity === 1 ? '1 mes solicitado (0 meses mostrados)' : `Últimos ${quantity} meses (0 meses mostrados)`);
  assert.match(element('chart-gastos-bar-data').innerHTML, /No hay meses para mostrar en el período seleccionado/);
  assert.match(element('chart-gastos-bar').attributes['aria-label'], /se muestran 0 meses/);
  assert.match(element('gastos-bar-months-status').textContent, /se muestran 0 meses/);
  assert.equal(element('gastos-bar-range').textContent, 'No hay meses para mostrar en el período seleccionado.');
}

console.log('F3: cuotas, filtros, reparto mensual, controles y rango: OK');
