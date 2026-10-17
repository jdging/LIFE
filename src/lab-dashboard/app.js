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
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(parseFloat(n) || 0);
const fmtARSExact = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n));
const fmtARSCompact = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', notation: 'compact', maximumFractionDigits: 1 }).format(parseFloat(n) || 0);
const paletteColors = (n) => Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);

function thisMonth() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}
function todayLocalISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function firstAvailableDate() {
  const dates = [
    ...DATA.gastos.map((row) => row.fecha),
    ...DATA.ingresos.map((row) => row.fecha),
    ...DATA.fijos.map((row) => row.vigente_desde),
  ].filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date) && date <= todayLocalISO());
  return dates.length ? dates.sort()[0] : todayLocalISO();
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

const DATA = {
  gastos: [], ingresos: [], fijos: [], resumen: [], deudaPendiente: null,
  loadErrors: {}, compras: null, comprasError: null, recetas: null, recetasError: null,
};
const charts = {};
let period = null;
let currentView = 'gastos';
// Destinos con pestaña visible en nav.view-tabs. 'inversiones' y 'presupuesto'
// siguen en el DOM (código/panel conservado) pero switchView los ignora: no
// tienen botón de tab y no deben quedar accesibles desde la navegación.
const VISIBLE_VIEWS = ['gastos', 'ingresos', 'fijos', 'supermercado', 'recetas'];
const ALL_VIEWS = [...VISIBLE_VIEWS, 'inversiones', 'presupuesto'];
let comprasLoaded = false;
let recetasLoaded = false;
let personaFiltro = 'comun';
let categPieMode = 'doughnut';
let subcatMode = 'doughnut';
let activeCat = null;
let categPieCache = [];
let gastosTableRows = [];
let tableFiltroCat = '';
let sortState = { key: 'fecha', dir: 'desc' };
let fijosMode = 'vigentes';
let fijosSelectedGroup = null;
let fijosChart = null;
let liveMode = false;
let authState = 'unknown';
let writePending = false;
let reloadPending = false;
let reloadFailed = false;
let activeForm = null;
const TABLE_KEY_MAP = { monto_total: 'monto', pago: 'pagado_por' };

// ── CARGA DE DATOS ───────────────────────────────────────────────────────

async function fetchJSON(path) {
  const res = await fetch(path, { credentials: 'same-origin' });
  if (!res.ok) {
    const error = new Error(`HTTP ${res.status} al cargar ${path}`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

function requireList(value, key) {
  if (!value || !Array.isArray(value[key])) throw new Error(`Respuesta inválida: ${key}`);
  return value[key];
}

const MAX_SQLITE_ID = '9223372036854775807';
function canonicalId(value) {
  const id = typeof value === 'number' && Number.isSafeInteger(value) ? String(value) : value;
  if (typeof id !== 'string' || !/^[1-9]\d*$/.test(id) ||
      id.length > MAX_SQLITE_ID.length ||
      (id.length === MAX_SQLITE_ID.length && id > MAX_SQLITE_ID)) {
    throw new Error('ID inválido o numérico inseguro: la identidad no se puede verificar.');
  }
  return id;
}

function compareIds(left, right) {
  const a = canonicalId(left);
  const b = canonicalId(right);
  return a.length - b.length || (a < b ? -1 : a > b ? 1 : 0);
}

function fixedGroupId(row) {
  return canonicalId(row.fijo_grupo_id == null ? row.id : row.fijo_grupo_id);
}

function adaptLiveMovement(row) {
  const date = typeof row?.fecha === 'string' ? row.fecha.slice(0, 10) : '';
  if (!validDate(date)) throw new Error('Movimiento con fecha inválida.');
  return { ...row, id: canonicalId(row.id), fecha: date };
}

function adaptLiveFixed(row) {
  const id = canonicalId(row?.id);
  return { ...row, id, fijo_grupo_id: row.fijo_grupo_id == null ? null : canonicalId(row.fijo_grupo_id) };
}

function adaptSummary(row) {
  if (!row || typeof row.month !== 'string' || !validDate(`${row.month}-01`) ||
      !row.proportion || typeof row.proportion !== 'object') {
    throw new Error('Resumen mensual inválido');
  }
  // El dominio devuelve los nombres de persona como claves; cero es un porcentaje válido.
  const jd = row.proportion.JD;
  const pinki = row.proportion.Pinki;
  const valid = typeof jd === 'number' && typeof pinki === 'number' &&
    Number.isFinite(jd) && Number.isFinite(pinki) && jd >= 0 && pinki >= 0 &&
    Math.abs(jd + pinki - 100) < .001;
  if (!valid) throw new Error('La proporción de la API no tiene porcentajes verificables.');
  if (![row.income_total, row.expenses_total, row.fixed_total_mensual]
      .every((amount) => typeof amount === 'number' && Number.isFinite(amount) && amount >= 0)) {
    throw new Error('Los totales del resumen mensual no son verificables.');
  }
  const debtMonth = adaptCurrentDebt(row.debt_month);
  const debtPending = adaptCurrentDebt(row.debt_pending_through_month);
  if (!debtMonth || !debtPending || typeof row.debt_status !== 'string' || !row.debt_status) {
    throw new Error('La deuda del resumen mensual no es verificable.');
  }
  return {
    mes: row.month, total_ingresos: row.income_total, total_gastos: row.expenses_total,
    total_fijos: row.fixed_total_mensual,
    proporcion_jd: jd, proporcion_pinki: pinki,
    debt_month: debtMonth, debt_pending_through_month: debtPending,
    debt_status: row.debt_status,
  };
}

function adaptCurrentDebt(value) {
  if (!value || typeof value !== 'object') return null;
  if (value.deudor === null && value.acreedor === null && value.monto === 0) {
    return { deudor: null, acreedor: null, monto: 0 };
  }
  if (!['JD', 'Pinki'].includes(value.deudor) || !['JD', 'Pinki'].includes(value.acreedor) ||
      value.deudor === value.acreedor || typeof value.monto !== 'number' ||
      !Number.isFinite(value.monto) || value.monto <= 0) return null;
  return { deudor: value.deudor, acreedor: value.acreedor, monto: value.monto };
}

async function loadLive() {
  const currentMonth = thisMonth();
  const [expenses, income, versions, summary, currentSummary] = await Promise.all([
    fetchJSON('/api/expenses'), fetchJSON('/api/income'),
    fetchJSON('/api/fixed/versions'), fetchJSON('/api/summary'),
    fetchJSON(`/api/summary?month=${currentMonth}`),
  ]);
  const months = requireList(summary, 'months').map(adaptSummary);
  const current = adaptSummary(currentSummary);
  if (current.mes !== currentMonth) throw new Error('El resumen actual no coincide con el mes solicitado.');
  const currentIndex = months.findIndex((row) => row.mes === currentMonth);
  if (currentIndex >= 0) months[currentIndex] = current;
  else months.push(current);
  months.sort((a, b) => a.mes.localeCompare(b.mes));
  const next = {
    gastos: requireList(expenses, 'expenses').map(adaptLiveMovement),
    ingresos: requireList(income, 'income').map(adaptLiveMovement),
    fijos: requireList(versions, 'versions').map(adaptLiveFixed),
    resumen: months,
  };
  Object.assign(DATA, next, { loadErrors: {}, deudaPendiente: current.debt_pending_through_month });
  liveMode = true;
  authState = 'authenticated';
  reloadFailed = false;
  updateAvailability();
  if (period) renderView(currentView);
}

async function loadSnapshot() {
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
  DATA.loadErrors = {
    gastos: g.status === 'rejected',
    ingresos: i.status === 'rejected',
    fijos: f.status === 'rejected',
    resumen: r.status === 'rejected',
    deudaPendiente: d.status === 'rejected',
  };
  updateAvailability();
  if (period) renderView(currentView);
}

async function loadAll() {
  authState = 'unavailable';
  liveMode = false;
  updateAvailability();
  try {
    const health = await fetchJSON('/api/health');
    if (health?.ok !== true || health.mode !== 'live' ||
        !Array.isArray(health.capabilities) ||
        !['expenses', 'income', 'fixed'].every((cap) => health.capabilities.includes(cap))) {
      throw new Error('API no disponible para formularios');
    }
    authState = 'authenticated';
    await loadLive();
  } catch (error) {
    if (error.status === 401) authState = 'unavailable';
    liveMode = false;
    reloadFailed = false;
    await loadSnapshot();
  }

  period = computePeriod('month', { month: thisMonth() });
  document.getElementById('month-picker').value = period.refMonth;
  switchView('gastos');
}

function updateAvailability() {
  const status = document.getElementById('api-status');
  status.textContent = liveMode
    ? (reloadFailed
      ? 'Conexión autenticada · guardado confirmado, pero el panel no pudo actualizarse. Nuevas escrituras pausadas hasta reintentar la lectura.'
      : (writePending || reloadPending)
        ? 'Conexión autenticada · procesando el cambio y actualizando el panel.'
        : 'Conexión autenticada · datos en vivo. Escrituras disponibles.')
    : (authState === 'authenticated'
      ? 'Conexión autenticada · los datos live no se pudieron verificar. Modo snapshot de solo lectura; no se pueden guardar cambios.'
      : 'Modo snapshot · solo lectura. La conexión autenticada no está disponible; no se pueden guardar cambios.');
  status.classList.toggle('status-live', liveMode);
  document.querySelectorAll('[data-write-action]').forEach((button) => {
    button.disabled = !liveMode || writePending || reloadPending || reloadFailed;
  });
  document.querySelector('.fijos-snapshot').textContent = liveMode
    ? (reloadFailed ? 'La recarga falló; los datos visibles pueden estar desactualizados.'
      : 'Datos en vivo. Cada cambio de un fijo conserva las versiones anteriores.')
    : 'Snapshot de lectura. Los formularios se habilitan al restablecer la conexión autenticada.';
  document.getElementById('footer-status').textContent = liveMode
    ? (reloadFailed ? 'Recarga pendiente' : 'Datos en vivo') : 'Snapshot de solo lectura';
}

// ── NAVEGACIÓN ───────────────────────────────────────────────────────────

// Solo los destinos en VISIBLE_VIEWS son alcanzables por esta función — evita
// que un onclick mal formado o un enlace viejo deje 'inversiones'/'presupuesto'
// visibles sin su pestaña correspondiente.
function switchView(v) {
  if (!VISIBLE_VIEWS.includes(v)) return;
  const focusWasInPanel = document.getElementById('view-' + currentView)?.contains(document.activeElement);
  currentView = v;
  ALL_VIEWS.forEach((name) => {
    const tab = document.getElementById('tab-' + name);
    const panel = document.getElementById('view-' + name);
    const isActive = name === v;
    if (tab) {
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', String(isActive));
      tab.tabIndex = isActive ? 0 : -1;
    }
    if (panel) {
      panel.classList.toggle('active', isActive);
      panel.hidden = !isActive;
    }
  });
  const topbar = document.getElementById('finanzas-topbar');
  if (topbar) topbar.hidden = !(v === 'gastos' || v === 'ingresos');
  renderView(v);
  if (focusWasInPanel) document.getElementById('tab-' + v).focus();
}

function renderView(v) {
  if (v === 'gastos') renderGastosView();
  else if (v === 'ingresos') renderIngresosView();
  else if (v === 'fijos') renderFijosView();
  else if (v === 'supermercado') ensureComprasLoaded();
  else if (v === 'recetas') ensureRecetasLoaded();
  // Inversiones y Presupuesto se quedan en el estado vacío ya maquetado en index.html.
}

// ── PERÍODO ──────────────────────────────────────────────────────────────

function computePeriod(type, opts = {}) {
  const todayDate = todayLocalISO();
  const today = todayDate.slice(0, 7);
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
      from = m + '-01'; to = fijosLastDay(m); refMonth = m; break;
    }
    case 'quarter':
      from = nMonthsAgo(2) + '-01'; to = todayDate; refMonth = today; break;
    case 'semester':
      from = nMonthsAgo(5) + '-01'; to = todayDate; refMonth = today; break;
    case 'year':
      from = cy + '-01-01'; to = todayDate; refMonth = today; break;
    case 'all':
      from = firstAvailableDate(); to = todayDate; refMonth = today; break;
    case 'range':
      from = opts.from || firstAvailableDate(); to = opts.to && opts.to < todayDate ? opts.to : todayDate;
      refMonth = to.substring(0, 7); break;
    default:
      from = null; to = null; refMonth = today;
  }
  if (to && to > todayDate) to = todayDate;
  return { type, from, to, refMonth };
}

function getMonthsInPeriod(from, to) {
  if (!from || !to || from > to) return [];
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
    const pjd = (raw !== undefined && raw !== null && raw !== '') ? Number(raw) : NaN;
    return Number.isFinite(pjd) && pjd >= 0 && pjd <= 100
      ? { pct1: pjd, pct2: 100 - pjd } : { pct1: 0, pct2: 0 };
  }
  const mes = row.fecha ? String(row.fecha).slice(0, 7) : null;
  const entry = mes ? DATA.resumen.find((r) => r.mes === mes) : null;
  if (entry && Number.isFinite(entry.proporcion_jd) && Number.isFinite(entry.proporcion_pinki)) {
    return { pct1: entry.proporcion_jd, pct2: entry.proporcion_pinki };
  }
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

function fijosLastDay(month) {
  const [year, number] = month.split('-').map(Number);
  return new Date(Date.UTC(year, number, 0)).toISOString().slice(0, 10);
}

function fijosPreviousDay(date) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - 1);
  return value.toISOString().slice(0, 10);
}

