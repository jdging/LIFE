'use strict';

// Nombres de persona: no existe data/config.json en este snapshot, así que se
// hardcodean según docs/CONTEXTO.md (Config: persona1=JD, persona2=Pinki).
const P1 = 'JD';
const P2 = 'Pinki';

const CATEGORY_ICONS = {
  Comida: '🛒',
  Transporte: '🚗',
  Hogar: '🏠',
  Salud: '💊',
  Entretenimiento: '🎬',
  Personal: '👤',
  Mascotas: '🐾',
};
const MESES_LARGO = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];
const MESES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const PALETTE = ['#7c9a6b', '#c97d55', '#d1a13f', '#8a6fa0', '#8a8a5c', '#a9926f', '#5f7d52', '#6e6552'];
const INK = '#332d22';
const LINE = '#e6dcc4';
const FONT = { family: 'Work Sans', size: 11 };

const iconFor = (categoria) => CATEGORY_ICONS[categoria] || '🔸';
const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const escapeHtml = (s) =>
  String(s ?? '—').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtARS = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(parseFloat(n) || 0);
const fmtARSCompact = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', notation: 'compact', maximumFractionDigits: 1 }).format(parseFloat(n) || 0);
const paletteColors = (n) => Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);

function thisMonth() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}
function mesLabel(mesStr) {
  const [y, m] = mesStr.split('-').map(Number);
  return `${capitalize(MESES_LARGO[m - 1])} ${y}`;
}
function shortMonth(ym) {
  const [y, m] = ym.split('-');
  return MESES_CORTO[parseInt(m, 10) - 1] + " '" + y.slice(2);
}
function cuotaLabel(r) {
  const total = parseInt(r.cuotas_total, 10) || 1;
  const nro = parseInt(r.cuota_nro, 10) || 1;
  return total > 1 ? `${nro}/${total}` : '—';
}
function pillClassFor(persona) {
  if (persona === 'JD') return 'pill-jd';
  if (persona === 'Pinki') return 'pill-pinki';
  return 'pill-comun';
}
function sum(rows, field) {
  return rows.reduce((acc, r) => acc + (parseFloat(r[field]) || 0), 0);
}
function groupBy(rows, field) {
  return rows.reduce((acc, r) => {
    const key = r[field] || 'Sin categoría';
    acc[key] = acc[key] || [];
    acc[key].push(r);
    return acc;
  }, {});
}
function getLatestRealMonth(rows) {
  const sorted = [...rows].sort((a, b) => a.mes.localeCompare(b.mes));
  const real = sorted.filter((r) => r.total_ingresos > 0);
  return real.length ? real[real.length - 1] : sorted[sorted.length - 1];
}

// ── ESTADO ────────────────────────────────────────────────────────────────

const DATA = { gastos: [], ingresos: [], fijos: [], resumen: [], deudaPendiente: null };
const charts = {};
let period = null;
let currentView = 'gastos';
let personaFiltro = 'comun';
let categPieMode = 'doughnut';
let subcatMode = 'doughnut';
let activeCat = null;
let categPieCache = [];
let gastosTableRows = [];
let tableFiltroCat = '';
let sortState = { key: 'fecha', dir: 'desc' };
const TABLE_KEY_MAP = { monto_total: 'monto', pago: 'pagado_por' };

// ── CARGA DE DATOS ───────────────────────────────────────────────────────