function fijosVersionVigente(rows, grupoId, fecha) {
  return rows.filter((row) => fixedGroupId(row) === canonicalId(grupoId) && row.vigente_desde <= fecha)
    .sort((a, b) => b.vigente_desde.localeCompare(a.vigente_desde) || compareIds(b.id, a.id))[0] || null;
}

function fijosVigentes(rows, fecha) {
  const ids = [...new Set(rows.map(fixedGroupId))];
  return ids.map((id) => fijosVersionVigente(rows, id, fecha))
    .filter((row) => row && Number(row.activo) === 1)
    .sort((a, b) => compareIds(fixedGroupId(a), fixedGroupId(b)));
}

function fijosHistorial(rows, grupoId) {
  const sorted = rows.filter((row) => fixedGroupId(row) === canonicalId(grupoId))
    .sort((a, b) => a.vigente_desde.localeCompare(b.vigente_desde) || compareIds(a.id, b.id));
  return sorted.map((row, index) => {
    const next = sorted[index + 1];
    const sameDay = !!next && next.vigente_desde === row.vigente_desde;
    return {
      ...row,
      supersedida_mismo_dia: sameDay,
      tiene_intervalo_vigencia: !sameDay,
      vigente_hasta: sameDay ? null : next ? fijosPreviousDay(next.vigente_desde) : null,
    };
  });
}

function fijosTramos(rows, desde, hasta) {
  if (desde > hasta) return [];
  const ids = [...new Set(rows.map(fixedGroupId))].sort(compareIds);
  return ids.flatMap((id) => fijosHistorial(rows, id)
    .filter((row) => (row.tiene_intervalo_vigencia !== false)
      && row.vigente_desde <= hasta && (!row.vigente_hasta || row.vigente_hasta >= desde))
    .map((row) => ({
      ...row,
      fijo_grupo_id: fixedGroupId(row),
      tramo_desde: row.vigente_desde > desde ? row.vigente_desde : desde,
      tramo_hasta: row.vigente_hasta && row.vigente_hasta < hasta ? row.vigente_hasta : hasta,
    })));
}

function fijosTotalMes(rows, month) {
  return fijosVigentes(rows, fijosLastDay(month))
    .reduce((total, row) => total + Number(row.monto_mensual || 0), 0);
}

function fijosEvolutionData(versions) {
  const points = versions.filter((row) => row.tiene_intervalo_vigencia !== false);
  return {
    dates: points.map((row) => row.vigente_desde),
    amounts: points.map((row) => Number(row.activo) === 0 ? 0 : Number(row.monto_mensual)),
  };
}

function gastosTotalState(varTotal, fixedTotal, cuotasTotal, fixedAvailable) {
  return fixedAvailable
    ? { total: varTotal + fixedTotal + cuotasTotal, partial: null }
    : { total: null, partial: varTotal + cuotasTotal };
}

function fixedCutoffDate() {
  return period.to || todayLocalISO();
}

function activeFijos() {
  return fijosVigentes(DATA.fijos, fixedCutoffDate());
}

function fixedMonths() {
  return getMonthsInPeriod(period.from, period.to);
}

function fixedMonthCutoff(month) {
  const lastDay = fijosLastDay(month);
  return period.to && period.to < lastDay ? period.to : lastDay;
}

function fixedAllocation(row, month) {
  if (row.responsable === 'JD') return { pct1: 100, pct2: 0 };
  if (row.responsable === 'Pinki') return { pct1: 0, pct2: 100 };
  if (row.responsable !== 'Común') return { pct1: 0, pct2: 0 };
  const type = String(row.tipo_proporcion || '').toLowerCase().trim();
  if (type === '50/50') return { pct1: 50, pct2: 50 };
  if (type === 'custom') {
    const raw = row.proporcion_jd;
    const pct1 = raw !== null && raw !== undefined && raw !== '' ? Number(raw) : NaN;
    return Number.isFinite(pct1) && pct1 >= 0 && pct1 <= 100
      ? { pct1, pct2: 100 - pct1 } : { pct1: 0, pct2: 0 };
  }
  const exact = DATA.resumen.find((entry) => entry.mes === month);
  const previous = DATA.resumen.filter((entry) => entry.mes <= month && Number(entry.total_ingresos) > 0)
    .sort((a, b) => b.mes.localeCompare(a.mes))[0];
  const entry = exact || previous;
  const pct1 = Number(entry?.proporcion_jd);
  const pct2 = Number(entry?.proporcion_pinki);
  return Number.isFinite(pct1) && Number.isFinite(pct2) && pct1 + pct2 === 100
    ? { pct1, pct2 } : { pct1: 50, pct2: 50 };
}

function computeFixedForPersona(filtro) {
  return fixedMonths().reduce((total, month) => {
    const monthRows = fijosVigentes(DATA.fijos, fixedMonthCutoff(month));
    return total + monthRows.reduce((subtotal, row) => {
      const amount = Number(row.monto_mensual || 0);
      if (filtro === 'comun') return subtotal + amount;
      const { pct1, pct2 } = fixedAllocation(row, month);
      if (filtro === 'jd') return subtotal + (pct1 === 100 ? amount : 0);
      if (filtro === 'pinki') return subtotal + (pct2 === 100 ? amount : 0);
      if (filtro === 'jd_comun') return subtotal + amount * pct1 / 100;
      if (filtro === 'pinki_comun') return subtotal + amount * pct2 / 100;
      return subtotal;
    }, 0);
  }, 0);
}

function fijosDateLabel(date) {
  if (!date) return 'vigente';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return 'fecha no disponible';
  const [year, month, day] = date.split('-');
  return `${day}/${month}/${year}`;
}

function fijosResponsable(row) {
  return row.responsable || 'Sin asignar';
}

function fijosRepartoLabel(row) {
  if (row.responsable === 'JD' || row.responsable === 'Pinki') return '100% personal';
  if (row.responsable !== 'Común') return 'Sin reparto asignado';
  if (row.tipo_proporcion === 'custom' && row.proporcion_jd !== null && Number.isFinite(Number(row.proporcion_jd))) {
    return `${row.proporcion_jd}% JD / ${100 - Number(row.proporcion_jd)}% Pinki`;
  }
  return 'Dinámico según salarios';
}

function setFijosMode(mode) {
  if (mode !== 'vigentes' && mode !== 'historial') return;
  fijosMode = mode;
  for (const name of ['vigentes', 'historial']) {
    const active = name === mode;
    const button = document.getElementById(`fijos-mode-${name}`);
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    document.getElementById(`fijos-${name}`).hidden = !active;
  }
  renderFijosView();
}

function renderFijosView() {
  const current = document.getElementById('fijos-current-list');
  const history = document.getElementById('fijos-history-list');
  const detail = document.getElementById('fijos-series-detail');
  if (DATA.loadErrors.fijos) {
    const error = '<div class="section-error" role="alert">No se pudo cargar data/gastos_fijos.json. La lectura no está confirmada; el listado puede estar desactualizado.</div>';
    current.innerHTML = error;
    history.innerHTML = error;
    document.getElementById('fijos-totals').innerHTML = '';
    detail.hidden = true;
    return;
  }

  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const currentRows = fijosVigentes(DATA.fijos, todayIso).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  const split = { 'Común': 0, JD: 0, Pinki: 0, 'Sin asignar': 0 };
  currentRows.forEach((row) => { split[fijosResponsable(row)] += Number(row.monto_mensual || 0); });
  const total = Object.values(split).reduce((value, amount) => value + amount, 0);
  document.getElementById('fijos-totals').innerHTML = `
    <div class="fijos-total-main"><span>Total mensual vigente · ${fijosDateLabel(todayIso)}</span><strong>${fmtARS(total)}</strong></div>
    <div class="fijos-total-split">${Object.entries(split).map(([name, amount]) => `<span><span class="pill ${pillClassFor(name)}">${name}</span> ${fmtARS(amount)}</span>`).join('')}</div>`;
  current.innerHTML = currentRows.length ? currentRows.map((row) => `
    <article class="fijos-item">
      <div class="fijos-item-head"><h3>${escapeHtml(row.nombre)}</h3><strong>${fmtARS(row.monto_mensual)} <small>/ mes</small></strong></div>
      <p>${capitalize(escapeHtml(row.periodicidad))}${row.periodicidad === 'bimestral' ? ` · bruto ${fmtARS(row.monto_estimado)} cada 2 meses` : ''}</p>
      <p><span class="pill ${pillClassFor(row.responsable)}">${escapeHtml(fijosResponsable(row))}</span> <span class="td-muted">desde ${fijosDateLabel(row.vigente_desde)}</span></p>
      <div class="fijos-actions">
        <button type="button" class="fijos-secondary" data-id="${escapeHtml(fixedGroupId(row))}" onclick="openFijosDetail(this.dataset.id)">Ver detalle e historial</button>
        <button type="button" class="fijos-secondary" data-write-action data-id="${escapeHtml(fixedGroupId(row))}" onclick="openFijosInfo('editar', this.dataset.id)" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Editar</button>
        <button type="button" class="fijos-secondary" data-write-action data-id="${escapeHtml(fixedGroupId(row))}" onclick="openFijosInfo('baja', this.dataset.id)" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Dar de baja</button>
      </div>
    </article>`).join('') : '<div class="empty-state-panel">No hay gastos fijos vigentes a hoy.</div>';

  const startInput = document.getElementById('fijos-desde');
  const endInput = document.getElementById('fijos-hasta');
  if (!startInput.value) startInput.value = DATA.fijos.reduce((first, row) => !first || row.vigente_desde < first ? row.vigente_desde : first, todayIso).slice(0, 7);
  if (!endInput.value) endInput.value = todayIso.slice(0, 7);
  const errorEl = document.getElementById('fijos-range-error');
  const invalid = startInput.value > endInput.value;
  errorEl.hidden = !invalid;
  errorEl.textContent = invalid ? 'El mes inicial debe ser anterior o igual al mes final.' : '';
  if (invalid) history.innerHTML = '';
  else {
    const tramos = fijosTramos(DATA.fijos, `${startInput.value}-01`, fijosLastDay(endInput.value));
    const ids = [...new Set(tramos.map((row) => row.fijo_grupo_id))];
    history.innerHTML = ids.length ? ids.map((id) => {
      const group = tramos.filter((row) => fixedGroupId(row) === id);
      const latest = fijosHistorial(DATA.fijos, id).at(-1);
      return `<article class="panel fijos-history-group">
        <div class="fijos-history-head"><h3>${escapeHtml(latest.nombre)}${Number(latest.activo) === 0 ? ' <span class="pill">Dado de baja</span>' : ''}</h3>
          <button type="button" class="fijos-secondary" data-id="${escapeHtml(id)}" onclick="openFijosDetail(this.dataset.id)">Ver detalle</button></div>
        <div class="fijos-tramos">${group.map((row) => `<div class="fijos-tramo">
          <strong>${fijosDateLabel(row.tramo_desde)} a ${fijosDateLabel(row.tramo_hasta)}</strong>
          <span>${escapeHtml(row.nombre)} · ${fmtARS(row.monto_mensual)}/mes${row.periodicidad === 'bimestral' ? ` · bruto ${fmtARS(row.monto_estimado)} bimestral` : ''}</span>
          <span class="pill ${pillClassFor(row.responsable)}">${escapeHtml(fijosResponsable(row))}</span>
          ${Number(row.activo) === 0 ? '<span class="pill">Baja</span>' : ''}
        </div>`).join('')}</div>
      </article>`;
    }).join('') : '<div class="empty-state-panel">No hay tramos de fijos en este período.</div>';
  }
  if (fijosSelectedGroup !== null) renderFijosSeriesDetail(fijosSelectedGroup);
}