async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP ${res.status} al cargar ${path}`);
  return res.json();
}

async function loadAll() {
  const [g, i, f, r, d] = await Promise.allSettled([
    fetchJSON('data/gastos.json'),
    fetchJSON('data/ingresos.json'),
    fetchJSON('data/gastos_fijos.json'),
    fetchJSON('data/resumen_meses.json'),
    fetchJSON('data/deuda_pendiente.json'),
  ]);
  DATA.gastos = g.status === 'fulfilled' ? g.value : [];
  DATA.ingresos = i.status === 'fulfilled' ? i.value : [];
  DATA.fijos = f.status === 'fulfilled' ? f.value : [];
  DATA.resumen = r.status === 'fulfilled' ? r.value : [];
  DATA.deudaPendiente = d.status === 'fulfilled' ? d.value : null;
  if (g.status === 'rejected') console.error('No se pudo cargar data/gastos.json', g.reason);
  if (i.status === 'rejected') console.error('No se pudo cargar data/ingresos.json', i.reason);
  if (f.status === 'rejected') console.error('No se pudo cargar data/gastos_fijos.json', f.reason);
  if (r.status === 'rejected') console.error('No se pudo cargar data/resumen_meses.json', r.reason);
  if (d.status === 'rejected') console.error('No se pudo cargar data/deuda_pendiente.json', d.reason);

  period = computePeriod('month', { month: thisMonth() });
  document.getElementById('month-picker').value = period.refMonth;

  switchView('gastos');
}

// ── NAVEGACIÓN ───────────────────────────────────────────────────────────

function switchView(v) {
  currentView = v;
  ['gastos', 'inversiones', 'ingresos', 'presupuesto'].forEach((name) => {
    const tab = document.getElementById('tab-' + name);
    const panel = document.getElementById('view-' + name);
    const isActive = name === v;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
    panel.classList.toggle('active', isActive);
    panel.hidden = !isActive;
  });
  renderView(v);
}

function renderView(v) {
  if (v === 'gastos') renderGastosView();
  else if (v === 'ingresos') renderIngresosView();
  // Inversiones y Presupuesto se quedan en el estado vacío ya maquetado en index.html.
}

// ── PERÍODO ──────────────────────────────────────────────────────────────

function computePeriod(type, opts = {}) {
  const today = thisMonth();
  const [cy, cm] = today.split('-').map(Number);
  function nMonthsAgo(n) {
    let m = cm - n;
    let y = cy;
    while (m < 1) { m += 12; y--; }
    return y + '-' + String(m).padStart(2, '0');
  }
  let from, to, refMonth;
  switch (type) {
    case 'month': {
      const m = opts.month || today;
      from = m + '-01'; to = m + '-31'; refMonth = m; break;
    }
    case 'quarter':
      from = nMonthsAgo(2) + '-01'; to = today + '-31'; refMonth = today; break;
    case 'semester':
      from = nMonthsAgo(5) + '-01'; to = today + '-31'; refMonth = today; break;
    case 'year':
      from = cy + '-01-01'; to = cy + '-12-31'; refMonth = today; break;
    case 'all':
      from = null; to = null; refMonth = today; break;
    case 'range':
      from = opts.from || null; to = opts.to || null;
      refMonth = (opts.to || today).substring(0, 7); break;
    default:
      from = null; to = null; refMonth = today;
  }
  return { type, from, to, refMonth };
}

function getMonthsInPeriod(from, to) {
  if (!from || !to) return [period.refMonth];
  let [y, m] = from.substring(0, 7).split('-').map(Number);
  const [ey, em] = to.substring(0, 7).split('-').map(Number);
  const months = [];
  while (y < ey || (y === ey && m <= em)) {
    months.push(y + '-' + String(m).padStart(2, '0'));
    m++;
    if (m > 12) { m = 1; y++; }
  }
  return months;
}

function selectPeriodType(type) {
  const monthVal = document.getElementById('month-picker').value || thisMonth();
  const fromVal = document.getElementById('range-from')?.value || null;
  const toVal = document.getElementById('range-to')?.value || null;
  period = computePeriod(type, { month: monthVal, from: fromVal, to: toVal });

  document.querySelectorAll('.period-btn').forEach((b) => {
    const active = b.dataset.period === type;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  document.getElementById('month-picker').style.display = type === 'month' ? '' : 'none';
  document.getElementById('range-pickers').hidden = type !== 'range';

  renderView(currentView);
}

function onMonthChange(val) {
  period = computePeriod('month', { month: val });
  renderView(currentView);
}

function onRangeChange() {
  const from = document.getElementById('range-from')?.value || null;
  const to = document.getElementById('range-to')?.value || null;
  period = computePeriod('range', { from, to });
  renderView(currentView);
}

// ── PROPORCIÓN / FILTRO PERSONA ─────────────────────────────────────────

// tipo_proporcion viene por fila en gastos.json. Para "dinamico"/vacío se usa
// la proporción ya calculada para ese mes en resumen_meses.json (no hay endpoint
// de historial de proporciones en este snapshot estático).
function getRowPct(row) {
  const tipo = (row.tipo_proporcion || '').toLowerCase().trim();
  if (tipo === '50/50') return { pct1: 50, pct2: 50 };
  if (tipo === 'custom') {
    const raw = row.proporcion_jd;
    const pjd = (raw !== undefined && raw !== null && raw !== '') ? parseFloat(raw) : 50;
    return { pct1: pjd, pct2: 100 - pjd };
  }
  const mes = row.fecha ? String(row.fecha).slice(0, 7) : null;
  const entry = mes ? DATA.resumen.find((r) => r.mes === mes) : null;
  if (entry) return { pct1: entry.proporcion_jd, pct2: entry.proporcion_pinki };
  return { pct1: 50, pct2: 50 };
}

function applyPersonaFiltro(rows) {
  switch (personaFiltro) {
    case 'comun':
      return rows.filter((r) => { const { pct1, pct2 } = getRowPct(r); return pct1 > 0 && pct2 > 0; });
    case 'jd_comun':
      return rows.filter((r) => getRowPct(r).pct1 > 0);
    case 'jd':
      return rows.filter((r) => getRowPct(r).pct1 === 100);
    case 'pinki_comun':
      return rows.filter((r) => getRowPct(r).pct2 > 0);
    case 'pinki':
      return rows.filter((r) => getRowPct(r).pct2 === 100);
    default:
      return rows;
  }
}

function applyPersonaMonto(rows) {
  if (personaFiltro === 'comun') return rows;
  return rows.map((r) => {
    const { pct1, pct2 } = getRowPct(r);
    const pct = (personaFiltro === 'jd_comun' || personaFiltro === 'jd') ? pct1 : pct2;
    return { ...r, monto: (parseFloat(r.monto) || 0) * pct / 100 };
  });
}

function setPersonaFiltro(filtro) {
  personaFiltro = filtro;
  document.querySelectorAll('#persona-filter-top .persona-btn').forEach((b) => {
    const active = b.dataset.filter === filtro;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  if (currentView === 'gastos') renderGastosView();
}

// ── FILTROS DE DATOS ─────────────────────────────────────────────────────

function filterGastosPeriod(from, to) {
  return DATA.gastos.filter((r) => {
    if (from && (r.fecha || '') < from) return false;
    if (to && (r.fecha || '') > to) return false;
    return true;
  });
}

function filterCuotasComprometidas(from, to) {
  return DATA.gastos.filter((r) => {
    const nro = parseInt(r.cuota_nro, 10) || 1;
    if (nro <= 1) return false;
    const fecha = r.fecha || '';
    if (from && fecha < from) return false;
    if (to && fecha > to) return false;
    return true;
  });
}

function filterIngresosPeriod(from, to) {
  return DATA.ingresos.filter((r) => {
    if (from && (r.fecha || '') < from) return false;
    if (to && (r.fecha || '') > to) return false;
    return true;
  });
}

// ── GASTOS FIJOS ─────────────────────────────────────────────────────────

function fijoMonthly(item) {
  return item.periodicidad === 'bimestral' ? item.monto_estimado / 2 : item.monto_estimado;
}

// gastos_fijos.json trae versiones históricas del mismo fijo (mismo nombre,
// "ultima_actualizacion" distinta, todas activo=1) — nos quedamos con la más
// reciente por nombre para no duplicar el total (ej: "Seguro departamento").
function activeFijos() {
  const items = DATA.fijos.filter((f) => f.activo === 1 || f.activo === true);
  const latestByName = new Map();
  items.forEach((f) => {
    const existing = latestByName.get(f.nombre);
    if (!existing || (f.ultima_actualizacion || '') > (existing.ultima_actualizacion || '')) {
      latestByName.set(f.nombre, f);
    }
  });
  return [...latestByName.values()];
}

// gastos_fijos.json no tiene tipo_proporcion/proporcion_jd por ítem (a diferencia
// de gastos.json), así que para los modos JD/Pinki se aplica la proporción dinámica
// del mes de referencia al bloque completo de fijos en lugar de a cada ítem.
function computeFixedForPersona(filtro) {
  const items = activeFijos();
  const months = getMonthsInPeriod(period.from, period.to).length || 1;
  const total = items.reduce((acc, f) => acc + fijoMonthly(f), 0) * months;
  if (filtro === 'comun') return total;
  const entry = DATA.resumen.find((r) => r.mes === period.refMonth) || getLatestRealMonth(DATA.resumen);
  const pct1 = entry ? entry.proporcion_jd : 50;
  const pct2 = entry ? entry.proporcion_pinki : 50;
  if (filtro === 'jd_comun') return total * pct1 / 100;
  if (filtro === 'pinki_comun') return total * pct2 / 100;
  return 0; // 'jd' / 'pinki' (100%): sin fijos marcados como 100% personales en los datos
}

// ── VISTA GASTOS ─────────────────────────────────────────────────────────

function renderGastosView() {
  resetGastosDrilldown();

  const rows = filterGastosPeriod(period.from, period.to);
  const filteredRows = applyPersonaFiltro(rows);
  const varRows = filteredRows.filter((r) => (parseInt(r.cuota_nro, 10) || 1) === 1);
  const varTotal = sum(varRows, 'monto');
  const fixTotal = computeFixedForPersona(personaFiltro);
  const cuotasRows = applyPersonaFiltro(filterCuotasComprometidas(period.from, period.to));
  const cuotasAdjusted = applyPersonaMonto(cuotasRows);
  const cuotasTotal = sum(cuotasAdjusted, 'monto');
  const total = varTotal + fixTotal + cuotasTotal;

  document.getElementById('g-total').textContent = fmtARS(total);
  renderTotalSub(varRows, fixTotal, cuotasRows);

  document.getElementById('g-fijos').textContent = fmtARS(fixTotal);
  const fijosCount = activeFijos().length;
  document.getElementById('g-fijos-count').textContent = `${fijosCount} ítem${fijosCount !== 1 ? 's' : ''} · ver detalle`;

  document.getElementById('g-cuotas').textContent = fmtARS(cuotasTotal);
  document.getElementById('g-cuotas-count').textContent =
    `${cuotasRows.length} cuota${cuotasRows.length !== 1 ? 's' : ''} activa${cuotasRows.length !== 1 ? 's' : ''} · ver detalle`;

  const creditoRows = filteredRows.filter((r) => r.medio_pago === 'Crédito');
  const creditoTotal = sum(applyPersonaMonto(creditoRows), 'monto');
  document.getElementById('g-credito').textContent = fmtARS(creditoTotal);
  document.getElementById('g-credito-sub').textContent =
    `${creditoRows.length} ítem${creditoRows.length !== 1 ? 's' : ''} · ver detalle`;

  renderDeudaCard();
  renderComposicion(varTotal, fixTotal, cuotasTotal);
  renderGastosPie(rows);
  renderGastosBar();

  setupTablaCategSelect(rows);
  gastosTableRows = applyPersonaMonto(applyPersonaFiltro(rows));
  renderGastosTable();

  if (!document.getElementById('fijos-detail').hidden) renderFijosDetail();
  if (!document.getElementById('cuotas-detail').hidden) renderCuotasDetail();
  if (!document.getElementById('credito-detail').hidden) renderCreditoDetail();
  if (!document.getElementById('deuda-detail').hidden) renderDeudaDetail();
}

function renderTotalSub(varRows, fixTotal, cuotasRows) {
  const subEl = document.getElementById('g-total-sub');
  if (personaFiltro !== 'comun' || (varRows.length === 0 && cuotasRows.length === 0)) {
    subEl.hidden = true;
    return;
  }
  let sub1 = 0, sub2 = 0;
  varRows.forEach((r) => {
    const monto = parseFloat(r.monto) || 0;
    const { pct1, pct2 } = getRowPct(r);
    sub1 += monto * pct1 / 100;
    sub2 += monto * pct2 / 100;
  });
  const entry = DATA.resumen.find((r) => r.mes === period.refMonth) || getLatestRealMonth(DATA.resumen);
  const pct1f = entry ? entry.proporcion_jd : 50;
  const pct2f = entry ? entry.proporcion_pinki : 50;
  sub1 += fixTotal * pct1f / 100;
  sub2 += fixTotal * pct2f / 100;
  cuotasRows.forEach((r) => {
    const monto = parseFloat(r.monto) || 0;
    const { pct1, pct2 } = getRowPct(r);
    sub1 += monto * pct1 / 100;
    sub2 += monto * pct2 / 100;
  });
  subEl.hidden = false;
  subEl.textContent = `${P1}: ${fmtARS(sub1)} · ${P2}: ${fmtARS(sub2)}`;
}

// La deuda neta se muestra SIEMPRE como el saldo pendiente actual (no varía
// según el período/mes seleccionado en la vista) — Juan pidió explícitamente
// no ver deudas de meses ya saldados, solo lo que sigue pendiente hoy. Viene
// precalculado en data/deuda_pendiente.json (db.calcular_deudas_pendientes,
// suma todos los gastos JD/Pinki con saldado=NULL, sin importar el mes).
function renderDeudaCard() {
  const d = DATA.deudaPendiente;
  const el = document.getElementById('g-deuda');
  const sub = document.getElementById('g-deuda-quien');
  if (!d || !d.deudor) {
    el.textContent = '$0';
    el.classList.remove('danger');
    sub.textContent = 'sin deuda pendiente';
    return;
  }
  el.textContent = fmtARS(d.monto);
  el.classList.add('danger');
  sub.textContent = `${d.deudor} le debe a ${d.acreedor} · ver detalle`;
}

function renderComposicion(varTotal, fixTotal, cuotasTotal) {
  const total = varTotal + fixTotal + cuotasTotal || 1;
  const segs = [
    { name: 'Fijos', val: fixTotal, elId: 'comp-seg-fijos', color: 'var(--terracotta)' },
    { name: 'Variable', val: varTotal, elId: 'comp-seg-var', color: 'var(--mustard)' },
    { name: 'Cuotas', val: cuotasTotal, elId: 'comp-seg-cuotas', color: 'var(--plum)' },
  ].map((s) => ({ ...s, pct: s.val / total * 100 }));

  segs.forEach((s) => { document.getElementById(s.elId).style.width = s.pct + '%'; });

  document.getElementById('comp-labels-row').innerHTML = segs
    .filter((s) => s.pct > 0)
    .map((s) => `
      <div class="composicion-label-item" style="width:${s.pct}%">
        <span class="composicion-label-name">${s.name}</span>
        <span class="composicion-label-val">${fmtARSCompact(s.val)}</span>
      </div>`)
    .join('');

  document.getElementById('comp-legend').innerHTML = segs.map((s) => `
    <div class="composicion-leg-item">
      <span class="composicion-leg-dot" style="background:${s.color}"></span>
      <span>${s.name}</span>
      <span class="composicion-leg-val">${fmtARS(s.val)}</span>
      <span class="composicion-leg-pct">(${s.pct.toFixed(0)}%)</span>
    </div>`).join('');
}

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

function renderGastosPie(rows) {
  categPieCache = rows;
  const filtered = applyPersonaFiltro(rows);
  const grouped = groupBy(filtered, 'categoria');
  const keys = Object.keys(grouped).sort((a, b) => sum(grouped[b], 'monto') - sum(grouped[a], 'monto'));
  const data = keys.map((k) => sum(grouped[k], 'monto'));

  renderPieSubtotals(filtered);

  destroyChart('gastos-pie');
  const canvas = document.getElementById('chart-gastos-pie');
  if (!data.length) {
    document.getElementById('categ-chip-row').innerHTML = '';
    return;
  }

  const toggleBtn = document.getElementById('categ-pie-toggle');
  toggleBtn.textContent = categPieMode === 'doughnut' ? 'barras' : 'torta';

  if (categPieMode === 'bar') {
    const labels = keys.map((k, i) => `${k}  ${fmtARSCompact(data[i])}`);
    charts['gastos-pie'] = new Chart(canvas, {
      type: 'bar',
      data: { labels, datasets: [{ data, backgroundColor: paletteColors(data.length), borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        onClick: (evt, els) => { if (els.length) drillDownToSubcat(keys[els[0].index]); },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ' ' + fmtARS(ctx.raw) } } },
        scales: {
          x: { ticks: { color: INK, font: FONT }, grid: { color: LINE } },
          y: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        },
      },
    });
  } else {
    const total = data.reduce((a, b) => a + b, 0) || 1;
    const labels = keys.map((k, i) => `${iconFor(k)} ${k}  ${((data[i] / total) * 100).toFixed(0)}%`);
    charts['gastos-pie'] = new Chart(canvas, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: paletteColors(data.length), borderColor: '#fffdf7', borderWidth: 2 }] },
      options: {
        cutout: '58%',
        onClick: (evt, els) => { if (els.length) drillDownToSubcat(keys[els[0].index]); },
        plugins: {
          legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12, padding: 10 } },
          tooltip: { callbacks: { label: (ctx) => ' ' + fmtARS(ctx.raw) } },
        },
      },
    });
  }

  document.getElementById('categ-chip-row').innerHTML = keys
    .map((k) => `<button type="button" class="categ-chip" data-cat="${escapeHtml(k)}">${iconFor(k)} ${escapeHtml(k)}</button>`)
    .join('');
  document.querySelectorAll('#categ-chip-row .categ-chip').forEach((chip) => {
    chip.addEventListener('click', () => drillDownToSubcat(chip.dataset.cat));
  });
}

function renderPieSubtotals(filtered) {
  const subtotalsEl = document.getElementById('gastos-pie-subtotals');
  if (personaFiltro === 'comun' && filtered.length) {
    let t1 = 0, t2 = 0;
    filtered.forEach((r) => {
      const monto = parseFloat(r.monto) || 0;
      const { pct1, pct2 } = getRowPct(r);
      t1 += monto * pct1 / 100;
      t2 += monto * pct2 / 100;
    });
    subtotalsEl.hidden = false;
    subtotalsEl.innerHTML = `
      <div class="pie-sub-row"><span>Corresponde a ${P1}</span><span>${fmtARS(t1)}</span></div>
      <div class="pie-sub-row"><span>Corresponde a ${P2}</span><span>${fmtARS(t2)}</span></div>`;
  } else if ((personaFiltro === 'jd_comun' || personaFiltro === 'pinki_comun') && filtered.length) {
    const isJD = personaFiltro === 'jd_comun';
    let comun = 0, propio = 0;
    filtered.forEach((r) => {
      const monto = parseFloat(r.monto) || 0;
      const { pct1, pct2 } = getRowPct(r);
      const pct = isJD ? pct1 : pct2;
      const other = isJD ? pct2 : pct1;
      if (pct === 100) propio += monto;
      else if (pct > 0 && other > 0) comun += monto * pct / 100;
    });
    subtotalsEl.hidden = false;
    subtotalsEl.innerHTML = `
      <div class="pie-sub-row"><span>Común</span><span>${fmtARS(comun)}</span></div>
      <div class="pie-sub-row"><span>Propio</span><span>${fmtARS(propio)}</span></div>`;
  } else {
    subtotalsEl.hidden = true;
  }
}

function toggleGastosCategType() {
  categPieMode = categPieMode === 'doughnut' ? 'bar' : 'doughnut';
  renderGastosPie(categPieCache);
}

function renderGastosBar() {
  destroyChart('gastos-bar');
  const sorted = [...DATA.resumen].sort((a, b) => a.mes.localeCompare(b.mes));
  const real = sorted.filter((r) => r.total_ingresos > 0 || r.total_gastos > 0);
  const last6 = (real.length ? real : sorted).slice(-6);
  charts['gastos-bar'] = new Chart(document.getElementById('chart-gastos-bar'), {
    type: 'bar',
    data: {
      labels: last6.map((r) => shortMonth(r.mes)),
      datasets: [
        { label: 'Gastos', data: last6.map((r) => r.total_gastos), backgroundColor: '#c97d55', borderRadius: 6, maxBarThickness: 26 },
        { label: 'Ingresos', data: last6.map((r) => r.total_ingresos), backgroundColor: '#7c9a6b', borderRadius: 6, maxBarThickness: 26 },
      ],
    },
    options: {
      scales: {
        x: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        y: { ticks: { color: INK, font: FONT, callback: (v) => fmtARSCompact(v) }, grid: { color: LINE } },
      },
      plugins: { legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12 } } },
    },
  });
}

function drillDownToSubcat(cat) {
  activeCat = cat;
  document.getElementById('drilldown-cat-name').textContent = cat;
  const box = document.getElementById('gastos-drilldown-box');
  box.hidden = false;
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  renderSubcatChart(cat);
}

function renderSubcatChart(cat) {
  destroyChart('gastos-subcat');
  const rows = applyPersonaFiltro(filterGastosPeriod(period.from, period.to).filter((r) => r.categoria === cat));
  const grouped = groupBy(rows, 'subcategoria');
  const keys = Object.keys(grouped).filter(Boolean);
  const displayKeys = keys.length ? keys : [cat];
  const data = displayKeys.map((k) => sum(keys.length ? (grouped[k] || []) : rows, 'monto'));
  const total = data.reduce((a, b) => a + b, 0) || 1;

  const btn = document.getElementById('subcat-toggle');
  btn.textContent = subcatMode === 'doughnut' ? 'barras' : 'torta';

  const canvas = document.getElementById('chart-gastos-subcat');
  if (subcatMode === 'bar') {
    const labels = displayKeys.map((k, i) => `${k}  ${fmtARSCompact(data[i])}`);
    charts['gastos-subcat'] = new Chart(canvas, {
      type: 'bar',
      data: { labels, datasets: [{ data, backgroundColor: paletteColors(data.length), borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ' ' + fmtARS(ctx.raw) } } },
        scales: {
          x: { ticks: { color: INK, font: FONT }, grid: { color: LINE } },
          y: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        },
      },
    });
  } else {
    const labels = displayKeys.map((k, i) => `${k}  ${((data[i] / total) * 100).toFixed(0)}%`);
    charts['gastos-subcat'] = new Chart(canvas, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: paletteColors(data.length), borderColor: '#fffdf7', borderWidth: 2 }] },
      options: {
        cutout: '58%',
        plugins: {
          legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12, padding: 10 } },
          tooltip: { callbacks: { label: (ctx) => ' ' + fmtARS(ctx.raw) } },
        },
      },
    });
  }
}

function toggleSubcatType() {
  subcatMode = subcatMode === 'doughnut' ? 'bar' : 'doughnut';
  if (activeCat) renderSubcatChart(activeCat);
}

function resetGastosDrilldown() {
  activeCat = null;
  destroyChart('gastos-subcat');
  const box = document.getElementById('gastos-drilldown-box');
  if (box) box.hidden = true;
}

// ── TABLA DE DETALLE (GASTOS) ────────────────────────────────────────────

function setupTablaCategSelect(periodRows) {
  const select = document.getElementById('filtro-cat-tabla');
  const cats = [...new Set(periodRows.map((r) => r.categoria).filter(Boolean))].sort();
  const prev = tableFiltroCat;
  select.innerHTML = '<option value="">Todas</option>' +
    cats.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  select.value = cats.includes(prev) ? prev : '';
  tableFiltroCat = select.value;
  select.onchange = () => { tableFiltroCat = select.value; renderGastosTable(); };
}

function renderGastosTable() {
  const data = tableFiltroCat ? gastosTableRows.filter((r) => r.categoria === tableFiltroCat) : gastosTableRows;
  const key = TABLE_KEY_MAP[sortState.key] || sortState.key;
  const sorted = [...data].sort((a, b) => {
    const va = a[key], vb = b[key];
    const cmp = key === 'monto'
      ? (parseFloat(va) || 0) - (parseFloat(vb) || 0)
      : String(va || '').localeCompare(String(vb || ''));
    return sortState.dir === 'asc' ? cmp : -cmp;
  });

  document.getElementById('tabla-body').innerHTML = sorted.map((g) => `
    <tr>
      <td class="td-muted">${g.fecha || '—'}</td>
      <td><span class="pill">${iconFor(g.categoria)} ${escapeHtml(g.categoria)}</span></td>
      <td class="td-amount td-accent">${fmtARS(g.monto)}</td>
      <td class="td-muted">${escapeHtml(g.medio_pago)}</td>
      <td><span class="pill ${pillClassFor(g.pagado_por)}">${escapeHtml(g.pagado_por)}</span></td>
      <td class="td-muted">${cuotaLabel(g)}</td>
    </tr>`).join('');

  document.getElementById('tabla-count').textContent = `${sorted.length} de ${gastosTableRows.length} gastos`;

  document.querySelectorAll('#tabla-gastos thead th').forEach((th) => {
    th.querySelector('.arrow')?.remove();
    if (th.dataset.key === sortState.key) {
      th.insertAdjacentHTML('beforeend', `<span class="arrow">${sortState.dir === 'asc' ? '↑' : '↓'}</span>`);
    }
  });
}

document.querySelectorAll('#tabla-gastos thead th[data-key]').forEach((th) => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (sortState.key === key) sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    else sortState = { key, dir: 'asc' };
    renderGastosTable();
  });
});

// ── PANELES DE DETALLE (fijos / cuotas / crédito / deuda) ──────────────

function toggleDetail(kind) {
  const panel = document.getElementById(kind + '-detail');
  const card = document.getElementById('card-' + kind + '-wrap');
  if (!panel) return;
  const opening = panel.hidden;
  panel.hidden = !opening;
  if (card) card.setAttribute('aria-expanded', String(opening));
  if (!opening) return;
  if (kind === 'fijos') renderFijosDetail();
  else if (kind === 'cuotas') renderCuotasDetail();
  else if (kind === 'credito') renderCreditoDetail();
  else if (kind === 'deuda') renderDeudaDetail();
}

function renderFijosDetail() {
  const inner = document.getElementById('fijos-detail-inner');
  const items = activeFijos();
  if (!items.length) {
    inner.innerHTML = '<div class="empty-state">Sin gastos fijos activos.</div>';
    return;
  }
  const sorted = [...items].sort((a, b) => fijoMonthly(b) - fijoMonthly(a));
  const total = sorted.reduce((acc, f) => acc + fijoMonthly(f), 0);
  inner.innerHTML = `
    <table>
      <thead><tr><th>Nombre</th><th>Categoría</th><th>Periodicidad</th><th style="text-align:right">Mensual</th></tr></thead>
      <tbody>
        ${sorted.map((f) => `<tr>
          <td>${escapeHtml(f.nombre)}</td>
          <td class="td-muted">${escapeHtml(f.categoria)}${f.subcategoria ? ' / ' + escapeHtml(f.subcategoria) : ''}</td>
          <td class="td-muted">${capitalize(f.periodicidad)}</td>
          <td class="td-amount td-accent">${fmtARS(fijoMonthly(f))}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="3" class="td-muted">Total mensual</td>
        <td class="td-amount td-accent">${fmtARS(total)}</td>
      </tr></tfoot>
    </table>
    <p class="td-muted" style="font-size:11px;margin-top:8px">
      Los fijos no tienen split JD/Pinki por ítem en los datos migrados — el desglose por
      persona en las cards usa la proporción dinámica del mes de referencia.
    </p>`;
}

function renderCuotasDetail() {
  const inner = document.getElementById('cuotas-detail-inner');
  const rows = applyPersonaFiltro(filterCuotasComprometidas(period.from, period.to))
    .sort((a, b) => (a.fecha || '').localeCompare(b.fecha || ''));
  if (!rows.length) {
    inner.innerHTML = '<div class="empty-state">Sin cuotas comprometidas en este período.</div>';
    return;
  }
  const adjusted = applyPersonaMonto(rows);
  const total = sum(adjusted, 'monto');
  inner.innerHTML = `
    <table>
      <thead><tr><th>Fecha</th><th>Descripción</th><th>Cuota</th><th>Tarjeta</th><th style="text-align:right">Monto</th></tr></thead>
      <tbody>
        ${adjusted.map((r) => `<tr>
          <td class="td-muted">${r.fecha || '—'}</td>
          <td>${escapeHtml(r.descripcion_original)}</td>
          <td class="td-muted">${cuotaLabel(r)}</td>
          <td class="td-muted">${escapeHtml(r.tarjeta_id)}</td>
          <td class="td-amount td-accent">${fmtARS(r.monto)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="4" class="td-muted">Total cuotas</td>
        <td class="td-amount td-accent">${fmtARS(total)}</td>
      </tr></tfoot>
    </table>`;
}

function renderCreditoDetail() {
  const inner = document.getElementById('credito-detail-inner');
  const rows = applyPersonaFiltro(filterGastosPeriod(period.from, period.to).filter((r) => r.medio_pago === 'Crédito'));
  if (!rows.length) {
    inner.innerHTML = '<div class="empty-state">Sin cargos en crédito en este período.</div>';
    return;
  }
  const groups = {};
  rows.forEach((r) => {
    const key = r.tarjeta_id || 'Sin tarjeta';
    (groups[key] = groups[key] || []).push(r);
  });
  const total = sum(applyPersonaMonto(rows), 'monto');
  const tarjetaKeys = Object.keys(groups).sort();

  inner.innerHTML = tarjetaKeys.map((tid) => {
    const items = applyPersonaMonto(groups[tid]).sort((a, b) => (b.monto || 0) - (a.monto || 0));
    const subtotal = sum(items, 'monto');
    return `
      <div class="credito-tarjeta-header">${escapeHtml(tid)} · ${fmtARS(subtotal)}</div>
      <table>
        <thead><tr><th>Fecha</th><th>Descripción</th><th>Categoría</th><th style="text-align:right">Monto</th></tr></thead>
        <tbody>
          ${items.map((r) => `<tr>
            <td class="td-muted">${r.fecha || '—'}</td>
            <td>${escapeHtml(r.descripcion_original)}</td>
            <td class="td-muted">${escapeHtml(r.categoria)}</td>
            <td class="td-amount td-accent">${fmtARS(r.monto)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }).join('') + `<div class="credito-tarjeta-header">Total crédito · ${fmtARS(total)}</div>`;
}

// Detalle de deuda: muestra el saldo pendiente actual (mismo dato que la
// card), no un histórico mes a mes de deudas ya saldadas — Juan pidió
// explícitamente no ver eso. data/deuda_pendiente.json es un agregado (no
// tiene desglose por gasto individual en este snapshot).
function renderDeudaDetail() {
  const inner = document.getElementById('deuda-detail-inner');
  const d = DATA.deudaPendiente;
  if (!d || !d.deudor) {
    inner.innerHTML = '<div class="empty-state">Sin deuda pendiente — todo saldado.</div>';
    return;
  }
  inner.innerHTML = `
    <table>
      <thead><tr><th>Deudor</th><th>Acreedor</th><th style="text-align:right">Monto pendiente</th></tr></thead>
      <tbody>
        <tr>
          <td>${escapeHtml(d.deudor)}</td>
          <td>${escapeHtml(d.acreedor)}</td>
          <td class="td-amount td-accent">${fmtARS(d.monto)}</td>
        </tr>
      </tbody>
    </table>
    <p class="detail-note">Suma de todos los gastos compartidos aún no saldados entre JD y
    Pinki, sin importar de qué mes sean. No incluye lo ya compensado.</p>`;
}

// ── VISTA INGRESOS ───────────────────────────────────────────────────────

function renderIngresosView() {
  const rows = filterIngresosPeriod(period.from, period.to);
  const total = sum(rows, 'monto');
  const totalP1 = sum(rows.filter((r) => r.persona === P1), 'monto');
  const totalP2 = sum(rows.filter((r) => r.persona === P2), 'monto');

  document.getElementById('inc-total').textContent = fmtARS(total);
  document.getElementById('inc-p1').textContent = fmtARS(totalP1);
  document.getElementById('inc-p2').textContent = fmtARS(totalP2);

  let entry = period.type === 'month' ? DATA.resumen.find((r) => r.mes === period.refMonth) : null;
  if (!entry) entry = getLatestRealMonth(DATA.resumen);
  if (entry) {
    document.getElementById('inc-proporcion').textContent =
      `${P1} ${entry.proporcion_jd.toFixed(0)}% · ${P2} ${entry.proporcion_pinki.toFixed(0)}%`;
    document.getElementById('inc-proporcion-source').textContent = mesLabel(entry.mes);
  }

  renderIncomeLines();

  const sorted = [...rows].sort((a, b) => (b.fecha || '').localeCompare(a.fecha || ''));
  document.getElementById('tabla-ingresos-body').innerHTML = sorted.length ? sorted.map((r) => `
    <tr>
      <td class="td-muted">${r.fecha || '—'}</td>
      <td><span class="pill">${escapeHtml(r.categoria)}</span></td>
      <td>${escapeHtml(r.descripcion_original)}</td>
      <td><span class="pill ${pillClassFor(r.persona)}">${escapeHtml(r.persona)}</span></td>
      <td class="td-amount td-accent">${fmtARS(r.monto)}</td>
    </tr>`).join('') : '';
}

function renderIncomeLines() {
  destroyChart('inc-lines');
  const sorted = [...DATA.resumen].sort((a, b) => a.mes.localeCompare(b.mes));
  const real = sorted.filter((r) => r.total_ingresos > 0);
  const months = (real.length ? real : sorted).slice(-6).map((r) => r.mes);
  const dataP1 = months.map((m) => sum(DATA.ingresos.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P1), 'monto'));
  const dataP2 = months.map((m) => sum(DATA.ingresos.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P2), 'monto'));

  charts['inc-lines'] = new Chart(document.getElementById('chart-inc-lines'), {
    type: 'line',
    data: {
      labels: months.map(shortMonth),
      datasets: [
        { label: P1, data: dataP1, borderColor: '#c97d55', backgroundColor: 'transparent', borderWidth: 2, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#c97d55' },
        { label: P2, data: dataP2, borderColor: '#d1a13f', backgroundColor: 'transparent', borderWidth: 2, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#d1a13f' },
      ],
    },
    options: {
      scales: {
        x: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        y: { ticks: { color: INK, font: FONT, callback: (v) => fmtARSCompact(v) }, grid: { color: LINE } },
      },
      plugins: { legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12 } } },
    },
  });
}

loadAll();