function openFijosDetail(groupId) {
  fijosSelectedGroup = groupId;
  renderFijosSeriesDetail(groupId);
  document.getElementById('fijos-series-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeFijosDetail() {
  fijosSelectedGroup = null;
  document.getElementById('fijos-series-detail').hidden = true;
  if (fijosChart) { fijosChart.destroy(); fijosChart = null; }
}

function renderFijosSeriesDetail(groupId) {
  const versions = fijosHistorial(DATA.fijos, groupId);
  if (!versions.length) return closeFijosDetail();
  const detail = document.getElementById('fijos-series-detail');
  detail.hidden = false;
  const latest = versions.at(-1);
  if (fijosChart) { fijosChart.destroy(); fijosChart = null; }
  detail.innerHTML = `<div class="fijos-history-head"><h2>Historial de ${escapeHtml(latest.nombre)}</h2>
    <button type="button" class="fijos-secondary" onclick="closeFijosDetail()">Cerrar detalle</button></div>
    <p class="td-muted">Serie #${escapeHtml(groupId)}. Cada cambio crea una versión; las anteriores se conservan.</p>
    <div class="fijos-version-list"><table class="fijos-versions-table">
      <thead><tr><th>Desde</th><th>Hasta</th><th>Descripción</th><th>Monto mensual</th><th>Responsable</th><th>Reparto</th><th>Estado</th><th>Cambios</th></tr></thead>
      <tbody>${[...versions].reverse().map((row) => {
      const previous = versions[versions.findIndex((item) => canonicalId(item.id) === canonicalId(row.id)) - 1];
      const changes = previous ? [
        previous.nombre !== row.nombre ? 'Descripción' : null,
        previous.monto_mensual !== row.monto_mensual ? 'Monto' : null,
        previous.responsable !== row.responsable ? 'Responsable' : null,
        previous.tipo_proporcion !== row.tipo_proporcion || previous.proporcion_jd !== row.proporcion_jd ? 'Reparto' : null,
        previous.periodicidad !== row.periodicidad ? 'Periodicidad' : null,
        Number(previous.activo) !== Number(row.activo) ? 'Estado' : null,
      ].filter(Boolean) : [];
      const status = Number(row.activo) === 0 ? 'Baja' : canonicalId(row.id) === canonicalId(latest.id) ? 'Vigente' : 'Histórica';
      return `<tr>
        <td data-label="Desde">${fijosDateLabel(row.vigente_desde)}</td>
        <td data-label="Hasta">${row.supersedida_mismo_dia ? 'reemplazada ese día' : row.vigente_hasta ? fijosDateLabel(row.vigente_hasta) : 'vigente'}</td>
        <td data-label="Descripción">${escapeHtml(row.nombre)}</td>
        <td data-label="Monto mensual">${fmtARS(row.monto_mensual)}${row.periodicidad === 'bimestral' ? `<small>bruto ${fmtARS(row.monto_estimado)}</small>` : ''}</td>
        <td data-label="Responsable"><span class="pill ${pillClassFor(row.responsable)}">${escapeHtml(fijosResponsable(row))}</span></td>
        <td data-label="Reparto">${escapeHtml(fijosRepartoLabel(row))}</td>
        <td data-label="Estado"><span class="pill">${status}</span></td>
        <td data-label="Cambios" class="fijos-changes">${changes.length ? changes.join(', ') : previous ? 'Sin cambio en los campos mostrados' : 'Alta inicial'}</td>
      </tr>`;
    }).join('')}</tbody></table></div>
    <h3>Evolución del monto mensual</h3>
    <div class="fijos-chart-wrap"><canvas id="fijos-evolution-chart" aria-label="Gráfico de evolución del monto mensual" role="img"></canvas></div>
    <p class="chart-error" id="fijos-chart-error" role="alert" hidden>No se pudo mostrar el gráfico. El historial sigue disponible arriba.</p>`;
  try {
    if (typeof Chart === 'undefined') throw new Error('Chart.js no disponible');
    const evolution = fijosEvolutionData(versions);
    fijosChart = new Chart(document.getElementById('fijos-evolution-chart'), {
      type: 'line',
      data: { labels: evolution.dates.map(fijosDateLabel), datasets: [{
        label: 'Monto mensual', data: evolution.amounts,
        // Cada punto inicia una versión: el monto previo llega hasta esa fecha.
        stepped: 'after', borderColor: '#5f7d52', backgroundColor: '#7c9a6b', tension: 0, pointRadius: 4,
      }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  } catch (error) {
    document.getElementById('fijos-evolution-chart').parentElement.hidden = true;
    document.getElementById('fijos-chart-error').hidden = false;
  }
}

function openFijosInfo(action, groupId = null) {
  const row = groupId === null ? null : fijosVersionVigente(DATA.fijos, groupId, todayLocalISO());
  if (action === 'agregar') openForm('fixed');
  if (action === 'editar' && row) openForm('fixed-edit', row.id);
  if (action === 'baja' && row) openForm('fixed-delete', row.id);
}

function formField(name, label, value = '', type = 'text', extra = '') {
  return `<label class="form-field" for="field-${name}">${label}
    <input id="field-${name}" name="${name}" type="${type}" value="${escapeHtml(value)}" ${extra} aria-describedby="error-${name}">
    <span class="field-error" id="error-${name}"></span></label>`;
}

function formSelect(name, label, choices, value) {
  return `<label class="form-field" for="field-${name}">${label}<select id="field-${name}" name="${name}" aria-describedby="error-${name}">
    ${choices.map((choice) => {
      const key = typeof choice === 'string' ? choice : choice.value;
      const title = typeof choice === 'string' ? choice : choice.label;
      return `<option value="${escapeHtml(key)}" ${key === value ? 'selected' : ''}>${escapeHtml(title)}</option>`;
    }).join('')}
    </select><span class="field-error" id="error-${name}"></span></label>`;
}

function formMarkup(kind, row) {
  if (kind === 'expense-delete') return `<p>Se dará de baja únicamente esta fila: ${escapeHtml(row.descripcion_original || row.categoria)} · ${escapeHtml(row.fecha)} · cuota ${cuotaLabel(row)} · ${fmtARSExact(row.monto)}. Las demás cuotas permanecen.</p>`;
  if (kind === 'fixed-delete') return `<p>La baja de ${escapeHtml(row.nombre)} crea una versión inactiva. El historial permanece.</p>${formField('fecha_baja', 'Fecha de baja', todayLocalISO(), 'date', 'required')}`;
  if (kind === 'expense') {
    const categories = [...new Set(DATA.gastos.map((item) => item.categoria).filter(Boolean))].sort();
    const subcategories = [...new Set(DATA.gastos.map((item) => item.subcategoria).filter(Boolean))].sort();
    const cards = [...new Set(DATA.gastos.map((item) => item.tarjeta_id).filter(Boolean))].sort();
    return `${formField('monto', 'Monto total (ARS)', '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
      ${formField('fecha', 'Fecha', todayLocalISO(), 'date', 'required')}
      ${formField('categoria', 'Categoría', '', 'text', 'required list="expense-categories"')}
      <datalist id="expense-categories">${categories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
      ${formField('subcategoria', 'Subcategoría', '', 'text', 'list="expense-subcategories"')}
      <datalist id="expense-subcategories">${subcategories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
      ${formField('descripcion_original', 'Descripción', '')}
      ${formSelect('medio_pago', 'Medio de pago', ['Efectivo', 'Transferencia', 'Débito', 'Crédito'], 'Efectivo')}
      ${formField('tarjeta_id', 'ID de tarjeta (opcional; ingresalo si corresponde)', '', 'text', 'list="expense-cards"')}
      <datalist id="expense-cards">${cards.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
      <p class="form-help">${cards.length ? 'Sugerencias tomadas de los gastos cargados. También podés ingresar un ID explícito.' : 'No hay un catálogo de tarjetas disponible. Ingresá el ID explícito si corresponde.'}</p>
      ${formSelect('pagado_por', 'Pagó', ['Común', 'JD', 'Pinki'], 'Común')}
      ${formSelect('tipo_proporcion', 'Reparto', [
        { value: 'dinamico', label: 'Dinámico según salarios del mes' },
        { value: '50/50', label: 'Mitad y mitad' },
        { value: 'custom', label: 'Manual por porcentajes' },
      ], 'dinamico')}
      <div id="custom-proportion" hidden>${formField('proporcion_jd', 'JD (%)', '50', 'number', 'min="0" max="100" step="0.01"')}
      ${formField('proporcion_pinki', 'Pinki (%)', '50', 'number', 'min="0" max="100" step="0.01"')}</div>
      ${formField('cuotas_total', 'Cantidad de cuotas', '1', 'number', 'required min="1" max="120" step="1"')}`;
  }
  if (kind === 'income' || kind === 'income-edit') return `
    ${formField('monto', 'Monto (ARS)', row?.monto ?? '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
    ${formField('fecha', 'Fecha', row?.fecha || todayLocalISO(), 'date', 'required')}
    ${formSelect('persona', 'Persona', ['JD', 'Pinki'], row?.persona || 'JD')}
    ${formSelect('categoria', 'Categoría', ['Salario', 'Extra', 'Freelance', 'Otro'], row?.categoria || 'Salario')}
    ${formField('descripcion_original', 'Descripción', row?.descripcion_original || '')}`;
  const fixedSplit = row?.responsable === 'Común' && row.tipo_proporcion === 'custom' ? 'custom' : 'dinamica';
  return `${formField('nombre', 'Descripción', row?.nombre || '', 'text', 'required')}
    ${formField('monto_estimado', 'Monto bruto (ARS)', row?.monto_estimado ?? '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
    ${formSelect('periodicidad', 'Periodicidad', ['mensual', 'bimestral'], row?.periodicidad || 'mensual')}
    ${formSelect('responsable', 'Responsable', ['Común', 'JD', 'Pinki'], row?.responsable || 'Común')}
    <div id="fixed-split-fields">
      ${formSelect('fixed_tipo_proporcion', 'Reparto del fijo común', [
        { value: 'dinamica', label: 'Dinámico según salarios del mes' },
        { value: 'custom', label: 'Personalizado' },
      ], fixedSplit)}
      <div id="fixed-custom-proportion" hidden>
        ${formField('proporcion_jd', 'JD (%)', fixedSplit === 'custom' ? row.proporcion_jd : '', 'number', 'min="0" max="100" step="any" inputmode="decimal"')}
        <p class="form-help">Pinki: <output id="fixed-pinki-percent" aria-live="polite">—</output></p>
      </div>
    </div>
    ${formField('vigente_desde', 'Vigente desde', todayLocalISO(), 'date', 'required')}`;
}

function openForm(kind, id = null) {
  if (!liveMode || writePending || reloadPending || reloadFailed) return;
  const source = kind.startsWith('expense') ? DATA.gastos : kind.startsWith('income') ? DATA.ingresos : DATA.fijos;
  const row = id === null ? null : source.find((item) => canonicalId(item.id) === canonicalId(id));
  if (id !== null && !row) return;
  activeForm = { kind, row, returnFocus: document.activeElement, confirmed: false, payload: null };
  const titles = { expense: 'Agregar gasto', 'expense-delete': 'Dar de baja una cuota', income: 'Agregar ingreso', 'income-edit': 'Editar ingreso', fixed: 'Agregar fijo', 'fixed-edit': 'Crear versión de fijo', 'fixed-delete': 'Dar de baja fijo' };
  document.getElementById('form-title').textContent = titles[kind];
  document.getElementById('form-intro').textContent = kind.includes('delete') ? 'Revisá qué cambio se aplicará.' : 'Completá los datos y revisá el resumen antes de guardar.';
  document.getElementById('form-fields').innerHTML = formMarkup(kind, row);
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-errors').textContent = '';
  document.getElementById('form-confirm').hidden = true;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-submit').disabled = false;
  document.getElementById('form-back').hidden = true;
  document.getElementById('form-back').disabled = false;
  document.getElementById('form-close').disabled = false;
  document.getElementById('form-modal').hidden = false;
  document.getElementById('form-modal').querySelector('input, select, button').focus();
  syncCustomProportion();
}

function closeForm() {
  if (writePending) return;
  document.getElementById('form-modal').hidden = true;
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-confirm').hidden = true;
  document.getElementById('form-back').hidden = true;
  document.getElementById('form-back').disabled = false;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-submit').disabled = false;
  document.getElementById('form-close').disabled = false;
  document.getElementById('form-errors').textContent = '';
  document.querySelectorAll('.field-error').forEach((el) => { el.textContent = ''; });
  const focus = activeForm?.returnFocus;
  activeForm = null;
  if (focus?.isConnected) focus.focus();
  else document.getElementById('tab-' + currentView)?.focus();
}

function syncCustomProportion() {
  const choice = document.getElementById('field-tipo_proporcion');
  const fields = document.getElementById('custom-proportion');
  if (choice && fields) {
    fields.hidden = choice.value !== 'custom';
    fields.querySelectorAll('input').forEach((input) => { input.disabled = fields.hidden; });
  }
  const responsable = document.getElementById('field-responsable');
  const fixedFields = document.getElementById('fixed-split-fields');
  const fixedChoice = document.getElementById('field-fixed_tipo_proporcion');
  const fixedCustom = document.getElementById('fixed-custom-proportion');
  if (!responsable || !fixedFields || !fixedChoice || !fixedCustom) return;
  fixedFields.hidden = responsable.value !== 'Común';
  fixedChoice.disabled = fixedFields.hidden;
  fixedCustom.hidden = fixedFields.hidden || fixedChoice.value !== 'custom';
  const jd = document.getElementById('field-proporcion_jd');
  jd.disabled = fixedCustom.hidden;
  const pinki = document.getElementById('fixed-pinki-percent');
  const raw = jd.value;
  const value = Number(raw);
  pinki.textContent = !fixedCustom.hidden && validFixedPercent(raw) ? `${100 - value}%` : '—';
}

function validFixedPercent(raw) {
  if (typeof raw !== 'string' || !/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(raw)) return false;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && value <= 100;
}

function validMoney(raw) {
  if (!/^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(String(raw))) return false;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 && value <= 1e12;
}

function validDate(raw) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return false;
  const date = new Date(`${raw}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === raw;
}

function collectForm(kind, row, values) {
  const errors = {};
  const dateKey = kind === 'fixed-delete' ? 'fecha_baja' : kind.startsWith('fixed') ? 'vigente_desde' : 'fecha';
  if (kind !== 'expense-delete' && !validDate(values[dateKey])) errors[dateKey] = 'Ingresá una fecha válida.';
  if (kind.endsWith('delete')) return { payload: kind === 'fixed-delete' ? { fecha_baja: values.fecha_baja } : null, errors };
  const moneyKey = kind.startsWith('fixed') ? 'monto_estimado' : 'monto';
  if (!validMoney(values[moneyKey])) errors[moneyKey] = 'Ingresá un monto positivo, finito, de hasta 2 decimales y máximo 1 billón.';
  if (kind === 'expense') {
    if (!values.categoria?.trim()) errors.categoria = 'Ingresá una categoría.';
    const cuotas = Number(values.cuotas_total);
    if (!/^\d+$/.test(values.cuotas_total) || !Number.isInteger(cuotas) || cuotas < 1 || cuotas > 120 ||
        Math.round(Number(values.monto) * 100) < cuotas) errors.cuotas_total = 'Entre 1 y 120 cuotas, con al menos un centavo por cuota.';
    const payload = { fecha: values.fecha, monto: Number(values.monto), categoria: values.categoria.trim(),
      subcategoria: values.subcategoria.trim(), descripcion_original: values.descripcion_original.trim(),
      medio_pago: values.medio_pago, pagado_por: values.pagado_por, tipo_proporcion: values.tipo_proporcion,
      cuotas_total: cuotas };
    if (values.tarjeta_id.trim()) payload.tarjeta_id = values.tarjeta_id.trim();
    if (values.tipo_proporcion === 'custom') {
      const jd = Number(values.proporcion_jd), pinki = Number(values.proporcion_pinki);
      if (!/^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(values.proporcion_jd) ||
          !/^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(values.proporcion_pinki) ||
          !Number.isFinite(jd) || !Number.isFinite(pinki) ||
          jd < 0 || pinki < 0 || jd > 100 || pinki > 100 || Math.abs(jd + pinki - 100) > .001) {
        errors.proporcion_jd = 'JD y Pinki deben sumar 100%, admitiendo 0%.';
      }
      payload.proporcion_jd = jd;
      payload.proporcion_pinki = pinki;
    }
    return { payload, errors };
  }
  if (kind.startsWith('income')) {
    if (!['JD', 'Pinki'].includes(values.persona)) errors.persona = 'Elegí JD o Pinki.';
    if (!values.categoria?.trim()) errors.categoria = 'Ingresá una categoría.';
    return { payload: { fecha: values.fecha, monto: Number(values.monto), persona: values.persona,
      categoria: values.categoria, descripcion_original: values.descripcion_original.trim() }, errors };
  }
  if (!values.nombre?.trim()) errors.nombre = 'Ingresá una descripción.';
  if (!['mensual', 'bimestral'].includes(values.periodicidad)) errors.periodicidad = 'Elegí una periodicidad válida.';
  if (!['Común', 'JD', 'Pinki'].includes(values.responsable)) errors.responsable = 'Elegí un responsable.';
  const payload = { nombre: values.nombre.trim(), monto_estimado: Number(values.monto_estimado),
    periodicidad: values.periodicidad, responsable: values.responsable, vigente_desde: values.vigente_desde };
  if (values.responsable === 'Común') {
    const split = values.fixed_tipo_proporcion;
    if (!['dinamica', 'custom'].includes(split)) errors.fixed_tipo_proporcion = 'Elegí un reparto válido.';
    if (split === 'custom') {
      if (!validFixedPercent(values.proporcion_jd)) errors.proporcion_jd = 'Ingresá un porcentaje de JD entre 0 y 100.';
      const jd = Number(values.proporcion_jd);
      if (kind === 'fixed' || row?.responsable !== 'Común' || row?.tipo_proporcion !== 'custom' ||
          Number(row.proporcion_jd) !== jd) {
        payload.tipo_proporcion = 'custom';
        if (!errors.proporcion_jd) payload.proporcion_jd = jd;
      }
    } else if (split === 'dinamica' && (kind === 'fixed' || row?.responsable !== 'Común' || row?.tipo_proporcion !== 'dinamica')) {
      payload.tipo_proporcion = 'dinamica';
      payload.proporcion_jd = null;
    }
  }
  return { payload, errors };
}

function describeForm(kind, row, payload) {
  if (kind === 'expense-delete') return `Baja solo de la cuota ${cuotaLabel(row)} del gasto #${row.id}, ${fmtARSExact(row.monto)}. Otras cuotas no se borran.`;
  if (kind === 'fixed-delete') return `Baja de ${row.nombre} desde ${payload.fecha_baja}. Se crea una versión inactiva; el historial permanece.`;
  if (kind === 'expense') return `Gasto ${payload.categoria}${payload.subcategoria ? ` / ${payload.subcategoria}` : ''}: ${fmtARSExact(payload.monto)}, ${payload.fecha}, ${payload.cuotas_total} cuota(s). ${payload.descripcion_original || 'Sin descripción'}. Medio: ${payload.medio_pago}${payload.tarjeta_id ? `, tarjeta ${payload.tarjeta_id}` : ''}. Pagó ${payload.pagado_por}; reparto ${payload.tipo_proporcion}${payload.tipo_proporcion === 'custom' ? ` (${payload.proporcion_jd}% JD / ${payload.proporcion_pinki}% Pinki)` : ''}.`;
  if (kind.startsWith('income')) return `${kind === 'income-edit' ? 'Editar' : 'Agregar'} ingreso ${payload.categoria} de ${payload.persona}: ${fmtARSExact(payload.monto)} el ${payload.fecha}. ${payload.descripcion_original || 'Sin descripción'}.${row?.categoria === 'Salario' || payload.categoria === 'Salario' ? ' Este cambio salarial puede modificar las proporciones de los meses afectados y sus deudas.' : ''}`;
  const fixedSplit = payload.responsable === 'Común'
    ? payload.tipo_proporcion === 'custom' ? `${payload.proporcion_jd}% JD / ${100 - payload.proporcion_jd}% Pinki`
      : payload.tipo_proporcion === 'dinamica' ? 'dinámico según salarios' : fijosRepartoLabel(row)
    : '100% personal';
  return `${kind === 'fixed-edit' ? 'Nueva versión de' : 'Nuevo fijo'} ${payload.nombre}: ${fmtARSExact(payload.monto_estimado)} ${payload.periodicidad}, responsable ${payload.responsable}, reparto ${fixedSplit}, desde ${payload.vigente_desde}. ${kind === 'fixed-edit' ? 'Se crea una nueva versión; la anterior queda en el historial.' : ''}`;
}

function routeForForm(kind, row) {
  if (kind === 'expense') return ['POST', '/api/expenses'];
  if (kind === 'expense-delete') return ['DELETE', `/api/expenses/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'income') return ['POST', '/api/income'];
  if (kind === 'income-edit') return ['PATCH', `/api/income/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'fixed') return ['POST', '/api/fixed'];
  return [kind === 'fixed-delete' ? 'DELETE' : 'PATCH', `/api/fixed/${encodeURIComponent(canonicalId(row.id))}`];
}

function verifiedWriteEnvelope(kind, row, result) {
  try {
    if (kind === 'expense-delete') return result?.deleted === true && canonicalId(result.id) === canonicalId(row.id);
    if (kind === 'expense') return Array.isArray(result?.expenses) && result.expenses.length > 0 &&
      result.expenses.every((expense) => !!canonicalId(expense?.id));
    if (kind.startsWith('income')) return !!canonicalId(result?.income?.id);
    canonicalId(result?.fixed?.id);
    if (result.fixed.fijo_grupo_id != null) canonicalId(result.fixed.fijo_grupo_id);
    return true;
  } catch {
    return false;
  }
}

async function writeForm(kind, row, payload) {
  const [method, path] = routeForForm(kind, row);
  const options = { method, credentials: 'same-origin' };
  if (payload !== null) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  let result;
  try { result = await response.json(); } catch {
    if (!response.ok) {
      const error = new Error(`Respuesta inválida (HTTP ${response.status}). No se confirmó la escritura.`);
      error.status = response.status;
      throw error;
    }
    result = null;
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}: ${result?.error || 'No se pudo guardar.'}`);
    error.status = response.status;
    throw error;
  }
  // Un 2xx confirma la escritura aunque el JSON haya perdido precisión de ID.
  // La identidad sólo se recupera con una lectura nueva y verificable.
  return { result, identityVerified: verifiedWriteEnvelope(kind, row, result) };
}

async function saveAndReload(kind, row, payload) {
  const writeResult = await writeForm(kind, row, payload);
  reloadPending = true;
  try {
    await loadLive();
    return { saved: true, reloaded: true, identityVerified: writeResult.identityVerified };
  } catch (error) {
    if (error.status === 401) { authState = 'unavailable'; liveMode = false; }
    reloadFailed = true;
    return { saved: true, reloaded: false, identityVerified: writeResult.identityVerified };
  } finally {
    reloadPending = false;
  }
}

function showWriteNotice(message, canRetry = false) {
  const notice = document.getElementById('write-notice');
  notice.textContent = message;
  if (canRetry) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Reintentar actualización del panel';
    button.addEventListener('click', handleRetryReload);
    notice.appendChild(button);
  }
  notice.hidden = false;
}

async function handleRetryReload() {
  if (reloadPending) return;
  reloadPending = true;
  updateAvailability();
  try {
    await loadLive();
    showWriteNotice('Panel actualizado con los datos en vivo.');
  } catch (error) {
    if (error.status === 401) { authState = 'unavailable'; liveMode = false; }
    reloadFailed = true;
    showWriteNotice('Guardado confirmado, pero no se pudo verificar la identidad en el panel. Revisá los datos; reintentá solo la lectura.', true);
  } finally {
    reloadPending = false;
    updateAvailability();
  }
}

async function handleFormSubmit(event) {
  event.preventDefault();
  if (!activeForm || !liveMode || writePending || reloadPending || reloadFailed) return;
  const { kind, row } = activeForm;
  const errorBox = document.getElementById('form-errors');
  errorBox.textContent = '';
  if (!activeForm.confirmed) {
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    const { payload, errors } = collectForm(kind, row, values);
    document.querySelectorAll('.field-error').forEach((el) => { el.textContent = ''; });
    for (const [key, message] of Object.entries(errors)) {
      const target = document.getElementById(`error-${key}`);
      if (target) target.textContent = message;
    }
    if (Object.keys(errors).length) {
      errorBox.textContent = 'Corregí los campos marcados.';
      document.getElementById(`field-${Object.keys(errors)[0]}`)?.focus();
      return;
    }
    activeForm.payload = payload;
    activeForm.confirmed = true;
    const confirm = document.getElementById('form-confirm');
    confirm.textContent = describeForm(kind, row, payload);
    confirm.hidden = false;
    document.getElementById('form-fields').hidden = true;
    document.getElementById('form-back').hidden = false;
    document.getElementById('form-submit').textContent = 'Confirmar y guardar';
    document.getElementById('form-submit').focus();
    return;
  }
  writePending = true;
  document.getElementById('form-submit').disabled = true;
  document.getElementById('form-close').disabled = true;
  document.getElementById('form-back').disabled = true;
  updateAvailability();
  try {
    const result = await saveAndReload(kind, row, activeForm.payload);
    writePending = false;
    closeForm();
    showWriteNotice(result.reloaded
      ? 'Guardado confirmado. Panel actualizado.'
      : 'Guardado confirmado, pero no se pudo verificar la identidad en el panel. Revisá los datos; reintentá solo la lectura.', !result.reloaded);
  } catch (error) {
    if (error.status === 401) { authState = 'unavailable'; liveMode = false; }
    errorBox.textContent = `No se confirmó el cambio. ${error.message}`;
  } finally {
    writePending = false;
    reloadPending = false;
    document.getElementById('form-submit').disabled = !liveMode || reloadFailed;
    document.getElementById('form-close').disabled = false;
    document.getElementById('form-back').disabled = false;
    updateAvailability();
  }
}

document.getElementById('life-form').addEventListener('submit', handleFormSubmit);
document.getElementById('form-close').addEventListener('click', closeForm);
document.getElementById('form-back').addEventListener('click', () => {
  if (!activeForm || writePending) return;
  activeForm.confirmed = false;
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-confirm').hidden = true;
  document.getElementById('form-back').hidden = true;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-fields').querySelector('input, select')?.focus();
});
document.getElementById('form-fields').addEventListener('change', syncCustomProportion);
document.getElementById('form-fields').addEventListener('input', syncCustomProportion);
document.getElementById('form-modal').addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !writePending) { event.preventDefault(); closeForm(); return; }
  if (event.key !== 'Tab') return;
  const focusable = [...event.currentTarget.querySelectorAll('input, select, button')]
    .filter((el) => !el.disabled && !el.closest('[hidden]'));
  if (!focusable.length) { event.preventDefault(); return; }
  const first = focusable[0], last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

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
  const { total, partial } = gastosTotalState(varTotal, fixTotal, cuotasTotal, !DATA.loadErrors.fijos);

  document.getElementById('g-total').textContent = total === null ? 'No disponible' : fmtARS(total);
  if (partial !== null) {
    const subEl = document.getElementById('g-total-sub');
    subEl.hidden = false;
    subEl.textContent = `Parcial sin fijos: ${fmtARS(partial)}`;
  } else renderTotalSub(varRows, fixTotal, cuotasRows);

  document.getElementById('g-fijos').textContent = DATA.loadErrors.fijos ? 'No disponible' : fmtARS(fixTotal);
  const fijosCount = activeFijos().length;
  document.getElementById('g-fijos-count').textContent = DATA.loadErrors.fijos
    ? 'No se pudo cargar el listado'
    : `${fijosCount} ítem${fijosCount !== 1 ? 's' : ''} · ver detalle`;

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
  if (personaFiltro !== 'comun' || (varRows.length === 0 && cuotasRows.length === 0 && fixTotal === 0)) {
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
  let unassigned = 0;
  fixedMonths().forEach((month) => {
    fijosVigentes(DATA.fijos, fixedMonthCutoff(month)).forEach((row) => {
      const amount = Number(row.monto_mensual || 0);
      const { pct1, pct2 } = fixedAllocation(row, month);
      sub1 += amount * pct1 / 100;
      sub2 += amount * pct2 / 100;
      if (pct1 + pct2 === 0) unassigned += amount;
    });
  });
  cuotasRows.forEach((r) => {
    const monto = parseFloat(r.monto) || 0;
    const { pct1, pct2 } = getRowPct(r);
    sub1 += monto * pct1 / 100;
    sub2 += monto * pct2 / 100;
  });
  subEl.hidden = false;
  subEl.textContent = `${P1}: ${fmtARS(sub1)} · ${P2}: ${fmtARS(sub2)}${unassigned ? ` · Sin asignar: ${fmtARS(unassigned)}` : ''}`;
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
  if (!d) {
    el.textContent = 'No disponible';
    el.classList.remove('danger');
    sub.textContent = 'No hay un saldo confirmado para mostrar';
    return;
  }
  if (!d.deudor) {
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
  if (DATA.loadErrors.fijos) {
    ['comp-seg-fijos', 'comp-seg-var', 'comp-seg-cuotas'].forEach((id) => { document.getElementById(id).style.width = '0%'; });
    document.getElementById('comp-labels-row').textContent = 'Composición no disponible: falta el archivo de fijos.';
    document.getElementById('comp-legend').textContent = '';
    return;
  }
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

function showChartError(key, canvas, message) {
  canvas.hidden = true;
  let error = canvas.parentElement.querySelector(`[data-chart-error="${key}"]`);
  if (!error) {
    error = document.createElement('p');
    error.className = 'chart-error';
    error.setAttribute('role', 'status');
    error.dataset.chartError = key;
    canvas.insertAdjacentElement('afterend', error);
  }
  error.textContent = message;
  error.hidden = false;
}

function renderChart(key, canvas, config) {
  if (typeof Chart === 'undefined') {
    showChartError(key, canvas, 'Gráfico no disponible: Chart.js no cargó. Totales y tablas siguen disponibles.');
    return;
  }
  try {
    charts[key] = new Chart(canvas, config);
    canvas.hidden = false;
    const error = canvas.parentElement.querySelector(`[data-chart-error="${key}"]`);
    if (error) error.hidden = true;
  } catch (error) {
    showChartError(key, canvas, 'No se pudo mostrar el gráfico. Totales y tablas siguen disponibles.');
  }
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
    if (typeof Chart === 'undefined') showChartError('gastos-pie', canvas, 'Gráfico no disponible: Chart.js no cargó. Totales y tablas siguen disponibles.');
    return;
  }

  const toggleBtn = document.getElementById('categ-pie-toggle');
  toggleBtn.textContent = categPieMode === 'doughnut' ? 'barras' : 'torta';

  if (categPieMode === 'bar') {
    const labels = keys.map((k, i) => `${k}  ${fmtARSCompact(data[i])}`);
    renderChart('gastos-pie', canvas, {
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
    renderChart('gastos-pie', canvas, {
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
  renderChart('gastos-bar', document.getElementById('chart-gastos-bar'), {
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
    renderChart('gastos-subcat', canvas, {
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
    renderChart('gastos-subcat', canvas, {
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
      <td data-label="Fecha" class="td-muted">${escapeHtml(g.fecha || '—')}</td>
      <td data-label="Categoría"><span class="pill">${iconFor(g.categoria)} ${escapeHtml(g.categoria)}</span></td>
      <td data-label="Monto" class="td-amount td-accent">${fmtARS(g.monto)}</td>
      <td data-label="Medio de pago" class="td-muted">${escapeHtml(g.medio_pago)}</td>
      <td data-label="Pagó"><span class="pill ${pillClassFor(g.pagado_por)}">${escapeHtml(g.pagado_por)}</span></td>
      <td data-label="Cuota" class="td-muted">${cuotaLabel(g)}</td>
      <td data-label="Acción"><button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(g.id))}" onclick="openForm('expense-delete', this.dataset.id)" aria-label="Dar de baja solo la cuota ${escapeHtml(cuotaLabel(g))} del gasto ${escapeHtml(canonicalId(g.id))}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Dar de baja</button></td>
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
  if (DATA.loadErrors.fijos) {
    inner.innerHTML = '<div class="section-error" role="alert">No se pudo cargar data/gastos_fijos.json — no se puede confirmar el listado de fijos.</div>';
    return;
  }
  const items = activeFijos();
  if (!items.length) {
    inner.innerHTML = '<div class="empty-state">Sin gastos fijos activos.</div>';
    return;
  }
  const sorted = [...items].sort((a, b) => Number(b.monto_mensual) - Number(a.monto_mensual));
  const total = fixedMonths().reduce((amount, month) => amount + fijosTotalMes(DATA.fijos, month), 0);
  inner.innerHTML = `
    <table>
      <thead><tr><th>Nombre</th><th>Categoría</th><th>Periodicidad</th><th style="text-align:right">Mensual</th></tr></thead>
      <tbody>
        ${sorted.map((f) => `<tr>
          <td>${escapeHtml(f.nombre)}</td>
          <td class="td-muted">${escapeHtml(f.categoria)}${f.subcategoria ? ' / ' + escapeHtml(f.subcategoria) : ''}</td>
          <td class="td-muted">${capitalize(escapeHtml(f.periodicidad))}</td>
          <td class="td-amount td-accent">${fmtARS(f.monto_mensual)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="3" class="td-muted">Total del período (${fixedMonths().length} mes${fixedMonths().length === 1 ? '' : 'es'})</td>
        <td class="td-amount td-accent">${fmtARS(total)}</td>
      </tr></tfoot>
    </table>
    <p class="td-muted" style="font-size:11px;margin-top:8px">La tabla muestra el corte del ${fijosDateLabel(fixedCutoffDate())}; el total suma cada mes con su versión vigente.</p>`;
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
  if (!d) {
    inner.textContent = 'No hay un saldo confirmado para mostrar.';
    return;
  }
  if (!d.deudor) {
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
  if (entry && Number.isFinite(entry.proporcion_jd) && Number.isFinite(entry.proporcion_pinki)) {
    document.getElementById('inc-proporcion').textContent =
      `${P1} ${entry.proporcion_jd.toFixed(0)}% · ${P2} ${entry.proporcion_pinki.toFixed(0)}%`;
    document.getElementById('inc-proporcion-source').textContent = mesLabel(entry.mes);
  } else {
    document.getElementById('inc-proporcion').textContent = 'No disponible';
    document.getElementById('inc-proporcion-source').textContent = 'La API no informó porcentajes verificables.';
  }

  renderIncomeLines();

  const sorted = [...rows].sort((a, b) => (b.fecha || '').localeCompare(a.fecha || ''));
  document.getElementById('tabla-ingresos-body').innerHTML = sorted.length ? sorted.map((r) => `
    <tr>
      <td data-label="Fecha" class="td-muted">${escapeHtml(r.fecha || '—')}</td>
      <td data-label="Categoría"><span class="pill">${escapeHtml(r.categoria)}</span></td>
      <td data-label="Descripción">${escapeHtml(r.descripcion_original)}</td>
      <td data-label="Persona"><span class="pill ${pillClassFor(r.persona)}">${escapeHtml(r.persona)}</span></td>
      <td data-label="Monto" class="td-amount td-accent">${fmtARS(r.monto)}</td>
      <td data-label="Acción"><button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(r.id))}" onclick="openForm('income-edit', this.dataset.id)" aria-label="Editar ingreso ${escapeHtml(canonicalId(r.id))} de ${escapeHtml(r.persona)}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Editar</button></td>
    </tr>`).join('') : '';
}

function renderIncomeLines() {
  destroyChart('inc-lines');
  const sorted = [...DATA.resumen].sort((a, b) => a.mes.localeCompare(b.mes));
  const real = sorted.filter((r) => r.total_ingresos > 0);
  const months = (real.length ? real : sorted).slice(-6).map((r) => r.mes);
  const dataP1 = months.map((m) => sum(DATA.ingresos.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P1), 'monto'));
  const dataP2 = months.map((m) => sum(DATA.ingresos.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P2), 'monto'));

  renderChart('inc-lines', document.getElementById('chart-inc-lines'), {
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

// ── VISTA SUPERMERCADO ───────────────────────────────────────────────────

async function ensureComprasLoaded() {
  if (comprasLoaded) { renderSupermercadoList(); return; }
  comprasLoaded = true;
  document.getElementById('supermercado-content').textContent = 'Cargando…';
  try {
    DATA.compras = await fetchJSON('data/compras.json');
    DATA.comprasError = null;
  } catch (err) {
    DATA.compras = [];
    DATA.comprasError = err.message;
    console.error('No se pudo cargar data/compras.json', err);
  }
  renderSupermercadoList();
}

function renderSupermercadoList() {
  const content = document.getElementById('supermercado-content');
  if (!content) return;
  if (DATA.comprasError) {
    content.innerHTML = `<div class="empty-state">No se pudo cargar la lista del súper (${escapeHtml(DATA.comprasError)}). Verificá que exista <code>data/compras.json</code>.</div>`;
    return;
  }
  if (DATA.compras === null) return; // todavía cargando

  const query = (document.getElementById('supermercado-search')?.value || '').trim().toLowerCase();
  const items = DATA.compras.filter((it) => !query || String(it.item_nombre || '').toLowerCase().includes(query));

  if (!DATA.compras.length) {
    content.innerHTML = '<div class="empty-state">La lista del súper está vacía.</div>';
    return;
  }
  if (!items.length) {
    content.innerHTML = '<div class="empty-state">Sin ítems que coincidan con la búsqueda.</div>';
    return;
  }

  const pendientes = items.filter((it) => !it.comprado);
  const comprados = items.filter((it) => it.comprado);
  const renderItem = (it) => {
    const prioridad = (it.prioridad || '').toLowerCase();
    return `
    <div class="super-item${it.comprado ? ' done' : ''}">
      <div class="super-item-main">
        <span>${escapeHtml(it.item_nombre)}</span>
        <span class="super-item-meta">
          ${escapeHtml(it.cantidad_deseada)} ${escapeHtml(it.unidad)}${it.agregado_por ? ' · agregado por ' + escapeHtml(it.agregado_por) : ''}${it.fecha_agregado ? ' · ' + escapeHtml(it.fecha_agregado) : ''}
        </span>
      </div>
      ${it.prioridad ? `<span class="${prioridad === 'alta' ? 'prioridad-alta' : ''}">${escapeHtml(it.prioridad)}</span>` : ''}
    </div>`;
  };

  content.innerHTML = `
    <div class="super-section-title">Pendientes (${pendientes.length})</div>
    <div class="super-list">${pendientes.length ? pendientes.map(renderItem).join('') : '<div class="empty-state">Nada pendiente.</div>'}</div>
    <div class="super-section-title">Comprados (${comprados.length})</div>
    <div class="super-list">${comprados.length ? comprados.map(renderItem).join('') : '<div class="empty-state">Nada marcado como comprado.</div>'}</div>`;
}

// ── VISTA RECETAS ────────────────────────────────────────────────────────

async function ensureRecetasLoaded() {
  if (recetasLoaded) { renderRecetasList(); return; }
  recetasLoaded = true;
  document.getElementById('recetas-content').textContent = 'Cargando…';
  try {
    DATA.recetas = await fetchJSON('data/recetas.json');
    DATA.recetasError = null;
  } catch (err) {
    DATA.recetas = [];
    DATA.recetasError = err.message;
    console.error('No se pudo cargar data/recetas.json', err);
  }
  renderRecetasList();
}

function renderRecetasList() {
  const content = document.getElementById('recetas-content');
  if (!content) return;
  if (DATA.recetasError) {
    content.innerHTML = `<div class="empty-state">No se pudo cargar el recetario (${escapeHtml(DATA.recetasError)}). Verificá que exista <code>data/recetas.json</code>.</div>`;
    return;
  }
  if (DATA.recetas === null) return; // todavía cargando

  const query = (document.getElementById('recetas-search')?.value || '').trim().toLowerCase();
  const recetas = DATA.recetas.filter((r) => !query || String(r.nombre || '').toLowerCase().includes(query));

  if (!DATA.recetas.length) {
    content.innerHTML = '<div class="empty-state">Todavía no hay recetas cargadas.</div>';
    return;
  }
  if (!recetas.length) {
    content.innerHTML = '<div class="empty-state">Sin recetas que coincidan con la búsqueda.</div>';
    return;
  }

  content.innerHTML = `<div class="recetas-grid">${recetas.map((r) => `
    <article class="receta-card">
      <h3>${escapeHtml(r.nombre)}</h3>
      <div class="receta-meta">${r.porciones ? escapeHtml(r.porciones) + ' porciones' : ''}${r.tiempo_preparacion_min ? ' · ' + escapeHtml(r.tiempo_preparacion_min) + ' min' : ''}</div>
      <ul class="receta-ingredientes">
        ${(r.ingredientes || []).map((ing) => `<li>${escapeHtml(ing.cantidad)} ${escapeHtml(ing.unidad)} ${escapeHtml(ing.ingrediente_nombre)}</li>`).join('') || '<li class="td-muted">Sin ingredientes cargados.</li>'}
      </ul>
      ${r.notas ? `<div class="receta-notas">${escapeHtml(r.notas)}</div>` : ''}
    </article>`).join('')}</div>`;
}

// ── IMPRIMIR / PDF (GASTOS) ──────────────────────────────────────────────

// Arma un resumen imprimible aparte del dashboard (ver .print-summary en
// style.css + @media print): reutiliza exactamente los mismos filtros y
// helpers que renderGastosView para no introducir una segunda fuente de
// verdad contable. Donde falta una fuente de datos, se deja constancia en
// vez de mostrar $0 (que se leería como "no hay gasto/deuda").
function printGastosResumen() {
  renderPrintSummary();
  window.print();
}

function renderPrintSummary() {
  const el = document.getElementById('print-summary');
  if (!el) return;

  const periodLabel = period.type === 'month'
    ? mesLabel(period.refMonth)
    : period.type === 'all' ? `Todo el historial disponible (${period.from} a ${period.to})`
      : (period.from && period.to) ? `${period.from} a ${period.to}` : 'Período sin fechas disponibles';
  const generatedAt = new Date().toLocaleString('es-AR');

  let html = `
    <h1>LIFE — Resumen de gastos</h1>
    <p>Período: <strong>${escapeHtml(periodLabel)}</strong> · generado el ${escapeHtml(generatedAt)}</p>`;

  if (DATA.loadErrors.gastos) {
    html += '<p class="print-missing">⚠ No se pudo cargar data/gastos.json: sin datos de gastos, cuotas ni desglose JD/Pinki para este resumen.</p>';
  } else {
    const rows = filterGastosPeriod(period.from, period.to);
    const varRows = rows.filter((r) => (parseInt(r.cuota_nro, 10) || 1) === 1);
    const varTotal = sum(varRows, 'monto');
    let sub1 = 0, sub2 = 0;
    varRows.forEach((r) => {
      const monto = parseFloat(r.monto) || 0;
      const { pct1, pct2 } = getRowPct(r);
      sub1 += monto * pct1 / 100;
      sub2 += monto * pct2 / 100;
    });
    const cuotasRows = filterCuotasComprometidas(period.from, period.to)
      .sort((a, b) => (a.fecha || '').localeCompare(b.fecha || ''));
    const cuotasTotal = sum(cuotasRows, 'monto');

    const months = fixedMonths().length;
    const fijos = DATA.loadErrors.fijos ? [] : activeFijos();
    const fijosTotal = DATA.loadErrors.fijos ? null : computeFixedForPersona('comun');
    const { total, partial } = gastosTotalState(varTotal, fijosTotal, cuotasTotal, fijosTotal !== null);

    html += `
      <h2>Total del período</h2>
      <table>
        <tr><th>Concepto</th><th>Monto</th></tr>
        <tr><td>Gastos variables</td><td>${fmtARS(varTotal)}</td></tr>
        <tr><td>Fijos${months > 1 ? ` (${months} meses, según vigencia)` : ''}</td><td>${DATA.loadErrors.fijos ? 'no disponible' : fmtARS(fijosTotal)}</td></tr>
        <tr><td>Cuotas comprometidas</td><td>${fmtARS(cuotasTotal)}</td></tr>
        <tr><td><strong>Total del período</strong></td><td><strong>${total === null ? 'no disponible' : fmtARS(total)}</strong></td></tr>
      </table>
      ${partial !== null ? `<p class="print-missing">⚠ Total parcial sin fijos: ${fmtARS(partial)}. Falta el archivo de fijos.</p>` : ''}
      ${DATA.loadErrors.resumen ? '<p class="print-missing">⚠ No se pudo cargar data/resumen_meses.json — las filas sin proporción explícita usan 50/50 por defecto, no la proporción real de ese mes.</p>' : ''}

      <h2>Desglose por persona (gastos variables)</h2>
      <table>
        <tr><th>Persona</th><th>Corresponde</th></tr>
        <tr><td>${escapeHtml(P1)}</td><td>${fmtARS(sub1)}</td></tr>
        <tr><td>${escapeHtml(P2)}</td><td>${fmtARS(sub2)}</td></tr>
      </table>
      <p class="print-note">Este desglose muestra gastos variables. Los fijos se informan arriba por separado.</p>

      <h2>Gastos fijos</h2>
      ${DATA.loadErrors.fijos
        ? '<p class="print-missing">⚠ No se pudo cargar data/gastos_fijos.json — sin listado de fijos para este resumen.</p>'
        : fijos.length
          ? `<table>
              <tr><th>Nombre</th><th>Responsable</th><th>Periodicidad</th><th>Mensual</th></tr>
              ${fijos.map((f) => `<tr>
                <td>${escapeHtml(f.nombre)}</td>
                <td>${f.responsable ? escapeHtml(f.responsable) : 'no especificado en los datos'}</td>
                <td>${escapeHtml(f.periodicidad)}${f.periodicidad === 'bimestral' ? ' (prorrateado ÷2, evita duplicar el bimestre)' : ''}</td>
                <td>${fmtARS(f.monto_mensual)}</td>
              </tr>`).join('')}
            </table>
            <p class="print-note">Listado al corte del ${fijosDateLabel(fixedCutoffDate())}. El total del período usa la versión vigente de cada mes.</p>`
          : '<p class="print-note">Sin fijos activos.</p>'}

      <h2>Cuotas comprometidas</h2>
      ${cuotasRows.length
        ? `<table>
            <tr><th>Fecha</th><th>Descripción</th><th>Cuota</th><th>Monto</th></tr>
            ${cuotasRows.map((r) => `<tr>
              <td>${r.fecha || '—'}</td>
              <td>${escapeHtml(r.descripcion_original)}</td>
              <td>${cuotaLabel(r)}</td>
              <td>${fmtARS(r.monto)}</td>
            </tr>`).join('')}
          </table>`
        : '<p class="print-note">Sin cuotas comprometidas en este período.</p>'}`;
  }

  html += '<h2>Deuda pendiente</h2>';
  if (DATA.loadErrors.deudaPendiente || !DATA.deudaPendiente) {
    html += '<p class="print-missing">⚠ No hay un saldo de deuda pendiente confirmado para este resumen.</p>';
  } else {
    const d = DATA.deudaPendiente;
    if (d && d.deudor) {
      html += `
        <p class="print-missing">⚠ Deuda ACTUAL, todavía NO saldada al momento de generar este resumen (no varía según el período elegido arriba).</p>
        <table>
          <tr><th>Deudor</th><th>Acreedor</th><th>Monto</th></tr>
          <tr><td>${escapeHtml(d.deudor)}</td><td>${escapeHtml(d.acreedor)}</td><td>${fmtARS(d.monto)}</td></tr>
        </table>`;
    } else {
      html += '<p class="print-note">Sin deuda pendiente registrada — todo saldado.</p>';
    }
  }

  el.innerHTML = html;
}

document.querySelector('.view-tabs').addEventListener('keydown', (event) => {
  const tab = event.target.closest('[role="tab"]');
  if (!tab || !event.currentTarget.contains(tab)) return;
  const index = VISIBLE_VIEWS.indexOf(tab.id.slice(4));
  if (index < 0) return;
  let next = index;
  if (event.key === 'ArrowRight') next = (index + 1) % VISIBLE_VIEWS.length;
  else if (event.key === 'ArrowLeft') next = (index - 1 + VISIBLE_VIEWS.length) % VISIBLE_VIEWS.length;
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = VISIBLE_VIEWS.length - 1;
  else return;
  event.preventDefault();
  switchView(VISIBLE_VIEWS[next]);
  document.getElementById('tab-' + VISIBLE_VIEWS[next]).focus();
});

loadAll();
