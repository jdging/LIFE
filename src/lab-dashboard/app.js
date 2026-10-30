'use strict';

// Nombres de persona: no existe data/config.json en este snapshot, así que se
// hardcodean según docs/CONTEXTO.md (Config: persona1=JD, persona2=Pinki).
const P1 = 'JD';
const P2 = 'Pinki';
const PERSONA_FILTRO_LABELS = {
  comun: 'Comunes', jd_comun: `${P1}+Común`, jd: P1, pinki_comun: `${P2}+Común`, pinki: P2,
};

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
const INVENTARIO_ESTADOS = ['Activo', 'Vendido', 'Donado', 'Desechado'];
const INVENTARIO_COTIZACION_STORAGE_KEY = 'life_inventario_cotizacion_usd_ars';
const INVENTARIO_COTIZACION_DEFAULT = 1200;

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
const fmtUSD = (n) =>
  'U$D ' + new Intl.NumberFormat('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(parseFloat(n) || 0);
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
// Sugerencias del selector de mes: incluye meses futuros con datos (cuotas
// pendientes, ingresos o fijos con vigente_desde futuro) para que el usuario
// sepa que puede navegarlos, sin restringir el input a esa lista.
function monthsWithData() {
  const months = new Set([
    ...DATA.gastos.map((row) => (row.fecha || '').slice(0, 7)),
    ...DATA.ingresos.map((row) => (row.fecha || '').slice(0, 7)),
    ...DATA.fijos.map((row) => (row.vigente_desde || '').slice(0, 7)),
  ].filter((m) => /^\d{4}-\d{2}$/.test(m)));
  return [...months].sort();
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
// Resuelve el resumen mensual a usar para un mes dado: el propio mes si existe
// en DATA.resumen, o si no, el último mes anterior (o igual) con ingresos reales.
// Nunca devuelve un mes posterior al consultado. Si no hay ninguno anterior con
// datos, devuelve undefined — cada consumidor define su propio fallback de "sin datos".
function getMonthProportion(month) {
  const sorted = [...DATA.resumen].sort((a, b) => a.mes.localeCompare(b.mes));
  const exact = sorted.find((r) => r.mes === month);
  if (exact && Number(exact.total_ingresos) > 0) return exact;
  const previous = sorted.filter((r) => r.mes <= month && Number(r.total_ingresos) > 0);
  return previous.length ? previous[previous.length - 1] : undefined;
}

// Gastos que generan deuda ENTRE JD y Pinki y todavía no fueron saldados:
// pagados por una sola persona (nunca 'Común') y sin `saldado`. Atemporal
// — no respeta el período activo, igual que el saldo que muestra la card
// (DATA.deudaPendiente): una deuda de un mes anterior sigue vigente hasta
// que se salda explícitamente.
function getDebtRows() {
  return DATA.gastos.filter((r) => {
    if (r.saldado) return false;
    if (r.pagado_por !== P1 && r.pagado_por !== P2) return false;
    const { pct1, pct2 } = getRowPct(r);
    if (r.pagado_por === P1 && pct2 === 0) return false;
    if (r.pagado_por === P2 && pct1 === 0) return false;
    return true;
  });
}

// ── ESTADO ────────────────────────────────────────────────────────────────

const DATA = {
  gastos: [], ingresos: [], fijos: [], resumen: [], deudaPendiente: null,
  loadErrors: {}, compras: null, comprasError: null, recetas: null, recetasError: null,
  inventario: [],
};
const charts = {};
let period = null;
let gastosBarMonths = 6;
function gastosBarMonthsLabel() {
  return `${gastosBarMonths} ${gastosBarMonths === 1 ? 'mes' : 'meses'}`;
}
let currentView = 'gastos';
// Destinos con pestaña visible en nav.view-tabs. 'inversiones' y 'presupuesto'
// siguen en el DOM (código/panel conservado) pero switchView los ignora: no
// tienen botón de tab y no deben quedar accesibles desde la navegación.
const VISIBLE_VIEWS = ['gastos', 'ingresos', 'fijos', 'supermercado', 'recetas', 'inventario'];
const ALL_VIEWS = [...VISIBLE_VIEWS, 'inversiones', 'presupuesto'];
let comprasLoaded = false;
let recetasLoaded = false;
let personaFiltro = 'comun';
let fijosPersonaFiltro = 'comun';
let incomePersonaFiltro = 'all';
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
// Independiente de liveMode: 'inventory' puede faltar en /api/health.capabilities
// (API más vieja o versión parcialmente desplegada) sin que el resto del dashboard
// deje de estar en vivo — ver loadAll/updateAvailability.
let inventoryAvailable = false;
let authState = 'unknown';
let writePending = false;
let reloadPending = false;
let reloadFailed = false;
let activeForm = null;
let categoriesGastoCache = null;
let activeExpenseCatalog = null;
let inventarioFiltroEstado = 'Activo';
// Filas de la tabla de inventario actualmente en el DOM: {id, usd, pctJD}.
// setInventarioCotizacion() la recorre para recalcular Reventa/Venta JD/Pinki
// por id (document.getElementById) en vez de reconstruir la tabla — así un
// cambio de cotización (global o en cualquier fila) no le hace perder el foco
// al input que el usuario está tipeando (brief t_0e38e74e v2, punto 1).
let inventarioRowsRendered = [];
// True si el usuario tipeó directamente en el campo USD de compra del
// formulario de inventario abierto: mientras esté en true, la sugerencia
// automática (onInventoryUsdSugerido) no pisa lo que escribió (t_0e38e74e,
// hallazgo 4 del revisor 46d4f3d5). Se resetea en cada apertura del form.
let inventoryUsdEditedManually = false;
const TABLE_KEY_MAP = { monto_total: 'monto_propio', pago: 'pagado_por' };

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

function adaptLiveInventario(row) {
  const id = canonicalId(row?.id);
  if (typeof row?.nombre !== 'string' || !row.nombre.trim()) throw new Error('Bien de inventario sin nombre.');
  if (typeof row?.valor_estimado !== 'number' || !Number.isFinite(row.valor_estimado) || row.valor_estimado <= 0) {
    throw new Error('Bien de inventario con valor estimado inválido.');
  }
  return { ...row, id };
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
  // Las rutas sin `month` devuelven todos los movimientos; `fixed/versions`
  // conserva la vigencia histórica y `summary` los porcentajes mensuales.
  // La serie de 1–24 meses se calcula localmente con estas respuestas completas:
  // consultar sólo el mes del período global ocultaría los meses anteriores.
  const [expenses, income, inventory, versions, summary, currentSummary] = await Promise.all([
    fetchJSON('/api/expenses'), fetchJSON('/api/income'),
    inventoryAvailable ? fetchJSON('/api/inventory') : Promise.resolve(null),
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
    // Si la API no declaró la capability 'inventory', la pestaña queda vacía
    // y en solo lectura/aviso (ver renderInventarioView) sin afectar liveMode.
    inventario: inventoryAvailable ? requireList(inventory, 'inventory').map(adaptLiveInventario) : [],
    fijos: requireList(versions, 'versions').map(adaptLiveFixed),
    resumen: months,
  };
  Object.assign(DATA, next, { loadErrors: {}, deudaPendiente: current.debt_pending_through_month });
  liveMode = true;
  authState = 'authenticated';
  reloadFailed = false;
  updateAvailability();
  renderMonthOptions();
  if (period) renderView(currentView);
}

async function loadSnapshot() {
  // El modo snapshot sólo tiene historia si están presentes los JSON completos
  // de `data/`. En este candidato no vienen incluidos: un fetch fallido marca
  // loadErrors y la serie informa falta de datos, en vez de mostrar ceros falsos.
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
  // Sin equivalente de snapshot para inventario (tabla nueva, sin archivo
  // data/inventario.json): esta pestaña queda vacía y de solo lectura hasta
  // que vuelva la conexión autenticada (ver renderInventarioView).
  DATA.inventario = [];
  DATA.loadErrors = {
    gastos: g.status === 'rejected',
    ingresos: i.status === 'rejected',
    fijos: f.status === 'rejected',
    resumen: r.status === 'rejected',
    deudaPendiente: d.status === 'rejected',
  };
  updateAvailability();
  renderMonthOptions();
  if (period) renderView(currentView);
}

// Caché en memoria durante la sesión: una vez resuelto el catálogo con éxito,
// no se vuelve a pedir aunque se abra el formulario de gasto varias veces.
async function loadCategoriasGasto() {
  if (categoriesGastoCache) return categoriesGastoCache;
  const data = await fetchJSON('/api/categories?tipo=Gasto');
  const list = requireList(data, 'categories');
  if (!list.length) throw new Error('Catálogo de categorías de gasto vacío.');
  if (!list.every((item) => item && typeof item === 'object' && !Array.isArray(item) &&
      typeof item.categoria === 'string' && item.categoria.trim() &&
      Array.isArray(item.subcategorias) &&
      item.subcategorias.every((name) => typeof name === 'string' && name.trim()))) {
    throw new Error('Catálogo de categorías de gasto inválido.');
  }
  categoriesGastoCache = list.map((item) => ({
    categoria: item.categoria.trim(),
    subcategorias: item.subcategorias.map((name) => name.trim()),
  }));
  return categoriesGastoCache;
}

async function loadAll() {
  authState = 'unavailable';
  liveMode = false;
  inventoryAvailable = false;
  updateAvailability();
  try {
    const health = await fetchJSON('/api/health');
    // 'inventory' queda afuera de este chequeo a propósito: el modo live del
    // resto del dashboard no puede depender de una capability que es propia
    // de una sola pestaña (ver inventoryAvailable, más abajo).
    if (health?.ok !== true || health.mode !== 'live' ||
        !Array.isArray(health.capabilities) ||
        !['expenses', 'income', 'fixed'].every((cap) => health.capabilities.includes(cap))) {
      throw new Error('API no disponible para formularios');
    }
    inventoryAvailable = health.capabilities.includes('inventory');
    authState = 'authenticated';
    await loadLive();
  } catch (error) {
    if (error.status === 401) authState = 'unavailable';
    liveMode = false;
    inventoryAvailable = false;
    reloadFailed = false;
    await loadSnapshot();
  }

  period = computePeriod('month', { month: thisMonth() });
  document.getElementById('month-picker').value = period.refMonth;
  switchView('gastos');
}

function renderMonthOptions() {
  const list = document.getElementById('month-options');
  if (!list) return;
  list.innerHTML = monthsWithData().map((m) => `<option value="${m}">${escapeHtml(mesLabel(m))}</option>`).join('');
}

function updateAvailability() {
  const status = document.getElementById('api-status');
  status.textContent = liveMode
    ? (reloadFailed
      ? 'Finanzas y otros módulos · conexión autenticada; guardado confirmado, pero el panel no pudo actualizarse. Nuevas escrituras pausadas hasta reintentar la lectura. Supermercado informa su propio estado.'
      : (writePending || reloadPending)
        ? 'Finanzas y otros módulos · conexión autenticada; procesando el cambio y actualizando el panel. Supermercado informa su propio estado.'
        : 'Finanzas y otros módulos · conexión autenticada; datos en vivo. Escrituras disponibles. Supermercado informa su propio estado.')
    : (authState === 'authenticated'
      ? 'Finanzas y otros módulos · los datos live no se pudieron verificar. Snapshot de solo lectura; no se pueden guardar cambios en esas vistas. Supermercado informa su propio estado.'
      : 'Finanzas y otros módulos · modo snapshot de solo lectura. Su conexión autenticada no está disponible; no se pueden guardar cambios en esas vistas. Supermercado informa su propio estado.');
  status.classList.toggle('status-live', liveMode);
  document.querySelectorAll('[data-write-action]').forEach((button) => {
    // Los botones marcados data-requires="inventory" (alta/edición/baja de
    // bienes) se deshabilitan también si falta esa capability puntual, sin
    // afectar al resto de los botones de escritura (ver inventoryAvailable).
    const needsInventory = button.dataset.requires === 'inventory';
    button.disabled = !liveMode || (needsInventory && !inventoryAvailable)
      || writePending || reloadPending || reloadFailed;
  });
  const invNotice = document.getElementById('inventario-notice');
  if (invNotice) {
    invNotice.hidden = !liveMode || inventoryAvailable;
    invNotice.textContent = 'La API no informó la capability "inventory": esta pestaña queda en solo lectura hasta que esté disponible. El resto del dashboard sigue en vivo.';
  }
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
  else if (v === 'supermercado') ensureComprasLoaded(true);
  else if (v === 'recetas') ensureRecetasLoaded();
  else if (v === 'inventario') renderInventarioView();
  // Inversiones y Presupuesto se quedan en el estado vacío ya maquetado en index.html.
}

// ── PERÍODO ──────────────────────────────────────────────────────────────

// 'month' y 'range' pueden ser futuros (cuotas y fijos vigentes de un mes que
// todavía no llegó); el resto de los períodos agregados ('quarter', 'semester',
// 'year', 'all') siguen recortados a hoy para no inflar totales con gasto futuro.
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
  let from, to, refMonth, capToToday = true;
  switch (type) {
    case 'month': {
      const m = opts.month || today;
      from = m + '-01'; to = fijosLastDay(m); refMonth = m; capToToday = false; break;
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
      from = opts.from || firstAvailableDate(); to = opts.to || todayDate;
      refMonth = to.substring(0, 7); capToToday = false; break;
    default:
      from = null; to = null; refMonth = today;
  }
  if (capToToday && to && to > todayDate) to = todayDate;
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
  const entry = mes ? getMonthProportion(mes) : null;
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

function allocationAmount(amount, pct1, pct2, filtro) {
  if (filtro === 'comun') return pct1 > 0 && pct2 > 0 ? amount : null;
  if (filtro === 'jd') return pct1 === 100 ? amount : null;
  if (filtro === 'pinki') return pct2 === 100 ? amount : null;
  if (filtro === 'jd_comun') return pct1 > 0 ? amount * pct1 / 100 : null;
  if (filtro === 'pinki_comun') return pct2 > 0 ? amount * pct2 / 100 : null;
  return null;
}

function expenseAmount(row, filtro = personaFiltro) {
  const { pct1, pct2 } = getRowPct(row);
  return allocationAmount(Number(row.monto) || 0, pct1, pct2, filtro);
}

function amountWithReference(amount, reference) {
  return `${fmtARS(amount)} de ${fmtARS(reference)}`;
}

function expenseAmountLabel(row, filtro = personaFiltro) {
  return amountWithReference(expenseAmount(row, filtro), Number(row.monto) || 0);
}

function fixedAmount(row, month, filtro = fijosPersonaFiltro) {
  const { pct1, pct2 } = fixedAllocation(row, month);
  return allocationAmount(Number(row.monto_mensual) || 0, pct1, pct2, filtro);
}

function fixedAmountLabel(row, month, filtro = fijosPersonaFiltro) {
  return amountWithReference(fixedAmount(row, month, filtro), Number(row.monto_mensual) || 0);
}

function setPersonaFiltro(filtro) {
  if (!Object.hasOwn(PERSONA_FILTRO_LABELS, filtro)) return;
  personaFiltro = filtro;
  document.querySelectorAll('.gastos-persona-filter .persona-btn').forEach((b) => {
    const active = b.dataset.filter === filtro;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('.gastos-persona-select').forEach((select) => { select.value = filtro; });
  if (currentView === 'gastos') renderGastosView();
}

function setFijosPersonaFiltro(filtro) {
  if (!Object.hasOwn(PERSONA_FILTRO_LABELS, filtro)) return;
  fijosPersonaFiltro = filtro;
  if (fijosSelectedGroup !== null) closeFijosDetail();
  document.querySelectorAll('#fijos-persona-filter .persona-btn').forEach((button) => {
    const active = button.dataset.filter === filtro;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  renderFijosView();
}

function setIncomePersonaFiltro(filtro) {
  if (!['all', 'jd', 'pinki'].includes(filtro)) return;
  incomePersonaFiltro = filtro;
  document.querySelectorAll('.income-persona-select').forEach((select) => { select.value = filtro; });
  if (currentView === 'ingresos') renderIngresosView();
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

function creditFixedItems() {
  if (DATA.loadErrors.fijos) return [];
  return fixedMonths().flatMap((month) => fijosVigentes(DATA.fijos, fixedMonthCutoff(month))
    .filter((row) => row.medio_pago === 'Crédito' && fixedAmount(row, month, personaFiltro) !== null)
    .map((row) => ({ row, month })));
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
  const entry = getMonthProportion(month);
  const pct1 = Number(entry?.proporcion_jd);
  const pct2 = Number(entry?.proporcion_pinki);
  return Number.isFinite(pct1) && Number.isFinite(pct2) && pct1 + pct2 === 100
    ? { pct1, pct2 } : { pct1: 50, pct2: 50 };
}

function computeFixedForPersona(filtro) {
  return fixedMonths().reduce((total, month) => {
    const monthRows = fijosVigentes(DATA.fijos, fixedMonthCutoff(month));
    return total + monthRows.reduce((subtotal, row) => {
      return subtotal + (fixedAmount(row, month, filtro) ?? 0);
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

// Solo invierte el orden de VISUALIZACIÓN (más nuevo primero). El cálculo de
// tramos (fijosTramos/fijosHistorial) sigue cronológico, como lo necesita el
// gráfico de evolución y el cómputo de vigente_hasta de cada tramo.
function renderFijosHistoryGroup(id, group, latest) {
  return `<article class="panel fijos-history-group">
    <div class="fijos-history-head"><h3>${escapeHtml(latest.nombre)}${Number(latest.activo) === 0 ? ' <span class="pill">Dado de baja</span>' : ''}</h3>
      <button type="button" class="fijos-secondary" data-id="${escapeHtml(id)}" onclick="openFijosDetail(this.dataset.id)">Ver detalle</button></div>
    <div class="fijos-tramos">${[...group].reverse().map((row) => `<div class="fijos-tramo">
      <strong>${fijosDateLabel(row.tramo_desde)} a ${fijosDateLabel(row.tramo_hasta)}</strong>
      <span>${escapeHtml(row.nombre)} · ${fmtARS(row.monto_mensual)}/mes${row.periodicidad === 'bimestral' ? ` · bruto ${fmtARS(row.monto_estimado)} bimestral` : ''}</span>
      <span class="pill ${pillClassFor(row.responsable)}">${escapeHtml(fijosResponsable(row))}</span>
      ${Number(row.activo) === 0 ? '<span class="pill">Baja</span>' : ''}
    </div>`).join('')}</div>
  </article>`;
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
  const currentRows = fijosVigentes(DATA.fijos, todayIso)
    .filter((row) => fixedAmount(row, todayIso.slice(0, 7)) !== null)
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  const split = { 'Común': 0, JD: 0, Pinki: 0, 'Sin asignar': 0 };
  currentRows.forEach((row) => { split[fijosResponsable(row)] += fixedAmount(row, todayIso.slice(0, 7)); });
  const total = Object.values(split).reduce((value, amount) => value + amount, 0);
  document.getElementById('fijos-totals').innerHTML = `
    <div class="fijos-total-main"><span>${escapeHtml(PERSONA_FILTRO_LABELS[fijosPersonaFiltro])} · ${fijosDateLabel(todayIso)}</span><strong>${fmtARS(total)}</strong></div>
    <div class="fijos-total-split">${Object.entries(split).map(([name, amount]) => `<span><span class="pill ${pillClassFor(name)}">${name}</span> ${fmtARS(amount)}</span>`).join('')}</div>`;
  current.innerHTML = currentRows.length ? currentRows.map((row) => `
    <article class="fijos-item">
      <div class="fijos-item-head"><h3>${escapeHtml(row.nombre)}</h3><strong>${fixedAmountLabel(row, todayIso.slice(0, 7))} <small>/ mes</small></strong></div>
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
    const months = getMonthsInPeriod(`${startInput.value}-01`, fijosLastDay(endInput.value));
    const monthly = months.flatMap((month) => fijosVigentes(DATA.fijos, fijosLastDay(month))
      .filter((row) => fixedAmount(row, month) !== null)
      .map((row) => ({ month, row })));
    history.innerHTML = monthly.length ? `<div class="panel table-scroll"><table><thead><tr><th>Mes</th><th>Fijo</th><th>Responsable</th><th>Importe filtrado de total</th><th>Historial</th></tr></thead><tbody>${monthly.map(({ month, row }) => `<tr>
      <td>${escapeHtml(month)}</td><td>${escapeHtml(row.nombre)}</td><td>${escapeHtml(fijosResponsable(row))}</td>
      <td class="td-amount">${fixedAmountLabel(row, month)}</td>
      <td><button type="button" class="fijos-secondary" data-id="${escapeHtml(fixedGroupId(row))}" onclick="openFijosDetail(this.dataset.id)">Ver versiones</button></td>
    </tr>`).join('')}</tbody></table></div>` : '<div class="empty-state-panel">No hay fijos para este filtro y período.</div>';
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
      <thead><tr><th>Desde</th><th>Hasta</th><th>Descripción</th><th>Categoría</th><th>Subcategoría</th><th>Monto mensual</th><th>Responsable</th><th>Reparto</th><th>Estado</th><th>Cambios</th></tr></thead>
      <tbody>${[...versions].reverse().map((row) => {
      const previous = versions[versions.findIndex((item) => canonicalId(item.id) === canonicalId(row.id)) - 1];
      const changes = previous ? [
        previous.nombre !== row.nombre ? 'Descripción' : null,
        (previous.categoria || '') !== (row.categoria || '') ? 'Categoría' : null,
        (previous.subcategoria || '') !== (row.subcategoria || '') ? 'Subcategoría' : null,
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
        <td data-label="Categoría">${escapeHtml(row.categoria || 'Sin categoría')}</td>
        <td data-label="Subcategoría">${escapeHtml(row.subcategoria || 'Sin subcategoría')}</td>
        <td data-label="Monto mensual">${fmtARS(row.monto_mensual)}${row.periodicidad === 'bimestral' ? `<small>bruto ${fmtARS(row.monto_estimado)}</small>` : ''}</td>
        <td data-label="Responsable"><span class="pill ${pillClassFor(row.responsable)}">${escapeHtml(fijosResponsable(row))}</span></td>
        <td data-label="Reparto">${escapeHtml(fijosRepartoLabel(row))}</td>
        <td data-label="Estado"><span class="pill">${status}</span></td>
        <td data-label="Cambios" class="fijos-changes">${changes.length ? changes.join(', ') : previous ? 'Sin cambio en los campos mostrados' : 'Alta inicial'}</td>
      </tr>`;
    }).join('')}</tbody></table></div>
    <div class="panel-title-row"><h3>Evolución del importe mensual filtrado</h3>
      <button type="button" class="btn-chart-toggle" id="fijos-evolution-show" aria-label="Mostrar gráfico de evolución de ${escapeHtml(latest.nombre)}" aria-expanded="false" aria-controls="fijos-evolution-body" onclick="toggleFijosEvolutionChart()">Mostrar gráfico</button></div>
    <div id="fijos-evolution-body" hidden><div class="fijos-chart-wrap"><canvas id="fijos-evolution-chart" aria-label="Evolución del importe mensual filtrado de ${escapeHtml(latest.nombre)}" aria-describedby="fijos-evolution-chart-data" role="img"></canvas></div>
      <details class="chart-data" id="fijos-evolution-chart-data"><summary>Ver datos mensuales de este fijo</summary></details></div>
    <p class="chart-error" id="fijos-chart-error" role="alert" hidden>No se pudo mostrar el gráfico. El historial sigue disponible arriba.</p>`;
}

function toggleFijosEvolutionChart() {
  const body = document.getElementById('fijos-evolution-body');
  const button = document.getElementById('fijos-evolution-show');
  if (!body || !button || fijosSelectedGroup === null) return;
  const opening = body.hidden;
  body.hidden = !opening;
  button.setAttribute('aria-expanded', String(opening));
  button.textContent = opening ? 'Ocultar gráfico' : 'Mostrar gráfico';
  button.setAttribute('aria-label', `${opening ? 'Ocultar' : 'Mostrar'} gráfico de evolución de ${fijosHistorial(DATA.fijos, fijosSelectedGroup).at(-1).nombre}`);
  if (!opening) {
    if (fijosChart) { fijosChart.destroy(); fijosChart = null; }
    return;
  }
  try {
    const versions = fijosHistorial(DATA.fijos, fijosSelectedGroup);
    const months = getMonthsInPeriod(versions[0].vigente_desde, todayLocalISO());
    const evolution = {
      dates: months.map((month) => month + '-01'),
      amounts: months.map((month) => {
        const row = fijosVersionVigente(versions, fijosSelectedGroup, fijosLastDay(month));
        return row && Number(row.activo) === 1 ? fixedAmount(row, month) ?? 0 : 0;
      }),
    };
    const fixedCanvas = document.getElementById('fijos-evolution-chart');
    renderChartData(fixedCanvas, `Evolución de ${versions.at(-1).nombre}`,
      `Filtro: ${PERSONA_FILTRO_LABELS[fijosPersonaFiltro]}. Desde ${versions[0].vigente_desde} hasta ${todayLocalISO()}.`,
      ['Mes', 'Importe mensual'], months.map((month, i) => [month, fmtARS(evolution.amounts[i])]));
    if (typeof Chart === 'undefined') {
      fixedCanvas.hidden = true;
      document.getElementById('fijos-chart-error').hidden = false;
      return;
    }
    fijosChart = new Chart(fixedCanvas, {
      type: 'line',
      data: { labels: evolution.dates.map(fijosDateLabel), datasets: [{
        label: `Importe ${PERSONA_FILTRO_LABELS[fijosPersonaFiltro]}`, data: evolution.amounts,
        // Cada punto inicia una versión: el monto previo llega hasta esa fecha.
        stepped: 'after', borderColor: '#5f7d52', backgroundColor: '#7c9a6b', tension: 0, pointRadius: 4,
      }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    fixedCanvas.hidden = false;
    document.getElementById('fijos-chart-error').hidden = true;
  } catch (error) {
    document.getElementById('fijos-evolution-chart').hidden = true;
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

// Catálogo vía <select> dependiente (GET /api/categories?tipo=Gasto, t_ce790609).
// Sin catálogo (fetch falló o vino vacío) se cae a los inputs de texto + datalist
// de siempre, para que el alta de gasto nunca quede bloqueada por ese endpoint.
function formExpenseCategorySelects(catalog, row = null) {
  // Sin `row` (alta), ningún `selected` aplica: mismo markup exacto que
  // antes de admitir precarga, sin el espacio extra que deja un atributo
  // condicional vacío (`" " + ''`) antes de cerrar la etiqueta.
  const options = catalog.map((c) => {
    const selected = c.categoria === row?.categoria ? ' selected' : '';
    return `<option value="${escapeHtml(c.categoria)}"${selected}>${escapeHtml(c.categoria)}</option>`;
  }).join('');
  // Precarga (expense-edit): las subcategorías se calculan acá para la
  // categoría ya elegida, en vez de delegar en onExpenseCategoriaChange()
  // (esa función reconstruye la lista PERO siempre resetea el valor a ''
  // -- correcto cuando el usuario cambia de categoría a mano, pero pisaría
  // la subcategoría precargada si se llamara también en el render inicial).
  const entry = row?.categoria ? catalog.find((c) => c.categoria === row.categoria) : null;
  const subOptions = (entry ? entry.subcategorias : []).map((s) => {
    const selected = s === row?.subcategoria ? ' selected' : '';
    return `<option value="${escapeHtml(s)}"${selected}>${escapeHtml(s)}</option>`;
  }).join('');
  const categoriaPlaceholderSelected = row?.categoria ? '' : ' selected';
  const subcategoriaPlaceholderSelected = row?.subcategoria ? '' : ' selected';
  return `<label class="form-field" for="field-categoria">Categoría
    <select id="field-categoria" name="categoria" required aria-describedby="error-categoria">
      <option value="" disabled${categoriaPlaceholderSelected}>Elegí una categoría</option>
      ${options}
    </select>
    <span class="field-error" id="error-categoria"></span></label>
    <label class="form-field" for="field-subcategoria">Subcategoría
    <select id="field-subcategoria" name="subcategoria" aria-describedby="error-subcategoria">
      <option value=""${subcategoriaPlaceholderSelected}>Sin subcategoría</option>
      ${subOptions}
    </select>
    <span class="field-error" id="error-subcategoria"></span></label>`;
}

function formExpenseCategoryText(row = null) {
  const categories = [...new Set(DATA.gastos.map((item) => item.categoria).filter(Boolean))].sort();
  const subcategories = [...new Set(DATA.gastos.map((item) => item.subcategoria).filter(Boolean))].sort();
  return `${formField('categoria', 'Categoría', row?.categoria || '', 'text', 'required list="expense-categories"')}
    <datalist id="expense-categories">${categories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
    ${formField('subcategoria', 'Subcategoría', row?.subcategoria || '', 'text', 'list="expense-subcategories"')}
    <datalist id="expense-subcategories">${subcategories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>`;
}

// Catálogo vía <select> dependiente para el formulario de FIJO (brief
// t_38a7253f hallazgo A): mismo catálogo de /api/categories?tipo=Gasto que
// el formulario de gasto, pero con dos diferencias a propósito:
//   - categoría/subcategoría quedan OPCIONALES (sin `required`), porque
//     `validar_gasto_fijo` las trata como opcionales -- un fijo legacy sin
//     categoría asignada sigue siendo válido.
//   - si el valor actual de la fila no está en el catálogo (fijo legacy con
//     una categoría libre, o el catálogo cambió desde que se guardó), se
//     agrega como opción extra seleccionada en vez de perderse en silencio.
function formFixedCategorySelects(catalog, row = null) {
  const categoriaEnCatalogo = !row?.categoria || catalog.some((c) => c.categoria === row.categoria);
  const options = catalog.map((c) => {
    const selected = c.categoria === row?.categoria ? ' selected' : '';
    return `<option value="${escapeHtml(c.categoria)}"${selected}>${escapeHtml(c.categoria)}</option>`;
  }).join('') + (row?.categoria && !categoriaEnCatalogo
    ? `<option value="${escapeHtml(row.categoria)}" selected>${escapeHtml(row.categoria)}</option>` : '');
  const entry = row?.categoria ? catalog.find((c) => c.categoria === row.categoria) : null;
  const subcategorias = entry ? entry.subcategorias : [];
  const subcategoriaEnCatalogo = !row?.subcategoria || subcategorias.includes(row.subcategoria);
  const subOptions = subcategorias.map((s) => {
    const selected = s === row?.subcategoria ? ' selected' : '';
    return `<option value="${escapeHtml(s)}"${selected}>${escapeHtml(s)}</option>`;
  }).join('') + (row?.subcategoria && !subcategoriaEnCatalogo
    ? `<option value="${escapeHtml(row.subcategoria)}" selected>${escapeHtml(row.subcategoria)}</option>` : '');
  const categoriaPlaceholderSelected = row?.categoria ? '' : ' selected';
  const subcategoriaPlaceholderSelected = row?.subcategoria ? '' : ' selected';
  return `<label class="form-field" for="field-categoria">Categoría
    <select id="field-categoria" name="categoria" aria-describedby="error-categoria">
      <option value=""${categoriaPlaceholderSelected}>Sin categoría</option>
      ${options}
    </select>
    <span class="field-error" id="error-categoria"></span></label>
    <label class="form-field" for="field-subcategoria">Subcategoría
    <select id="field-subcategoria" name="subcategoria" aria-describedby="error-subcategoria">
      <option value=""${subcategoriaPlaceholderSelected}>Sin subcategoría</option>
      ${subOptions}
    </select>
    <span class="field-error" id="error-subcategoria"></span></label>`;
}

// Texto libre + datalist para el formulario de fijo SIN catálogo (brief
// t_38a7253f F1b, hallazgo A). Desde F1b-fix2 (hallazgo 1 del revisor),
// `openForm()` ya NO toma este camino en producción: sin catálogo válido
// bloquea el form entero (ver `renderFixedCatalogBlocked`) en vez de caer a
// texto libre. `formMarkup` conserva esta rama como función pura para quien
// la invoque directamente sin catálogo (ver su propia cobertura de tests,
// brief F1 #5) -- las sugerencias del datalist vienen de los fijos ya
// cargados, ya que no hay otro origen posible sin el catálogo.
function formFixedCategoryText(row = null) {
  const categories = [...new Set(DATA.fijos.map((item) => item.categoria).filter(Boolean))].sort();
  const subcategories = [...new Set(DATA.fijos.map((item) => item.subcategoria).filter(Boolean))].sort();
  return `${formField('categoria', 'Categoría', row?.categoria || '', 'text', 'list="fixed-categorias"')}
    <datalist id="fixed-categorias">${categories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
    ${formField('subcategoria', 'Subcategoría', row?.subcategoria || '', 'text', 'list="fixed-subcategorias"')}
    <datalist id="fixed-subcategorias">${subcategories.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>`;
}

// Repuebla #field-subcategoria con las subcategorías de la categoría elegida,
// solo esas (nunca las de otra categoría). Sin selección, o sin subcategorías
// para esa categoría, queda únicamente la opción "Sin subcategoría".
function onExpenseCategoriaChange() {
  const categoriaSelect = document.getElementById('field-categoria');
  const subcategoriaSelect = document.getElementById('field-subcategoria');
  if (!categoriaSelect || !subcategoriaSelect || !activeExpenseCatalog) return;
  const entry = activeExpenseCatalog.find((c) => c.categoria === categoriaSelect.value);
  const subcategorias = entry ? entry.subcategorias : [];
  subcategoriaSelect.innerHTML = '<option value="">Sin subcategoría</option>' +
    subcategorias.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
  subcategoriaSelect.value = '';
}

function formMarkup(kind, row, categoriesCatalog) {
  if (kind === 'expense-delete') return `<p>Se dará de baja únicamente esta fila: ${escapeHtml(row.descripcion_original || row.categoria)} · ${escapeHtml(row.fecha)} · cuota ${cuotaLabel(row)} · ${fmtARSExact(row.monto)}. Las demás cuotas permanecen.</p>`;
  if (kind === 'expense-saldar') {
    const { pct1, pct2 } = getRowPct(row);
    const monto = Number(row.monto) || 0;
    return `<p>Se marcará como saldado: ${escapeHtml(row.descripcion_original || row.categoria)} · ${escapeHtml(row.fecha)} · ${fmtARSExact(monto)}, pagado por ${escapeHtml(row.pagado_por)} (reparto ${pct1}% ${P1} / ${pct2}% ${P2}). Deja de computar en la deuda neta; no se puede deshacer desde el dashboard.</p>`;
  }
  if (kind === 'expense-saldar-todas') {
    const rows = getDebtRows();
    if (!rows.length) return '<p>No hay deudas pendientes para saldar.</p>';
    const total = sum(rows, 'monto');
    return `<p>Se van a marcar como saldados ${rows.length} gasto${rows.length === 1 ? '' : 's'} pendiente${rows.length === 1 ? '' : 's'}, por un total de ${fmtARSExact(total)}. Esto deja la deuda neta entre ${P1} y ${P2} en $0; no se puede deshacer desde el dashboard.</p>`;
  }
  if (kind === 'income-delete') return `<p>Se dará de baja el ingreso de ${escapeHtml(row.persona)}: ${escapeHtml(row.descripcion_original || row.categoria)} · ${escapeHtml(row.fecha)} · ${fmtARSExact(row.monto)}.${row.categoria === 'Salario' ? ' Es un ingreso de Salario: esta baja puede cambiar la proporción del mes y las deudas.' : ''}</p>`;
  if (kind === 'fixed-delete') return `<p>La baja de ${escapeHtml(row.nombre)} crea una versión inactiva. El historial permanece.</p>${formField('fecha_baja', 'Fecha de baja', todayLocalISO(), 'date', 'required')}`;
  if (kind === 'inventory-delete') return `<p>Se dará de baja el bien "${escapeHtml(row.nombre)}"${row.categoria ? ` (${escapeHtml(row.categoria)})` : ''}, valor estimado ${fmtARSExact(row.valor_estimado)}.</p>`;
  if (kind === 'inventory' || kind === 'inventory-edit') {
    const categorias = [...new Set(DATA.inventario.map((it) => it.categoria).filter(Boolean))].sort();
    const ubicaciones = [...new Set(DATA.inventario.map((it) => it.ubicacion).filter(Boolean))].sort();
    // proporcion_jd=null en edición (hallazgo 4 del revisor fc195491): el campo
    // queda vacío con placeholder, nunca precargado en 50 — precargarlo en 50
    // haría que editar cualquier otro campo lo mande como un 50/50 declarado,
    // perdiendo el estado "sin dato" que la tabla preserva. En el alta (row
    // null) sigue el default 50 que ya existía.
    const proporcionSinDato = kind === 'inventory-edit' && row && row.proporcion_jd === null;
    const pctJD = proporcionSinDato ? '' : (row?.proporcion_jd ?? 50);
    const pctJDExtra = 'min="0" max="100" step="any" inputmode="decimal" oninput="onInventoryProporcionChange()"' +
      (proporcionSinDato ? ' placeholder="sin dato, 50/50 por defecto en cálculos"' : '');
    return `${formField('nombre', 'Descripción', row?.nombre || '', 'text', 'required')}
      ${formField('categoria', 'Categoría', row?.categoria || '', 'text', 'list="inventario-categorias"')}
      <datalist id="inventario-categorias">${categorias.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
      ${formField('ubicacion', 'Ubicación', row?.ubicacion || '', 'text', 'list="inventario-ubicaciones"')}
      <datalist id="inventario-ubicaciones">${ubicaciones.map((v) => `<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>
      ${formField('valor_estimado', 'Valor estimado (ARS)', row?.valor_estimado ?? '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
      ${formField('fecha_adquisicion', 'Fecha de compra (opcional)', row?.fecha_adquisicion || '', 'date')}
      ${formField('precio_ars', 'ARS pagado en la compra (opcional)', row?.precio_ars ?? '', 'number', 'min="0" max="1000000000000" step="0.01" oninput="onInventoryUsdSugerido()"')}
      ${formField('cotizacion_usd_compra', 'Cotización USD al comprar (opcional)', row?.cotizacion_usd_compra ?? '', 'number', 'min="0" max="1000000000000" step="0.01" oninput="onInventoryUsdSugerido()"')}
      ${formField('precio_usd_compra', 'USD de compra (sugerido = ARS / cotización)', row?.precio_usd_compra ?? '', 'number', 'min="0" max="1000000000000" step="0.01" oninput="onInventoryUsdEdited()"')}
      <div id="inventory-proportion">${formField('proporcion_jd', 'JD (%)', pctJD, 'number', pctJDExtra)}
      <p class="form-help">Pinki: <output id="inventory-pinki-percent" aria-live="polite">${pctJD !== '' && Number.isFinite(Number(pctJD)) ? `${100 - Number(pctJD)}%` : '—'}</output></p></div>
      ${formField('precio_venta_estimado_usd', 'Precio de reventa estimado (USD, opcional)', row?.precio_venta_estimado_usd ?? '', 'number', 'min="0" max="1000000000000" step="0.01"')}
      ${formSelect('estado', 'Estado', INVENTARIO_ESTADOS, row?.estado || 'Activo')}
      ${formField('notas', 'Notas', row?.notas || '')}`;
  }
  if (kind === 'expense' || kind === 'expense-edit') {
    const isEdit = kind === 'expense-edit';
    const categoryFields = categoriesCatalog ? formExpenseCategorySelects(categoriesCatalog, row) : formExpenseCategoryText(row);
    const tipoProporcion = row?.tipo_proporcion || 'dinamico';
    const proporcionJd = tipoProporcion === 'custom' && row?.proporcion_jd != null ? row.proporcion_jd : '50';
    const proporcionPinki = tipoProporcion === 'custom' && row?.proporcion_pinki != null ? row.proporcion_pinki : '50';
    return `${isEdit ? `<p class="form-help">Esta edición aplica solo a esta fila (cuota ${escapeHtml(cuotaLabel(row))} de ${escapeHtml(String(row.cuotas_total))}); las demás cuotas de este gasto no cambian. La cantidad de cuotas no se puede editar desde aquí.</p>` : ''}
      ${formField('monto', 'Monto total (ARS)', row?.monto ?? '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
      ${formField('fecha', 'Fecha', row?.fecha || todayLocalISO(), 'date', 'required')}
      ${categoryFields}
      ${formField('descripcion_original', 'Descripción', row?.descripcion_original || '')}
      ${formSelect('medio_pago', 'Medio de pago', ['Efectivo', 'Transferencia', 'Débito', 'Crédito'], row?.medio_pago || 'Efectivo')}
      ${formSelect('pagado_por', 'Pagó', ['Común', 'JD', 'Pinki'], row?.pagado_por || 'Común')}
      ${formSelect('tipo_proporcion', 'Reparto', [
        { value: 'dinamico', label: 'Dinámico según salarios del mes' },
        { value: '50/50', label: 'Mitad y mitad' },
        { value: 'jd_100', label: '100% JD' },
        { value: 'pinki_100', label: '100% Pinki' },
        { value: 'custom', label: 'Manual por porcentajes' },
      ], tipoProporcion)}
      <div id="custom-proportion" hidden>${formField('proporcion_jd', 'JD (%)', proporcionJd, 'number', 'min="0" max="100" step="0.01"')}
      ${formField('proporcion_pinki', 'Pinki (%)', proporcionPinki, 'number', 'min="0" max="100" step="0.01"')}</div>
      ${isEdit ? '' : formField('cuotas_total', 'Cantidad de cuotas', '1', 'number', 'required min="1" max="120" step="1"')}`;
  }
  if (kind === 'income' || kind === 'income-edit') return `
    ${formField('monto', 'Monto (ARS)', row?.monto ?? '', 'number', 'required min="0.01" max="1000000000000" step="0.01"')}
    ${formField('fecha', 'Fecha', row?.fecha || todayLocalISO(), 'date', 'required')}
    ${formSelect('persona', 'Persona', ['JD', 'Pinki'], row?.persona || 'JD')}
    ${formSelect('categoria', 'Categoría', ['Salario', 'Extra', 'Freelance', 'Otro'], row?.categoria || 'Salario')}
    ${formField('descripcion_original', 'Descripción', row?.descripcion_original || '')}`;
  const fixedSplit = row?.responsable === 'Común' && row.tipo_proporcion === 'custom' ? 'custom' : 'dinamica';
  const fixedCategoryFields = categoriesCatalog ? formFixedCategorySelects(categoriesCatalog, row) : formFixedCategoryText(row);
  return `${formField('nombre', 'Descripción', row?.nombre || '', 'text', 'required')}
    ${fixedCategoryFields}
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

async function openForm(kind, id = null) {
  if (!liveMode || writePending || reloadPending || reloadFailed) return;
  if (kind.startsWith('inventory') && !inventoryAvailable) return;
  const source = kind.startsWith('expense') ? DATA.gastos
    : kind.startsWith('income') ? DATA.ingresos
    : kind.startsWith('inventory') ? DATA.inventario
    : DATA.fijos;
  const row = id === null ? null : source.find((item) => canonicalId(item.id) === canonicalId(id));
  if (id !== null && !row) return;
  // Si el bien ya tiene precio_usd_compra != null al abrir el formulario de
  // edición (hallazgo 3 del revisor fc195491), arranca en `true`: no se
  // autosugiere sobre un USD ya explícito. Solo se arranca en `false` (y se
  // autosugiere) cuando el campo está vacío — alta, o edición sin ese dato.
  if (kind.startsWith('inventory')) {
    inventoryUsdEditedManually = row != null && row.precio_usd_compra !== null && row.precio_usd_compra !== undefined;
  }
  // Si ya hay una apertura en curso (modal abierto o cargando), el foco actual
  // está dentro del modal (ej: #form-close) y no es un disparador real: se
  // conserva el returnFocus original en vez de reemplazarlo.
  const returnFocus = activeForm ? activeForm.returnFocus : document.activeElement;
  const form = activeForm = { kind, row, returnFocus, confirmed: false, payload: null };
  const titles = {
    expense: 'Agregar gasto', 'expense-edit': 'Editar gasto', 'expense-delete': 'Dar de baja una cuota', 'expense-saldar': 'Saldar gasto',
    'expense-saldar-todas': 'Saldar todas las deudas',
    income: 'Agregar ingreso', 'income-edit': 'Editar ingreso', 'income-delete': 'Dar de baja ingreso',
    inventory: 'Agregar bien', 'inventory-edit': 'Editar bien', 'inventory-delete': 'Dar de baja bien',
    fixed: 'Agregar fijo', 'fixed-edit': 'Crear versión de fijo', 'fixed-delete': 'Dar de baja fijo',
  };
  document.getElementById('form-title').textContent = titles[kind];
  document.getElementById('form-intro').textContent = kind.includes('delete') || kind === 'expense-saldar' || kind === 'expense-saldar-todas'
    ? 'Revisá qué cambio se aplicará.' : 'Completá los datos y revisá el resumen antes de guardar.';
  document.getElementById('form-errors').textContent = '';
  document.getElementById('form-confirm').hidden = true;
  document.getElementById('form-back').hidden = true;
  document.getElementById('form-back').disabled = false;
  document.getElementById('form-close').disabled = false;
  document.getElementById('form-submit').hidden = false;
  document.getElementById('form-submit').disabled = false;
  let catalog = null;
  let catalogWarning = '';
  if (kind === 'expense' || kind === 'expense-edit' || kind === 'fixed' || kind === 'fixed-edit') {
    // Mostrar el modal YA, en estado de carga: así Escape/Cancelar operan sobre el
    // listener del modal mientras el catálogo todavía no resolvió, en vez de dejar
    // el foco afuera en el disparador durante el fetch.
    document.getElementById('form-fields').innerHTML = '<p class="form-loading" role="status" aria-live="polite">Cargando categorías…</p>';
    document.getElementById('form-fields').hidden = false;
    document.getElementById('form-submit').textContent = 'Revisar';
    document.getElementById('form-submit').disabled = true;
    document.getElementById('form-modal').hidden = false;
    document.getElementById('form-close').focus();
    try {
      catalog = await loadCategoriasGasto();
    } catch {
      catalog = null;
      catalogWarning = '<p class="form-warning">No se pudo cargar el catálogo de categorías. Completá categoría y subcategoría como texto libre.</p>';
    }
    // El modal pudo cerrarse, o reabrirse (mismo u otro tipo), mientras esperaba el
    // fetch: esta apertura ya no es la vigente. Comparar identidad, no `kind`,
    // porque dos aperturas de 'expense' en carrera comparten el mismo kind.
    if (activeForm !== form) return;
    activeExpenseCatalog = catalog;
    // Fail-closed para fijos (brief t_38a7253f F1b-fix2, hallazgo 1 del revisor):
    // a diferencia de gasto, sin catálogo válido no hay texto libre de
    // respaldo -- se bloquea el formulario entero (ni nombre ni monto quedan
    // editables) hasta reintentar con éxito. Gasto conserva el fallback a
    // texto libre: ya tenía categoría obligatoria y no fue objeto de este hallazgo.
    if (!catalog && kind.startsWith('fixed')) {
      form.catalogBlocked = true;
      renderFixedCatalogBlocked();
      return;
    }
  }
  document.getElementById('form-fields').innerHTML = catalogWarning + formMarkup(kind, row, catalog);
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-submit').disabled = false;
  document.getElementById('form-modal').hidden = false;
  document.getElementById('form-modal').querySelector('input, select, button').focus();
  syncCustomProportion();
  if (kind === 'expense' && catalog) onExpenseCategoriaChange();
}

function closeForm() {
  if (writePending) return;
  document.getElementById('form-modal').hidden = true;
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-confirm').hidden = true;
  document.getElementById('form-back').hidden = true;
  document.getElementById('form-back').disabled = false;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-submit').hidden = false;
  document.getElementById('form-submit').disabled = false;
  document.getElementById('form-close').disabled = false;
  document.getElementById('form-errors').textContent = '';
  document.querySelectorAll('.field-error').forEach((el) => { el.textContent = ''; });
  const focus = activeForm?.returnFocus;
  activeForm = null;
  if (focus?.isConnected) focus.focus();
  else document.getElementById('tab-' + currentView)?.focus();
}

// Pinta el bloqueo fail-closed del form de fijo sin catálogo (ver openForm):
// solo el aviso y "Reintentar" -- ni nombre, monto ni ningún otro campo del
// fijo quedan expuestos mientras no haya categorías confiables.
function renderFixedCatalogBlocked() {
  document.getElementById('form-fields').innerHTML =
    '<p class="form-warning" role="alert">No se pudo cargar el catálogo de categorías. No es posible crear ni editar fijos sin él.</p>' +
    '<button type="button" id="fixed-catalog-retry" onclick="retryFixedCatalog()">Reintentar</button>';
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-submit').hidden = true;
  document.getElementById('form-submit').disabled = true;
  document.getElementById('form-modal').hidden = false;
  document.getElementById('form-modal').querySelector('input, select, button').focus();
}

// Vuelve a pedir el catálogo desde el botón "Reintentar" del bloqueo
// fail-closed. Si vuelve a fallar, se mantiene bloqueado; si llega, recién
// ahí se pinta el form real (categoría/subcategoría + el resto de los campos).
async function retryFixedCatalog() {
  if (!activeForm?.catalogBlocked) return;
  const form = activeForm;
  document.getElementById('form-fields').innerHTML = '<p class="form-loading" role="status" aria-live="polite">Cargando categorías…</p>';
  let catalog = null;
  try {
    catalog = await loadCategoriasGasto();
  } catch {
    catalog = null;
  }
  if (activeForm !== form) return;
  activeExpenseCatalog = catalog;
  if (!catalog) {
    renderFixedCatalogBlocked();
    return;
  }
  form.catalogBlocked = false;
  document.getElementById('form-submit').hidden = false;
  document.getElementById('form-fields').innerHTML = formMarkup(form.kind, form.row, catalog);
  document.getElementById('form-fields').hidden = false;
  document.getElementById('form-submit').textContent = 'Revisar';
  document.getElementById('form-submit').disabled = false;
  document.getElementById('form-modal').querySelector('input, select, button').focus();
  syncCustomProportion();
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

// Sugerencia en vivo de precio_usd_compra = precio_ars / cotizacion_usd_compra
// (brief t_0e38e74e punto 3: "sugerencia de USD = ARS / cotización"). Solo
// sugiere — nunca pisa un USD que el usuario ya haya completado a mano
// (hallazgo 4 del revisor 46d4f3d5): si el campo tiene contenido Y el
// usuario lo tocó directamente (ver onInventoryUsdEdited), se deja intacto.
function onInventoryUsdSugerido() {
  const arsInput = document.getElementById('field-precio_ars');
  const cotInput = document.getElementById('field-cotizacion_usd_compra');
  const usdInput = document.getElementById('field-precio_usd_compra');
  if (!arsInput || !cotInput || !usdInput) return;
  if (usdInput.value.trim() && inventoryUsdEditedManually) return;
  const ars = Number(arsInput.value);
  const cot = Number(cotInput.value);
  if (Number.isFinite(ars) && ars > 0 && Number.isFinite(cot) && cot > 0) {
    usdInput.value = (ars / cot).toFixed(2);
  }
}

// Marca que el usuario escribió directamente en el campo USD de compra, para
// que onInventoryUsdSugerido deje de pisarlo mientras tenga contenido.
function onInventoryUsdEdited() {
  inventoryUsdEditedManually = true;
}

// Muestra el % de Pinki al lado del de JD, igual que en el reparto de fijos
// (ver syncCustomProportion) pero sin deshabilitar nada: proporcion_jd es
// siempre editable en el formulario de inventario.
function onInventoryProporcionChange() {
  const jdInput = document.getElementById('field-proporcion_jd');
  const pinkiOutput = document.getElementById('inventory-pinki-percent');
  if (!jdInput || !pinkiOutput) return;
  const value = Number(jdInput.value);
  pinkiOutput.textContent = validFixedPercent(jdInput.value) ? `${100 - value}%` : '—';
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

// Igual que validMoney, pero admite 0 — para los campos monetarios opcionales
// de paridad con el legacy (precio_ars, cotizacion_usd_compra, etc.), que en
// el servidor se validan con positive=False (ver api.py, INVENTORY_MONEY_OPTIONAL_FIELDS).
function validMoneyOptional(raw) {
  if (!/^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(String(raw))) return false;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && value <= 1e12;
}

function validDate(raw) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return false;
  const date = new Date(`${raw}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === raw;
}

function collectForm(kind, row, values) {
  const errors = {};
  if (kind === 'expense-saldar' || kind === 'expense-saldar-todas') return { payload: null, errors };
  // Inventario tiene su propia forma (campos y fecha opcional distintos de
  // gastos/ingresos/fijos): se resuelve aparte en vez de forzarla en la
  // lógica genérica de dateKey/moneyKey de abajo, pensada para esos tres.
  if (kind.startsWith('inventory')) {
    if (kind === 'inventory-delete') return { payload: null, errors };
    if (!values.nombre?.trim()) errors.nombre = 'Ingresá una descripción.';
    if (!validMoney(values.valor_estimado)) {
      errors.valor_estimado = 'Ingresá un valor positivo, finito, de hasta 2 decimales y máximo 1 billón.';
    }
    if (values.fecha_adquisicion?.trim() && !validDate(values.fecha_adquisicion)) {
      errors.fecha_adquisicion = 'Ingresá una fecha válida o dejala vacía.';
    }
    // Campos de paridad con el legacy (t_0e38e74e): todos opcionales. Si se
    // completan, deben respetar el mismo formato de monto que valor_estimado,
    // pero admitiendo 0 (ver validMoneyOptional / INVENTORY_MONEY_OPTIONAL_FIELDS en api.py).
    for (const field of ['precio_ars', 'cotizacion_usd_compra', 'precio_usd_compra', 'precio_venta_estimado_usd']) {
      if (values[field]?.trim() && !validMoneyOptional(values[field])) {
        errors[field] = 'Ingresá un monto válido (≥ 0, hasta 2 decimales, máximo 1 billón) o dejalo vacío.';
      }
    }
    if (values.proporcion_jd?.trim() && !validFixedPercent(values.proporcion_jd)) {
      errors.proporcion_jd = 'Ingresá un porcentaje de JD entre 0 y 100, o dejalo vacío.';
    }
    if (values.estado && !INVENTARIO_ESTADOS.includes(values.estado)) {
      errors.estado = 'Elegí un estado válido.';
    }
    const payload = { nombre: values.nombre.trim(), valor_estimado: Number(values.valor_estimado) };
    // En edición, vaciar un campo opcional lo manda explícito en `null` para
    // que el PATCH lo borre (api.py acepta `null` para todos los opcionales
    // de inventario, t_0e38e74e hallazgo 3 del revisor 46d4f3d5); en el alta
    // se sigue omitiendo sin más — no hay nada previo que borrar.
    const isEdit = kind === 'inventory-edit';
    if (values.categoria?.trim()) payload.categoria = values.categoria.trim();
    else if (isEdit) payload.categoria = null;
    if (values.ubicacion?.trim()) payload.ubicacion = values.ubicacion.trim();
    else if (isEdit) payload.ubicacion = null;
    if (values.fecha_adquisicion?.trim()) payload.fecha_adquisicion = values.fecha_adquisicion;
    else if (isEdit) payload.fecha_adquisicion = null;
    if (values.notas?.trim()) payload.notas = values.notas.trim();
    else if (isEdit) payload.notas = null;
    if (values.precio_ars?.trim()) payload.precio_ars = Number(values.precio_ars);
    else if (isEdit) payload.precio_ars = null;
    if (values.cotizacion_usd_compra?.trim()) payload.cotizacion_usd_compra = Number(values.cotizacion_usd_compra);
    else if (isEdit) payload.cotizacion_usd_compra = null;
    if (values.precio_usd_compra?.trim()) payload.precio_usd_compra = Number(values.precio_usd_compra);
    else if (isEdit) payload.precio_usd_compra = null;
    if (values.precio_venta_estimado_usd?.trim()) payload.precio_venta_estimado_usd = Number(values.precio_venta_estimado_usd);
    else if (isEdit) payload.precio_venta_estimado_usd = null;
    if (values.proporcion_jd?.trim()) payload.proporcion_jd = Number(values.proporcion_jd);
    else if (isEdit) payload.proporcion_jd = null;
    if (values.estado) payload.estado = values.estado;
    return { payload, errors };
  }
  const dateKey = kind === 'fixed-delete' ? 'fecha_baja' : kind.startsWith('fixed') ? 'vigente_desde' : 'fecha';
  if (kind !== 'expense-delete' && kind !== 'income-delete' && !validDate(values[dateKey])) errors[dateKey] = 'Ingresá una fecha válida.';
  if (kind.endsWith('delete')) return { payload: kind === 'fixed-delete' ? { fecha_baja: values.fecha_baja } : null, errors };
  const moneyKey = kind.startsWith('fixed') ? 'monto_estimado' : 'monto';
  if (!validMoney(values[moneyKey])) errors[moneyKey] = 'Ingresá un monto positivo, finito, de hasta 2 decimales y máximo 1 billón.';
  if (kind === 'expense' || kind === 'expense-edit') {
    const isEdit = kind === 'expense-edit';
    if (!values.categoria?.trim()) errors.categoria = 'Ingresá una categoría.';
    const payload = { fecha: values.fecha, monto: Number(values.monto), categoria: values.categoria.trim(),
      subcategoria: values.subcategoria.trim(), descripcion_original: values.descripcion_original.trim(),
      medio_pago: values.medio_pago, pagado_por: values.pagado_por, tipo_proporcion: values.tipo_proporcion };
    if (!isEdit) {
      const cuotas = Number(values.cuotas_total);
      if (!/^\d+$/.test(values.cuotas_total) || !Number.isInteger(cuotas) || cuotas < 1 || cuotas > 120 ||
          Math.round(Number(values.monto) * 100) < cuotas) errors.cuotas_total = 'Entre 1 y 120 cuotas, con al menos un centavo por cuota.';
      payload.cuotas_total = cuotas;
    }
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
    } else if (values.tipo_proporcion === 'jd_100' || values.tipo_proporcion === 'pinki_100' || values.tipo_proporcion === '50/50') {
      // Atajos de reparto (brief F1 #6, y fix4 hallazgo 6 del revisor para
      // 'Mitad y mitad'): el backend solo conoce 'dinamico'/'custom' (ver
      // validaciones.TIPO_PROPORCION_VALIDOS) -- enviar '50/50' tal cual lo
      // rechaza. Los tres presets viajan como 'custom' con el porcentaje ya
      // resuelto, sin pasar por los campos manuales (ocultos y deshabilitados
      // para estas opciones, ver syncCustomProportion).
      const jd = values.tipo_proporcion === 'jd_100' ? 100 : values.tipo_proporcion === 'pinki_100' ? 0 : 50;
      payload.tipo_proporcion = 'custom';
      payload.proporcion_jd = jd;
      payload.proporcion_pinki = 100 - jd;
    } else if (isEdit) {
      // Al editar, cambiar de 'custom' a otro reparto debe limpiar explícitamente
      // los porcentajes guardados -- sin esto, validar_expense rechaza la edición
      // (tipo_proporcion='dinamico' no admite proporcion_jd/proporcion_pinki, y
      // el servidor valida la fila RESULTANTE: fila actual + estos cambios).
      payload.proporcion_jd = null;
      payload.proporcion_pinki = null;
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
  // Semántica explícita omitido/null (brief t_38a7253f F1b-fix2, hallazgo 2
  // del revisor; espejo de `db.resolve_fixed_categoria`): en edición, elegir
  // "Sin categoría/subcategoría" cuando antes había un valor envía `null`
  // EXPLÍCITO (vacía); si no cambió respecto a la versión vigente, se omite
  // el campo (hereda). En alta no hay versión anterior: un valor vacío
  // simplemente se omite, igual que siempre.
  const isEditFixed = kind === 'fixed-edit';
  const nuevaCategoria = values.categoria?.trim() || '';
  const categoriaAnterior = row?.categoria || '';
  if (nuevaCategoria) {
    if (!isEditFixed || nuevaCategoria !== categoriaAnterior) payload.categoria = nuevaCategoria;
  } else if (isEditFixed && categoriaAnterior) {
    payload.categoria = null;
  }
  const nuevaSubcategoria = values.subcategoria?.trim() || '';
  const subcategoriaAnterior = row?.subcategoria || '';
  if (nuevaSubcategoria) {
    if (!isEditFixed || nuevaSubcategoria !== subcategoriaAnterior) payload.subcategoria = nuevaSubcategoria;
  } else if (isEditFixed && subcategoriaAnterior) {
    payload.subcategoria = null;
  }
  // Regla de dominio (válida tanto en alta como en edición, espejo del
  // backend): no puede quedar subcategoría sin categoría. El <select>
  // dependiente (onExpenseCategoriaChange) ya lo evita en el uso normal --
  // esto es la segunda capa de defensa en el propio formulario.
  if (nuevaSubcategoria && !nuevaCategoria) {
    errors.subcategoria = 'No podés elegir una subcategoría sin categoría.';
  }
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
  if (kind === 'expense-saldar') return `Saldar el gasto #${canonicalId(row.id)}, ${fmtARSExact(row.monto)} pagado por ${row.pagado_por}. Deja de computar en la deuda neta.`;
  if (kind === 'expense-saldar-todas') {
    const rows = getDebtRows();
    const total = sum(rows, 'monto');
    return `Saldar ${rows.length} gasto${rows.length === 1 ? '' : 's'} pendiente${rows.length === 1 ? '' : 's'} por un total de ${fmtARSExact(total)}. Deja la deuda neta entre ${P1} y ${P2} en $0.`;
  }
  if (kind === 'expense-delete') return `Baja solo de la cuota ${cuotaLabel(row)} del gasto #${row.id}, ${fmtARSExact(row.monto)}. Otras cuotas no se borran.`;
  if (kind === 'fixed-delete') return `Baja de ${row.nombre} desde ${payload.fecha_baja}. Se crea una versión inactiva; el historial permanece.`;
  if (kind === 'expense') return `Gasto ${payload.categoria}${payload.subcategoria ? ` / ${payload.subcategoria}` : ''}: ${fmtARSExact(payload.monto)}, ${payload.fecha}, ${payload.cuotas_total} cuota(s). ${payload.descripcion_original || 'Sin descripción'}. Medio: ${payload.medio_pago}. Pagó ${payload.pagado_por}; reparto ${payload.tipo_proporcion}${payload.tipo_proporcion === 'custom' ? ` (${payload.proporcion_jd}% JD / ${payload.proporcion_pinki}% Pinki)` : ''}.`;
  if (kind === 'expense-edit') return `Editar gasto #${canonicalId(row.id)} (cuota ${cuotaLabel(row)} de ${row.cuotas_total}): ${payload.categoria}${payload.subcategoria ? ` / ${payload.subcategoria}` : ''}, ${fmtARSExact(payload.monto)}, ${payload.fecha}. ${payload.descripcion_original || 'Sin descripción'}. Medio: ${payload.medio_pago}. Pagó ${payload.pagado_por}; reparto ${payload.tipo_proporcion}${payload.tipo_proporcion === 'custom' ? ` (${payload.proporcion_jd}% JD / ${payload.proporcion_pinki}% Pinki)` : ''}. Las demás cuotas de este gasto no cambian.`;
  if (kind === 'income-delete') return `Baja del ingreso de ${row.persona} del ${row.fecha}, ${fmtARSExact(row.monto)}.${row.categoria === 'Salario' ? ' Es un ingreso de Salario: puede cambiar la proporción del mes y las deudas.' : ''}`;
  if (kind.startsWith('income')) return `${kind === 'income-edit' ? 'Editar' : 'Agregar'} ingreso ${payload.categoria} de ${payload.persona}: ${fmtARSExact(payload.monto)} el ${payload.fecha}. ${payload.descripcion_original || 'Sin descripción'}.${row?.categoria === 'Salario' || payload.categoria === 'Salario' ? ' Este cambio salarial puede modificar las proporciones de los meses afectados y sus deudas.' : ''}`;
  if (kind === 'inventory-delete') return `Baja del bien "${row.nombre}"${row.categoria ? ` (${row.categoria})` : ''}, valor estimado ${fmtARSExact(row.valor_estimado)}, estado ${row.estado || 'Activo'}.`;
  if (kind.startsWith('inventory')) return `${kind === 'inventory-edit' ? 'Editar' : 'Agregar'} bien "${payload.nombre}"${payload.categoria ? ` · ${payload.categoria}` : ''}${payload.ubicacion ? ` · ${payload.ubicacion}` : ''}: ${fmtARSExact(payload.valor_estimado)}${payload.fecha_adquisicion ? ` · adquirido ${payload.fecha_adquisicion}` : ''}. Estado ${payload.estado || 'Activo'}${payload.precio_usd_compra != null ? `, U$D ${payload.precio_usd_compra} de compra` : ''}${payload.proporcion_jd != null ? `, reparto ${payload.proporcion_jd}% JD / ${100 - payload.proporcion_jd}% Pinki` : ''}.`;
  const fixedSplit = payload.responsable === 'Común'
    ? payload.tipo_proporcion === 'custom' ? `${payload.proporcion_jd}% JD / ${100 - payload.proporcion_jd}% Pinki`
      : payload.tipo_proporcion === 'dinamica' ? 'dinámico según salarios' : fijosRepartoLabel(row)
    : '100% personal';
  const fixedCategoria = Object.prototype.hasOwnProperty.call(payload, 'categoria') ? payload.categoria : row?.categoria;
  const fixedSubcategoria = Object.prototype.hasOwnProperty.call(payload, 'subcategoria') ? payload.subcategoria
    : fixedCategoria ? row?.subcategoria : null;
  const fixedCategoryLabel = kind === 'fixed-edit'
    ? ` (categoría: ${fixedCategoria || 'Sin categoría'}; subcategoría: ${fixedSubcategoria || 'Sin subcategoría'})`
    : fixedCategoria ? ` (${fixedCategoria}${fixedSubcategoria ? ` / ${fixedSubcategoria}` : ''})` : '';
  return `${kind === 'fixed-edit' ? 'Nueva versión de' : 'Nuevo fijo'} ${payload.nombre}${fixedCategoryLabel}: ${fmtARSExact(payload.monto_estimado)} ${payload.periodicidad}, responsable ${payload.responsable}, reparto ${fixedSplit}, desde ${payload.vigente_desde}. ${kind === 'fixed-edit' ? 'Se crea una nueva versión; la anterior queda en el historial.' : ''}`;
}

function routeForForm(kind, row) {
  if (kind === 'expense') return ['POST', '/api/expenses'];
  if (kind === 'expense-edit') return ['PATCH', `/api/expenses/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'expense-delete') return ['DELETE', `/api/expenses/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'expense-saldar') return ['POST', `/api/expenses/${encodeURIComponent(canonicalId(row.id))}/saldar`];
  if (kind === 'expense-saldar-todas') return ['POST', '/api/expenses/saldar-todas'];
  if (kind === 'income') return ['POST', '/api/income'];
  if (kind === 'income-edit') return ['PATCH', `/api/income/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'income-delete') return ['DELETE', `/api/income/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'inventory') return ['POST', '/api/inventory'];
  if (kind === 'inventory-edit') return ['PATCH', `/api/inventory/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'inventory-delete') return ['DELETE', `/api/inventory/${encodeURIComponent(canonicalId(row.id))}`];
  if (kind === 'fixed') return ['POST', '/api/fixed'];
  return [kind === 'fixed-delete' ? 'DELETE' : 'PATCH', `/api/fixed/${encodeURIComponent(canonicalId(row.id))}`];
}

function verifiedWriteEnvelope(kind, row, result) {
  try {
    if (kind === 'expense-delete' || kind === 'income-delete' || kind === 'inventory-delete') {
      return result?.deleted === true && canonicalId(result.id) === canonicalId(row.id);
    }
    if (kind === 'expense') return Array.isArray(result?.expenses) && result.expenses.length > 0 &&
      result.expenses.every((expense) => !!canonicalId(expense?.id));
    if (kind === 'expense-edit') return !!canonicalId(result?.expense?.id) &&
      canonicalId(result.expense.id) === canonicalId(row.id);
    if (kind === 'expense-saldar') return !!canonicalId(result?.expense?.id) &&
      canonicalId(result.expense.id) === canonicalId(row.id) && result.expense.saldado != null;
    if (kind === 'expense-saldar-todas') return Array.isArray(result?.expenses) &&
      typeof result?.count === 'number' && result.count === result.expenses.length &&
      result.expenses.every((expense) => !!canonicalId(expense?.id) && expense.saldado != null);
    if (kind.startsWith('income')) return !!canonicalId(result?.income?.id);
    if (kind.startsWith('inventory')) return !!canonicalId(result?.inventory?.id);
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
  // Defensa en profundidad del fail-closed de fijos (ver renderFixedCatalogBlocked):
  // sin esto, un bug que reactivara #form-submit igual no alcanzaría a armar un payload.
  if (activeForm.catalogBlocked) return;
  const { kind, row } = activeForm;
  if (kind.startsWith('inventory') && !inventoryAvailable) return;
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
document.getElementById('form-fields').addEventListener('change', (event) => {
  if (event.target?.id === 'field-categoria') onExpenseCategoriaChange();
});
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
  updateGastosBarRange();
  const rows = filterGastosPeriod(period.from, period.to);
  const filteredRows = applyPersonaFiltro(rows);
  const varRows = filteredRows.filter((r) => (parseInt(r.cuota_nro, 10) || 1) === 1);
  const varTotal = varRows.reduce((total, row) => total + (expenseAmount(row) ?? 0), 0);
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
  const fijosCount = activeFijos().filter((row) => fixedAmount(row, fixedCutoffDate().slice(0, 7), personaFiltro) !== null).length;
  document.getElementById('g-fijos-count').textContent = DATA.loadErrors.fijos
    ? 'No se pudo cargar el listado'
    : `${fijosCount} ítem${fijosCount !== 1 ? 's' : ''} · ver detalle`;

  document.getElementById('g-cuotas').textContent = fmtARS(cuotasTotal);
  document.getElementById('g-cuotas-count').textContent =
    `${cuotasRows.length} cuota${cuotasRows.length !== 1 ? 's' : ''} activa${cuotasRows.length !== 1 ? 's' : ''} · ver detalle`;

  const creditoRows = filteredRows.filter((r) => r.medio_pago === 'Crédito');
  const creditoFijos = creditFixedItems();
  const creditoTotal = creditoRows.reduce((total, row) => total + (expenseAmount(row) ?? 0), 0)
    + creditoFijos.reduce((total, item) => total + fixedAmount(item.row, item.month, personaFiltro), 0);
  document.getElementById('g-credito').textContent = fmtARS(creditoTotal);
  document.getElementById('g-credito-sub').textContent =
    `${creditoRows.length + creditoFijos.length} ítem${creditoRows.length + creditoFijos.length !== 1 ? 's' : ''} · ver detalle`;

  renderDeudaCard();
  renderComposicion(varTotal, fixTotal, cuotasTotal);
  if (!document.getElementById('gastos-pie-body').hidden) renderGastosPie(rows);
  if (!document.getElementById('gastos-bar-body').hidden) renderGastosBar();
  if (activeCat) renderSubcatChart(activeCat);

  setupTablaCategSelect(rows);
  // monto_propio conserva el monto ORIGINAL del gasto (antes de applyPersonaMonto
  // recortarlo a la porción de la persona filtrada): la columna de reparto de la
  // tabla siempre usa el % y el monto propios del gasto, nunca el filtro activo.
  const personaFilteredRows = applyPersonaFiltro(rows);
  gastosTableRows = applyPersonaMonto(personaFilteredRows)
    .map((r, i) => ({ ...r, monto_propio: personaFilteredRows[i].monto }));
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
      if (fixedAmount(row, month, 'comun') === null) return;
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
    document.getElementById('comp-total').textContent = 'Total no disponible';
    document.getElementById('comp-legend').textContent = 'Composición no disponible: falta el archivo de fijos.';
    return;
  }
  const actualTotal = varTotal + fixTotal + cuotasTotal;
  const total = actualTotal || 1;
  const segs = [
    { name: 'Fijos', val: fixTotal, elId: 'comp-seg-fijos', color: 'var(--terracotta)' },
    { name: 'Variable', val: varTotal, elId: 'comp-seg-var', color: 'var(--mustard)' },
    { name: 'Cuotas', val: cuotasTotal, elId: 'comp-seg-cuotas', color: 'var(--plum)' },
  ].map((s) => {
    const pct = s.val / total * 100;
    return { ...s, pct, pctLabel: s.val > 0 && pct < 1 ? 'menos de 1%' : `${pct.toFixed(0)}%` };
  });
  const visibleWidths = segs.map((s) => s.val > 0 ? Math.max(s.pct, 1) : 0);
  const largestIndex = segs.findIndex((s) => s.pct === Math.max(...segs.map((item) => item.pct)));
  if (actualTotal > 0) visibleWidths[largestIndex] -= visibleWidths.reduce((sum, width) => sum + width, 0) - 100;

  segs.forEach((s, index) => {
    const el = document.getElementById(s.elId);
    el.style.width = visibleWidths[index] + '%';
  });
  document.getElementById('comp-total').textContent = `Total ${fmtARS(actualTotal)}`;

  document.getElementById('comp-legend').innerHTML = segs.map((s) => `
    <div class="composicion-leg-item" role="listitem">
      <span class="composicion-leg-dot" style="background:${s.color}" aria-hidden="true"></span>
      <span>${s.name}</span>
      <span class="composicion-leg-val">${fmtARS(s.val)}</span>
      <span class="composicion-leg-pct">(${s.pctLabel})</span>
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
  const selected = applyPersonaFiltro(rows);
  const filtered = applyPersonaMonto(selected);
  const grouped = groupBy(filtered, 'categoria');
  const keys = Object.keys(grouped).sort((a, b) => sum(grouped[b], 'monto') - sum(grouped[a], 'monto'));
  const data = keys.map((k) => sum(grouped[k], 'monto'));

  renderPieSubtotals(selected);

  destroyChart('gastos-pie');
  const canvas = document.getElementById('chart-gastos-pie');
  renderChartData(canvas, 'Gastos por categoría',
    `Período: ${period.from} a ${period.to}. Persona: ${PERSONA_FILTRO_LABELS[personaFiltro]}.`,
    ['Categoría', 'Monto'], keys.map((key, i) => [key, fmtARS(data[i])]));
  if (!data.length) {
    document.getElementById('categ-chip-row').innerHTML = '';
    if (typeof Chart === 'undefined') showChartError('gastos-pie', canvas, 'Gráfico no disponible: Chart.js no cargó. Totales y tablas siguen disponibles.');
    return;
  }

  const toggleBtn = document.getElementById('categ-pie-toggle');
  toggleBtn.textContent = categPieMode === 'doughnut' ? 'barras' : 'torta';
  toggleBtn.setAttribute('aria-label', `Cambiar tipo de gráfico por categoría a ${toggleBtn.textContent}`);

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

const CHART_PANELS = {
  gastosPie: ['gastos-pie-body', 'gastos-pie-show', () => renderGastosPie(filterGastosPeriod(period.from, period.to)), 'gastos-pie', 'gastos por categoría'],
  gastosBar: ['gastos-bar-body', 'gastos-bar-show', renderGastosBar, 'gastos-bar', 'gastos e ingresos mensuales'],
  incLines: ['inc-lines-body', 'inc-lines-show', renderIncomeLines, 'inc-lines', 'evolución de ingresos'],
};

function toggleChartPanel(name) {
  const config = CHART_PANELS[name];
  if (!config) return;
  const [bodyId, buttonId, render, chartKey, title] = config;
  const body = document.getElementById(bodyId);
  const button = document.getElementById(buttonId);
  const opening = body.hidden;
  body.hidden = !opening;
  button.setAttribute('aria-expanded', String(opening));
  button.textContent = opening ? 'Ocultar gráfico' : 'Mostrar gráfico';
  button.setAttribute('aria-label', `${opening ? 'Ocultar' : 'Mostrar'} gráfico de ${title}`);
  if (opening) render();
  else destroyChart(chartKey);
}

function handleGastosBarMonthsChange(input) {
  const raw = String(input.value);
  const months = Number(raw);
  const status = document.getElementById('gastos-bar-months-status');
  if (!/^\d+$/.test(raw) || !Number.isInteger(months) || months < 1 || months > 24) {
    input.value = String(gastosBarMonths);
    status.textContent = 'Cantidad inválida. Elegí un número entero entre 1 y 24.';
    return;
  }
  gastosBarMonths = months;
  if (document.getElementById('gastos-bar-body').hidden) updateGastosBarRange();
  else renderGastosBar();
}

// Las barras usan meses consecutivos hasta el mes final del período. Mes y Rango
// pueden señalar meses futuros explícitamente; el mes actual termina hoy.
function gastosBarMonthCutoff(month, rangeTo) {
  const lastDay = fijosLastDay(month);
  const periodCutoff = rangeTo && rangeTo < lastDay ? rangeTo : lastDay;
  const today = todayLocalISO();
  return month === today.slice(0, 7) && periodCutoff > today ? today : periodCutoff;
}

function renderGastosBar() {
  destroyChart('gastos-bar');
  const { months, context, to: rangeTo } = updateGastosBarRange();
  if (DATA.loadErrors.gastos || DATA.loadErrors.ingresos || DATA.loadErrors.fijos || DATA.loadErrors.resumen) {
    const canvas = document.getElementById('chart-gastos-bar');
    renderChartData(canvas, 'Gastos e ingresos mensuales',
      context,
      ['Mes', 'Gastos', 'Ingresos'], [], 'No se puede calcular la serie: faltan datos históricos.');
    showChartError('gastos-bar', canvas, 'Gráfico no disponible: faltan datos históricos.');
    return;
  }
  const monthlyRows = months.map((month) => {
    const from = month + '-01';
    const to = gastosBarMonthCutoff(month, month === months.at(-1) ? rangeTo : null);
    const gastos = applyPersonaFiltro(filterGastosPeriod(from, to));
    const variable = gastos.reduce((total, row) => total + (expenseAmount(row) ?? 0), 0);
    const fixed = fijosVigentes(DATA.fijos, to)
      .reduce((total, row) => total + (fixedAmount(row, month, personaFiltro) ?? 0), 0);
    const incomeRows = filterIngresosPeriod(from, to);
    const selectedIncome = personaFiltro.startsWith('jd') ? incomeRows.filter((row) => row.persona === P1)
      : personaFiltro.startsWith('pinki') ? incomeRows.filter((row) => row.persona === P2) : incomeRows;
    return { mes: month, total_gastos: variable + fixed,
      total_ingresos: sum(selectedIncome, 'monto') };
  });
  renderChartData(document.getElementById('chart-gastos-bar'), 'Gastos e ingresos mensuales',
    context,
    ['Mes', 'Gastos', 'Ingresos'], monthlyRows.map((row) => [row.mes, fmtARS(row.total_gastos), fmtARS(row.total_ingresos)]));
  renderChart('gastos-bar', document.getElementById('chart-gastos-bar'), {
    type: 'bar',
    data: {
      labels: monthlyRows.map((r) => shortMonth(r.mes)),
      datasets: [
        { label: 'Gastos', data: monthlyRows.map((r) => r.total_gastos), backgroundColor: '#c97d55', borderRadius: 6, maxBarThickness: 26 },
        { label: 'Ingresos', data: monthlyRows.map((r) => r.total_ingresos), backgroundColor: '#7c9a6b', borderRadius: 6, maxBarThickness: 26 },
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

function updateGastosBarRange() {
  const end = period?.to;
  const validPeriod = typeof period?.from === 'string' && typeof end === 'string' &&
    /^\d{4}-\d{2}-\d{2}$/.test(period.from) && /^\d{4}-\d{2}-\d{2}$/.test(end) &&
    period.from <= end && Number(end.slice(5, 7)) >= 1 && Number(end.slice(5, 7)) <= 12;
  const anchor = validPeriod ? end.slice(0, 7) : null;
  const months = [];
  if (anchor) {
    const [year, month] = anchor.split('-').map(Number);
    for (let offset = gastosBarMonths - 1; offset >= 0; offset--) {
      const index = year * 12 + month - 1 - offset;
      const targetYear = Math.floor(index / 12);
      if (targetYear < 1) continue;
      months.push(`${String(targetYear).padStart(4, '0')}-${String(index % 12 + 1).padStart(2, '0')}`);
    }
  }
  const shown = months.length;
  const shownCount = `${shown} ${shown === 1 ? 'mes' : 'meses'}`;
  const shownLabel = `${shown} ${shown === 1 ? 'mes mostrado' : 'meses mostrados'}`;
  const requestedLabel = gastosBarMonthsLabel();
  const title = shown === gastosBarMonths
    ? (shown === 1 ? 'Último mes' : `Últimos ${requestedLabel}`)
    : (gastosBarMonths === 1 ? `1 mes solicitado (${shownLabel})` : `Últimos ${requestedLabel} (${shownLabel})`);
  const from = shown ? months[0] + '-01' : null;
  const to = shown ? gastosBarMonthCutoff(months.at(-1), end) : null;
  const range = shown ? `Rango mostrado: ${from} a ${to}.` : 'No hay meses para mostrar en el período seleccionado.';
  const countDescription = `Se ${gastosBarMonths === 1 ? 'solicitó' : 'solicitaron'} ${requestedLabel} y se ${shown === 1 ? 'muestra' : 'muestran'} ${shownCount}. ${range}`;
  const context = `Período seleccionado: ${period?.from || 'sin inicio'} a ${period?.to || 'sin fin'}. Persona: ${PERSONA_FILTRO_LABELS[personaFiltro]}. ${countDescription}`;
  document.getElementById('gastos-bar-title').textContent = title;
  document.getElementById('gastos-bar-range').textContent = range;
  const status = document.getElementById('gastos-bar-months-status');
  if (status.textContent !== countDescription) status.textContent = countDescription;
  return { months, context, from, to };
}

// La tabla usa los mismos valores ya calculados para Chart.js. Se conserva el
// estado abierto del details cuando cambia el filtro o el período.
function renderChartData(canvas, title, context, headings, rows, emptyMessage = 'Sin datos para este filtro y período.') {
  if (!canvas?.id || typeof canvas.setAttribute !== 'function') return;
  const details = document.getElementById(`${canvas.id}-data`);
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `${title}. ${context} Datos en la tabla siguiente.`);
  details.innerHTML = `<summary>Ver datos de ${escapeHtml(title)}</summary>
    <p class="chart-data-context">${escapeHtml(context)}</p>
    ${rows.length ? `<div class="table-scroll"><table><thead><tr>${headings.map((heading) => `<th scope="col">${escapeHtml(heading)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${row.map((value, index) => `<${index === 0 ? 'th scope="row"' : 'td'}>${escapeHtml(value)}</${index === 0 ? 'th' : 'td'}>`).join('')}</tr>`).join('')}</tbody></table></div>`
    : `<p>${escapeHtml(emptyMessage)}</p>`}`;
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
  const rows = applyPersonaMonto(applyPersonaFiltro(filterGastosPeriod(period.from, period.to).filter((r) => r.categoria === cat)));
  const grouped = groupBy(rows, 'subcategoria');
  const keys = Object.keys(grouped).filter(Boolean);
  const displayKeys = keys.length ? keys : [cat];
  const data = displayKeys.map((k) => sum(keys.length ? (grouped[k] || []) : rows, 'monto'));
  const total = data.reduce((a, b) => a + b, 0) || 1;

  const btn = document.getElementById('subcat-toggle');
  btn.textContent = subcatMode === 'doughnut' ? 'barras' : 'torta';
  btn.setAttribute('aria-label', `Cambiar tipo de gráfico por subcategoría a ${btn.textContent}`);

  const canvas = document.getElementById('chart-gastos-subcat');
  renderChartData(canvas, `Gastos por subcategoría de ${cat}`,
    `Período: ${period.from} a ${period.to}. Persona: ${PERSONA_FILTRO_LABELS[personaFiltro]}.`,
    ['Subcategoría', 'Monto'], rows.length ? displayKeys.map((key, i) => [key, fmtARS(data[i])]) : []);
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
    const cmp = key === 'monto_propio'
      ? (parseFloat(va) || 0) - (parseFloat(vb) || 0)
      : String(va || '').localeCompare(String(vb || ''));
    return sortState.dir === 'asc' ? cmp : -cmp;
  });

  // Con filtro de persona activo resaltamos la columna de esa persona, pero la
  // columna "Monto" siempre muestra el TOTAL del gasto (monto_propio) -- "$ JD"
  // y "$ Pinki" ya muestran la parte de cada uno; mostrar ahí también el monto
  // recortado por el filtro duplicaba la confusión (brief F1b, hallazgo B).
  const jdHighlight = personaFiltro === 'jd' || personaFiltro === 'jd_comun';
  const pinkiHighlight = personaFiltro === 'pinki' || personaFiltro === 'pinki_comun';

  document.getElementById('tabla-body').innerHTML = sorted.map((g) => {
    const { pct1, pct2 } = getRowPct(g);
    const montoPropio = parseFloat(g.monto_propio ?? g.monto) || 0;
    const montoP1 = montoPropio * pct1 / 100;
    const montoP2 = montoPropio * pct2 / 100;
    return `
    <tr>
      <td data-label="Fecha" class="td-muted">${escapeHtml(g.fecha || '—')}</td>
      <td data-label="Categoría"><span class="pill">${iconFor(g.categoria)} ${escapeHtml(g.categoria)}</span></td>
      <td data-label="Descripción">${escapeHtml(g.descripcion_original)}</td>
      <td data-label="Monto" class="td-amount td-accent">${fmtARS(montoPropio)}</td>
      <td data-label="Importe filtrado" class="td-amount">${amountWithReference(expenseAmount({ ...g, monto: montoPropio }), montoPropio)}</td>
      <td data-label="Proporción" class="td-muted">${pct1}% ${P1} / ${pct2}% ${P2}</td>
      <td data-label="$ JD" class="td-amount${jdHighlight ? ' td-persona-jd' : ''}">${fmtARS(montoP1)}</td>
      <td data-label="$ Pinki" class="td-amount${pinkiHighlight ? ' td-persona-pinki' : ''}">${fmtARS(montoP2)}</td>
      <td data-label="Medio de pago" class="td-muted">${escapeHtml(g.medio_pago)}</td>
      <td data-label="Pagó"><span class="pill ${pillClassFor(g.pagado_por)}">${escapeHtml(g.pagado_por)}</span></td>
      <td data-label="Cuota" class="td-muted">${cuotaLabel(g)}</td>
      <td data-label="Acción">
        <button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(g.id))}" onclick="openForm('expense-edit', this.dataset.id)" aria-label="Editar la cuota ${escapeHtml(cuotaLabel(g))} del gasto ${escapeHtml(canonicalId(g.id))}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Editar</button>
        <button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(g.id))}" onclick="openForm('expense-delete', this.dataset.id)" aria-label="Dar de baja solo la cuota ${escapeHtml(cuotaLabel(g))} del gasto ${escapeHtml(canonicalId(g.id))}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Dar de baja</button>
      </td>
    </tr>`;
  }).join('');

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

// Las 4 cards con panel desplegable (fijos/cuotas/credito/deuda) comparten
// un único slot visible: abrir una cierra cualquier otra que haya quedado
// abierta, en vez de apilarse debajo de la vista.
const DETAIL_KINDS = ['fijos', 'cuotas', 'credito', 'deuda'];

function closeDetail(kind) {
  const panel = document.getElementById(kind + '-detail');
  const card = document.getElementById('card-' + kind + '-wrap');
  if (!panel || panel.hidden) return;
  panel.hidden = true;
  if (card) card.setAttribute('aria-expanded', 'false');
}

function toggleDetail(kind) {
  const panel = document.getElementById(kind + '-detail');
  const card = document.getElementById('card-' + kind + '-wrap');
  if (!panel) return;
  const opening = panel.hidden;
  for (const other of DETAIL_KINDS) {
    if (other !== kind) closeDetail(other);
  }
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
  const items = fixedMonths().flatMap((month) => fijosVigentes(DATA.fijos, fixedMonthCutoff(month))
    .filter((row) => fixedAmount(row, month, personaFiltro) !== null)
    .map((row) => ({ row, month })));
  if (!items.length) {
    inner.innerHTML = '<div class="empty-state">Sin gastos fijos activos.</div>';
    return;
  }
  const sorted = [...items].sort((a, b) => Number(b.row.monto_mensual) - Number(a.row.monto_mensual));
  const total = sorted.reduce((amount, item) => amount + fixedAmount(item.row, item.month, personaFiltro), 0);
  inner.innerHTML = `
    <table>
      <thead><tr><th>Mes</th><th>Nombre</th><th>Categoría</th><th>Periodicidad</th><th style="text-align:right">Filtrado de total</th></tr></thead>
      <tbody>
        ${sorted.map(({ row, month }) => `<tr>
          <td>${escapeHtml(month)}</td>
          <td>${escapeHtml(row.nombre)}</td>
          <td class="td-muted">${escapeHtml(row.categoria)}${row.subcategoria ? ' / ' + escapeHtml(row.subcategoria) : ''}</td>
          <td class="td-muted">${capitalize(escapeHtml(row.periodicidad))}</td>
          <td class="td-amount td-accent">${fixedAmountLabel(row, month, personaFiltro)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="4" class="td-muted">Total del período (${fixedMonths().length} mes${fixedMonths().length === 1 ? '' : 'es'})</td>
        <td class="td-amount td-accent">${fmtARS(total)}</td>
      </tr></tfoot>
    </table>
    <p class="td-muted" style="font-size:11px;margin-top:8px">Cada mes usa su versión vigente y su reparto correspondiente.</p>`;
}

function renderCuotasDetail() {
  const inner = document.getElementById('cuotas-detail-inner');
  const rows = applyPersonaFiltro(filterCuotasComprometidas(period.from, period.to))
    .sort((a, b) => (a.fecha || '').localeCompare(b.fecha || ''));
  if (!rows.length) {
    inner.innerHTML = '<div class="empty-state">Sin cuotas comprometidas en este período.</div>';
    return;
  }
  const total = rows.reduce((value, row) => value + expenseAmount(row), 0);
  inner.innerHTML = `
    <table>
      <thead><tr><th>Fecha</th><th>Descripción</th><th>Cuota</th><th style="text-align:right">Monto</th></tr></thead>
      <tbody>
        ${rows.map((r) => `<tr>
          <td class="td-muted">${r.fecha || '—'}</td>
          <td>${escapeHtml(r.descripcion_original)}</td>
          <td class="td-muted">${cuotaLabel(r)}</td>
          <td class="td-amount td-accent">${expenseAmountLabel(r)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="3" class="td-muted">Total cuotas</td>
        <td class="td-amount td-accent">${fmtARS(total)}</td>
      </tr></tfoot>
    </table>`;
}

function renderCreditoDetail() {
  const inner = document.getElementById('credito-detail-inner');
  const rows = applyPersonaFiltro(filterGastosPeriod(period.from, period.to).filter((r) => r.medio_pago === 'Crédito'));
  const fixedItems = creditFixedItems();
  if (!rows.length && !fixedItems.length) {
    inner.innerHTML = '<div class="empty-state">Sin cargos en crédito en este período.</div>';
    return;
  }
  const total = rows.reduce((value, row) => value + expenseAmount(row), 0)
    + fixedItems.reduce((value, item) => value + fixedAmount(item.row, item.month, personaFiltro), 0);
  const items = [...rows].sort((a, b) => expenseAmount(b) - expenseAmount(a));
  inner.innerHTML = `
      <table>
        <thead><tr><th>Fecha</th><th>Descripción</th><th>Categoría</th><th style="text-align:right">Monto</th></tr></thead>
        <tbody>
          ${items.map((r) => `<tr>
            <td class="td-muted">${r.fecha || '—'}</td>
            <td>${escapeHtml(r.descripcion_original)}</td>
            <td class="td-muted">${escapeHtml(r.categoria)}</td>
            <td class="td-amount td-accent">${expenseAmountLabel(r)}</td>
          </tr>`).join('')}
          ${fixedItems.map(({ row, month }) => `<tr>
            <td class="td-muted">${escapeHtml(month)}</td>
            <td>${escapeHtml(row.nombre)} · fijo</td>
            <td class="td-muted">${escapeHtml(row.categoria)}</td>
            <td class="td-amount td-accent">${fixedAmountLabel(row, month, personaFiltro)}</td>
          </tr>`).join('')}
        </tbody>
      </table><div class="credito-tarjeta-header">Total crédito · ${fmtARS(total)}</div>`;
}

// Detalle de deuda: composición gasto a gasto del saldo pendiente actual
// (mismo universo que la card — atemporal, ver getDebtRows), con de dónde
// viene cada ítem (mes, quién pagó, % de reparto) y, si hay conexión en
// vivo, la posibilidad de saldarlo ahí mismo. Si DATA.gastos no cargó, no
// hay gastos individuales para desglosar (data/deuda_pendiente.json y
// DATA.deudaPendiente son un agregado, sin eso).
function renderDeudaDetail() {
  const inner = document.getElementById('deuda-detail-inner');
  if (DATA.loadErrors.gastos) {
    inner.innerHTML = '<div class="section-error" role="alert">No se pudo cargar data/gastos.json — no se puede mostrar el detalle de la deuda.</div>';
    return;
  }
  const rows = getDebtRows().sort((a, b) => (a.fecha || '').localeCompare(b.fecha || ''));
  if (!rows.length) {
    inner.innerHTML = '<div class="empty-state">Sin deuda pendiente — todo saldado.</div>';
    return;
  }
  let debeP1 = 0, debeP2 = 0;
  const rowsData = rows.map((r) => {
    const monto = Number(r.monto) || 0;
    const { pct1, pct2 } = getRowPct(r);
    const montoP1 = monto * (pct1 / 100);
    const montoP2 = monto * (pct2 / 100);
    if (r.pagado_por === P1) debeP2 += montoP2;
    else debeP1 += montoP1;
    return { r, monto, pct1, pct2, montoP1, montoP2 };
  });
  const net = debeP2 - debeP1;
  const saldoText = Math.abs(net) < 1
    ? 'sin saldo neto'
    : net > 0 ? `${P2} debe ${fmtARS(net)} a ${P1}` : `${P1} debe ${fmtARS(Math.abs(net))} a ${P2}`;
  const canWrite = !(!liveMode || writePending || reloadPending || reloadFailed);
  inner.innerHTML = `
    <div class="fijos-actions">
      <button type="button" class="fijos-secondary" data-write-action onclick="openForm('expense-saldar-todas')" ${canWrite ? '' : 'disabled'}>Saldar todas las deudas</button>
    </div>
    <p class="td-muted" style="font-size:11px;margin:4px 0 10px">${rows.length} ítem${rows.length === 1 ? '' : 's'} sin saldar · neto ${saldoText}.
      Incluye todo gasto pagado por ${P1} o ${P2} (nunca "Común"), sin importar el mes de origen — una deuda sigue vigente hasta que se salda explícitamente.
      ${canWrite ? '' : ' Saldar requiere conexión en vivo; en modo snapshot el detalle es de solo lectura.'}</p>
    <table>
      <thead><tr>
        <th>Fecha</th><th>Descripción</th>
        <th style="text-align:right">Monto</th>
        <th style="text-align:right">% ${P1}</th><th style="text-align:right">% ${P2}</th>
        <th style="text-align:right">$ ${P1}</th><th style="text-align:right">$ ${P2}</th>
        <th></th>
      </tr></thead>
      <tbody>
        ${rowsData.map(({ r, monto, pct1, pct2, montoP1, montoP2 }) => `<tr>
          <td class="td-muted">${escapeHtml(r.fecha || '—')}</td>
          <td>${escapeHtml(r.descripcion_original || r.subcategoria || r.categoria)}
            <br><span class="td-muted" style="font-size:11px">pagó: ${escapeHtml(r.pagado_por)}</span>
          </td>
          <td class="td-amount">${fmtARS(monto)}</td>
          <td class="td-muted" style="text-align:right">${pct1}%</td>
          <td class="td-muted" style="text-align:right">${pct2}%</td>
          <td class="td-amount">${fmtARS(montoP1)}</td>
          <td class="td-amount">${fmtARS(montoP2)}</td>
          <td style="text-align:center"><button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(r.id))}" onclick="openForm('expense-saldar', this.dataset.id)" aria-label="Saldar gasto ${escapeHtml(r.descripcion_original || r.categoria)} del ${escapeHtml(r.fecha)}" ${canWrite ? '' : 'disabled'}>Saldar</button></td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td colspan="5" class="td-muted">Subtotales deuda activa</td>
        <td class="td-amount td-accent">${fmtARS(debeP1)}</td>
        <td class="td-amount td-accent">${fmtARS(debeP2)}</td>
        <td></td>
      </tr></tfoot>
    </table>`;
}

// ── VISTA INGRESOS ───────────────────────────────────────────────────────

function renderIngresosView() {
  const rows = filterIngresosPeriod(period.from, period.to);
  const selectedRows = incomePersonaFiltro === 'all' ? rows
    : rows.filter((row) => row.persona === (incomePersonaFiltro === 'jd' ? P1 : P2));
  const total = sum(rows, 'monto');
  const totalP1 = sum(rows.filter((r) => r.persona === P1), 'monto');
  const totalP2 = sum(rows.filter((r) => r.persona === P2), 'monto');

  document.getElementById('inc-total').textContent = fmtARS(total);
  document.getElementById('inc-p1').textContent = fmtARS(totalP1);
  document.getElementById('inc-p2').textContent = fmtARS(totalP2);

  const entry = getMonthProportion(period.refMonth);
  if (entry && Number.isFinite(entry.proporcion_jd) && Number.isFinite(entry.proporcion_pinki)) {
    document.getElementById('inc-proporcion').textContent =
      `${P1} ${entry.proporcion_jd.toFixed(0)}% · ${P2} ${entry.proporcion_pinki.toFixed(0)}%`;
    document.getElementById('inc-proporcion-source').textContent = mesLabel(entry.mes);
  } else {
    document.getElementById('inc-proporcion').textContent = 'No disponible';
    document.getElementById('inc-proporcion-source').textContent = 'La API no informó porcentajes verificables.';
  }

  renderIncomeLines();

  const sorted = [...selectedRows].sort((a, b) => (b.fecha || '').localeCompare(a.fecha || ''));
  document.getElementById('tabla-ingresos-body').innerHTML = sorted.length ? sorted.map((r) => `
    <tr>
      <td data-label="Fecha" class="td-muted">${escapeHtml(r.fecha || '—')}</td>
      <td data-label="Categoría"><span class="pill">${escapeHtml(r.categoria)}</span></td>
      <td data-label="Descripción">${escapeHtml(r.descripcion_original)}</td>
      <td data-label="Persona"><span class="pill ${pillClassFor(r.persona)}">${escapeHtml(r.persona)}</span></td>
      <td data-label="Monto" class="td-amount td-accent">${fmtARS(r.monto)}</td>
      <td data-label="Acción">
        <button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(r.id))}" onclick="openForm('income-edit', this.dataset.id)" aria-label="Editar ingreso ${escapeHtml(canonicalId(r.id))} de ${escapeHtml(r.persona)}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Editar</button>
        <button type="button" class="fijos-secondary table-action" data-write-action data-id="${escapeHtml(canonicalId(r.id))}" onclick="openForm('income-delete', this.dataset.id)" aria-label="Dar de baja ingreso ${escapeHtml(canonicalId(r.id))} de ${escapeHtml(r.persona)}" ${!liveMode || writePending || reloadPending || reloadFailed ? 'disabled' : ''}>Dar de baja</button>
      </td>
    </tr>`).join('') : '';
}

function renderIncomeLines() {
  destroyChart('inc-lines');
  if (document.getElementById('inc-lines-body').hidden) return;
  const months = getMonthsInPeriod(period.from, period.to);
  const rows = filterIngresosPeriod(period.from, period.to);
  const dataP1 = months.map((m) => sum(rows.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P1), 'monto'));
  const dataP2 = months.map((m) => sum(rows.filter((r) => (r.fecha || '').slice(0, 7) === m && r.persona === P2), 'monto'));
  document.getElementById('inc-lines-range-note').textContent = `${months.length} mes${months.length === 1 ? '' : 'es'} del período seleccionado`;

  const showP1 = incomePersonaFiltro === 'all' || incomePersonaFiltro === 'jd';
  const showP2 = incomePersonaFiltro === 'all' || incomePersonaFiltro === 'pinki';
  renderChartData(document.getElementById('chart-inc-lines'), 'Evolución mensual de ingresos',
    `Período: ${period.from} a ${period.to}. Persona: ${incomePersonaFiltro === 'all' ? 'Ambos' : incomePersonaFiltro === 'jd' ? P1 : P2}.`,
    ['Mes', ...(showP1 ? [P1] : []), ...(showP2 ? [P2] : [])],
    months.map((month, i) => [month, ...(showP1 ? [fmtARS(dataP1[i])] : []), ...(showP2 ? [fmtARS(dataP2[i])] : [])]));

  renderChart('inc-lines', document.getElementById('chart-inc-lines'), {
    type: 'line',
    data: {
      labels: months.map(shortMonth),
      datasets: [
        { label: P1, data: dataP1, borderColor: '#c97d55', backgroundColor: 'transparent', borderWidth: 2, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#c97d55' },
        { label: P2, data: dataP2, borderColor: '#d1a13f', backgroundColor: 'transparent', borderWidth: 2, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#d1a13f' },
      ].filter((dataset) => incomePersonaFiltro === 'all' || dataset.label === (incomePersonaFiltro === 'jd' ? P1 : P2)),
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

let supermercadoData = null;
let supermercadoLoadPromise = null;
let supermercadoLoadRevision = 0;
let supermercadoLoadPromiseRevision = 0;
let supermercadoWriteAvailable = false;
let supermercadoMutationPending = false;
let supermercadoStockQueuePromise = null;
let supermercadoStockTransaction = false;
let supermercadoDeferredRefresh = false;
const supermercadoStockQueue = [];
const supermercadoStockQueued = new Set();
let superHistoryProductId = null;
let superHistoryCursor = null;
let superHistoryRows = [];
let superHistoryRevision = 0;
let superHistoryOrigin = null;
let superHistoryPagePending = false;
const superStockDrafts = new Map();
const superNumber = (value) => new Intl.NumberFormat('es-AR', { maximumFractionDigits: 6 }).format(value);
const superQuantity = (value, unit) => `${superNumber(value)} ${unit}`;
const superOnline = () => typeof navigator === 'undefined' || navigator.onLine !== false;

function superStatus(message, error = false) {
  const node = document.getElementById('supermercado-status');
  node.textContent = message;
  node.classList.toggle('super-error', error);
}
function setSuperWriteAvailable(available) {
  supermercadoWriteAvailable = available;
  document.getElementById('supermercado-availability').textContent = available
    ? (supermercadoMutationPending ? 'Supermercado en vivo · guardando cambios.' : 'Supermercado en vivo · escrituras disponibles.')
    : 'Supermercado en solo lectura/no disponible · esperando una lectura verificada de la API.';
  document.querySelectorAll('[data-super-write]').forEach(control => { control.disabled = !available || supermercadoMutationPending; });
  refreshSuperStockStepButtons();
}
function requireSuperWrite() {
  if (supermercadoMutationPending) { superStatus('Esperá a que termine el guardado.', true); return false; }
  if (supermercadoStockQueuePromise) { superStatus('Esperá a que termine el guardado de stock. El formulario conserva tus datos.', true); return false; }
  if (supermercadoWriteAvailable && supermercadoData && superOnline()) return true;
  superStatus('Supermercado en solo lectura/no disponible. Esperá la conexión y una lectura verificada.', true);
  return false;
}
function validSuperSnapshot(data) {
  const global = data?.resumen?.global;
  const counts = ['productos', 'a_reponer', 'vacios', 'reponer', 'ok', 'porcentaje_vacio', 'porcentaje_lleno'];
  const positiveId = value => Number.isSafeInteger(value) && value > 0;
  const validCategoryId = value => value === null || positiveId(value);
  const closeNumber = (actual, expected, scale = 1) =>
    Math.abs(actual - expected) <= Math.min(4e-7, Math.max(1e-10, 4 * Number.EPSILON * scale));
  const expectedCounts = rows => {
    const total = rows.length;
    const vacios = rows.filter(row => row.stock_actual <= 0).length;
    return { productos: total, a_reponer: rows.filter(row => row.stock_deseado > row.stock_actual).length,
      vacios, reponer: rows.filter(row => row.stock_actual > 0 && row.stock_actual < row.stock_deseado).length,
      ok: rows.filter(row => row.stock_actual > 0 && row.stock_actual >= row.stock_deseado).length,
      porcentaje_vacio: total ? 100 * vacios / total : 0,
      porcentaje_lleno: total ? 100 * (total - vacios) / total : 0 };
  };
  const matchesCounts = (row, expected) => counts.every(key =>
    key.startsWith('porcentaje_') ? closeNumber(row[key], expected[key]) : row[key] === expected[key]);
  const validCounts = row => row && counts.every(key => typeof row[key] === 'number' && Number.isFinite(row[key])) &&
    ['productos', 'a_reponer', 'vacios', 'reponer', 'ok'].every(key => Number.isSafeInteger(row[key]) && row[key] >= 0) &&
    ['porcentaje_vacio', 'porcentaje_lleno'].every(key => row[key] >= 0 && row[key] <= 100) &&
    row.a_reponer <= row.productos && row.vacios + row.reponer + row.ok === row.productos;
  if (!Array.isArray(data?.categorias) || !Array.isArray(data?.productos) ||
      !Array.isArray(data?.resumen?.categorias) || !validCounts(global)) return false;
  const categories = new Map();
  for (const row of data.categorias) {
    if (!positiveId(row?.id) || categories.has(row.id) || typeof row.nombre !== 'string' || !row.nombre.trim() ||
        !Number.isSafeInteger(row.orden) || row.orden < 0) return false;
    categories.set(row.id, row);
  }
  const summary = new Map();
  for (const row of data.resumen.categorias) {
    if (!row || !Object.prototype.hasOwnProperty.call(row, 'id') || !validCategoryId(row.id) || summary.has(row.id) ||
        typeof row.nombre !== 'string' || !validCounts(row)) return false;
    if (row.id === null) {
      if (row.nombre !== 'Sin categoría' || row.orden !== null) return false;
    } else if (!categories.has(row.id) || row.nombre !== categories.get(row.id).nombre || row.orden !== categories.get(row.id).orden) return false;
    summary.set(row.id, row);
  }
  if (summary.size !== categories.size + 1 || !summary.has(null) || global.productos !== data.productos.length) return false;
  const productIds = new Set();
  const groups = new Map([...summary.keys()].map(id => [id, []]));
  for (const row of data.productos) {
    if (!positiveId(row?.id) || productIds.has(row.id) || !Object.prototype.hasOwnProperty.call(row, 'categoria_id') ||
        !validCategoryId(row.categoria_id) || !summary.has(row.categoria_id) ||
        typeof row.producto !== 'string' || !row.producto.trim() || typeof row.unidad !== 'string' || !row.unidad.trim() ||
        !['Vacío', 'Reponer', 'OK'].includes(row.estado) || !positiveId(row.version) ||
        !['stock_actual', 'stock_deseado', 'a_comprar'].every(key => typeof row[key] === 'number' && Number.isFinite(row[key]) && row[key] >= 0 && row[key] <= 1000000000) ||
        typeof row.porcentaje_faltante !== 'number' || !Number.isFinite(row.porcentaje_faltante) ||
        row.porcentaje_faltante < 0 || row.porcentaje_faltante > 100) return false;
    const missing = Math.max(0, row.stock_deseado - row.stock_actual);
    const expectedState = row.stock_actual <= 0 ? 'Vacío' : row.stock_actual < row.stock_deseado ? 'Reponer' : 'OK';
    const expectedPercent = row.stock_deseado > 0 ? missing / row.stock_deseado * 100 : 0;
    if (!closeNumber(row.a_comprar, missing, Math.max(1, row.stock_actual, row.stock_deseado)) ||
        !closeNumber(row.porcentaje_faltante, expectedPercent) || row.estado !== expectedState) return false;
    productIds.add(row.id);
    groups.get(row.categoria_id).push(row);
  }
  return matchesCounts(global, expectedCounts(data.productos)) &&
    [...summary].every(([id, row]) => matchesCounts(row, expectedCounts(groups.get(id))));
}
async function superRequest(method, path, payload) {
  const response = await fetch(path, { method, credentials: 'same-origin',
    ...(payload === undefined ? {} : { headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) }) });
  let body;
  try { body = await response.json(); } catch (error) { if (response.ok) throw error; }
  if (!response.ok) {
    const error = new Error(body?.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return body;
}
function reconcileSuperDrafts(data) {
  for (const [id, draft] of superStockDrafts) {
    const row = data.productos.find(item => item.id === id);
    if (!row) {
      clearTimeout(draft.timer);
      draft.timer = null;
      if (!draft.dirty && !draft.saving && !draft.conflict) superStockDrafts.delete(id);
      else { draft.conflict = true; draft.server = null; }
      continue;
    }
    if (draft.conflict) { draft.server = row; continue; }
    if (draft.dirty && !draft.saving && row.version !== draft.version) {
      draft.conflict = true;
      draft.server = row;
      clearTimeout(draft.timer);
      draft.timer = null;
    } else if (!draft.dirty && !draft.saving) {
      clearTimeout(draft.timer);
      draft.timer = null;
      if (draft.version !== row.version || Number(draft.value) !== row.stock_actual) draft.unchanged = false;
      draft.value = String(row.stock_actual);
      draft.version = row.version;
      draft.server = row;
    }
  }
}
function loadSupermercado() {
  const revision = ++supermercadoLoadRevision;
  if (!superOnline()) {
    setSuperWriteAvailable(false);
    superStatus('Sin conexión. Stock conservado en pantalla; no actualizado.', true);
    return Promise.resolve(false);
  }
  superStatus('Comprobando stock…');
  const promise = (async () => {
    try {
      const data = await fetchJSON('/api/supermercado');
      if (!validSuperSnapshot(data)) throw new Error('Respuesta de stock inválida');
      if (revision !== supermercadoLoadRevision) return false;
      reconcileSuperDrafts(data);
      supermercadoData = data;
      renderSupermercadoList();
      setSuperWriteAvailable(true);
      superStatus('Stock verificado con la API.');
      return true;
    } catch (error) {
      if (revision !== supermercadoLoadRevision) return false;
      setSuperWriteAvailable(false);
      if (!supermercadoData) document.getElementById('supermercado-content').textContent = 'No se pudo cargar el stock. Se reintentará al abrir la pestaña o recuperar la conexión.';
      superStatus(`No se pudo verificar el stock: ${error.message}`, true);
      return false;
    }
  })();
  supermercadoLoadPromise = promise;
  supermercadoLoadPromiseRevision = revision;
  promise.then(() => { if (supermercadoLoadPromise === promise) supermercadoLoadPromise = null; });
  return promise;
}
function ensureComprasLoaded(force = false) {
  if (supermercadoStockTransaction || supermercadoMutationPending) {
    if (supermercadoLoadPromise && supermercadoLoadPromiseRevision === supermercadoLoadRevision) return supermercadoLoadPromise;
    supermercadoDeferredRefresh = true;
    return Promise.resolve(false);
  }
  if (supermercadoLoadPromise) return supermercadoLoadPromiseRevision === supermercadoLoadRevision
    ? supermercadoLoadPromise : loadSupermercado();
  if (supermercadoData && supermercadoWriteAvailable && !force) return Promise.resolve(true);
  return loadSupermercado();
}
function superCoverage(row) {
  if (row.stock_deseado === 0) return { percent: null, text: row.stock_actual > 0 ? `Deseado 0 · hay ${superQuantity(row.stock_actual, row.unidad)}; excedente` : 'Deseado 0 · sin faltante' };
  const percent = Math.min(100, Math.max(0, row.stock_actual / row.stock_deseado * 100));
  const detail = row.a_comprar > 0 ? `Faltan ${superQuantity(row.a_comprar, row.unidad)}` : row.stock_actual > row.stock_deseado ? `Excedente ${superQuantity(row.stock_actual - row.stock_deseado, row.unidad)}` : 'Objetivo alcanzado';
  return { percent, text: `${superNumber(Math.round(percent))}% de cobertura · ${detail}` };
}
function superCountChart(counts, label, rows = []) {
  if (!counts.productos) return '<p class="empty-state">Sin productos para graficar.</p>';
  const eligible = rows.filter(row => row.stock_deseado > 0);
  const average = eligible.length ? Math.round(eligible.reduce((total, row) => total + superCoverage(row).percent, 0) / eligible.length) : null;
  return `<div class="super-count-chart" role="img" aria-label="${escapeHtml(label)}: ${counts.vacios} vacíos, ${counts.reponer} para reponer, ${counts.ok} OK; ${counts.a_reponer} a comprar; ${average === null ? 'cobertura no aplicable' : `cobertura promedio ${average}%`}">
    ${[['vacios', 'Vacío'], ['reponer', 'Reponer'], ['ok', 'OK']].map(([key, title]) => `<div class="super-count-row"><span>${title}: ${counts[key]}</span><div class="super-count-track"><span class="super-count-fill super-${key}" style="width:${counts[key] / counts.productos * 100}%"></span></div></div>`).join('')}
    <p>${counts.a_reponer} de ${counts.productos} productos a comprar. ${average === null ? 'Cobertura no aplicable: ningún producto tiene deseado mayor que 0.' : `Cobertura promedio por producto: ${average}% (${eligible.length} con deseado mayor que 0, cada cobertura limitada al 100%).`} No se suman cantidades de distintas unidades.</p></div>`;
}
function superStockStatus(id) {
  const draft = superStockDrafts.get(id);
  if (!draft) return '<span class="super-save-note">Se guarda al salir del campo o tras una pausa.</span>';
  const row = supermercadoData?.productos.find(item => item.id === id);
  if (draft.conflict) return `<span class="super-save-error">${draft.conflictMessage ? escapeHtml(draft.conflictMessage) + ' ' : ''}Conflicto: servidor ${draft.server ? escapeHtml(superQuantity(draft.server.stock_actual, draft.server.unidad)) : 'sin lectura actual disponible'}. Tu borrador: ${escapeHtml(draft.value)}.</span> <button type="button" onclick="retrySuperStock(${id})">Reintentar con datos actualizados</button> <button type="button" onclick="discardSuperStock(${id})">Descartar borrador</button>`;
  if (draft.saving) return '<span>Guardando…</span>';
  if (draft.error) return `<span class="super-save-error">${escapeHtml(draft.error)}</span> <button type="button" onclick="retrySuperStock(${id})">Reintentar</button>`;
  if (draft.dirty) return '<span>Borrador sin guardar</span>';
  if (draft.unchanged) return '<span>Sin cambios · stock verificado</span>';
  return `<span>Guardado y verificado: ${escapeHtml(superQuantity(row?.stock_actual ?? draft.value, row?.unidad || ''))}</span>`;
}
function updateSuperStockStatus(id) {
  const target = document.getElementById(`super-stock-status-${id}`);
  const status = superStockStatus(id);
  if (target && target.innerHTML !== status) target.innerHTML = status;
}
function reconcileSupermercadoContent(content, markup) {
  const template = document.createElement('template');
  template.innerHTML = markup;
  for (const node of [...content.childNodes]) if (node.nodeType === 3) node.remove();
  const currentSections = new Map([...content.querySelectorAll('.super-group')].map(node => [node.dataset.superCategoryId, node]));
  const currentArticles = new Map([...content.querySelectorAll('.super-item')].map(node => [node.dataset.superProductId, node]));
  const currentOrphans = new Map([...content.querySelectorAll('.super-orphan')].map(node => [node.dataset.superOrphanId, node]));
  const desiredNodes = [...template.content.children];
  const desiredGroups = [];
  const active = document.activeElement;
  const caret = active?.selectionStart;

  for (const desiredSection of desiredNodes) {
    if (desiredSection.classList.contains('super-orphan')) {
      const orphan = currentOrphans.get(desiredSection.dataset.superOrphanId);
      if (orphan) {
        if (orphan.innerHTML !== desiredSection.innerHTML) orphan.innerHTML = desiredSection.innerHTML;
        desiredNodes[desiredNodes.indexOf(desiredSection)] = orphan;
      }
      continue;
    }
    if (!desiredSection.classList.contains('super-group')) continue;
    const section = currentSections.get(desiredSection.dataset.superCategoryId) || desiredSection;
    const header = section.querySelector('.super-group-head');
    const nextHeader = desiredSection.querySelector('.super-group-head');
    if (header !== nextHeader && header.innerHTML !== nextHeader.innerHTML) header.innerHTML = nextHeader.innerHTML;
    const items = section.querySelector('.super-group-items');
    const wanted = [...desiredSection.querySelectorAll('.super-item')];
    const ids = new Set();
    wanted.forEach((desiredArticle, index) => {
      const id = desiredArticle.dataset.superProductId;
      ids.add(id);
      const article = currentArticles.get(id) || desiredArticle;
      if (article !== desiredArticle) {
        if (desiredArticle.parentNode === items) desiredArticle.remove();
        const main = article.querySelector('.super-item-main');
        const nextMain = desiredArticle.querySelector('.super-item-main');
        if (main.innerHTML !== nextMain.innerHTML) main.innerHTML = nextMain.innerHTML;
        const label = article.querySelector('.super-stock-control label');
        const nextLabel = desiredArticle.querySelector('.super-stock-control label');
        if (label.innerHTML !== nextLabel.innerHTML) label.innerHTML = nextLabel.innerHTML;
        const stepButtons = article.querySelectorAll('[data-super-step]');
        const nextStepButtons = desiredArticle.querySelectorAll('[data-super-step]');
        stepButtons.forEach((button, stepIndex) => {
          const nextLabelText = nextStepButtons[stepIndex]?.getAttribute('aria-label');
          if (nextLabelText && button.getAttribute('aria-label') !== nextLabelText) button.setAttribute('aria-label', nextLabelText);
        });
        const input = article.querySelector('input');
        const draft = superStockDrafts.get(Number(id));
        if (!draft?.dirty && !draft?.saving && input.value !== desiredArticle.querySelector('input').value) {
          input.value = desiredArticle.querySelector('input').value;
        }
        updateSuperStockStatus(Number(id));
      }
      if (items.children[index] !== article) items.insertBefore(article, items.children[index] || null);
    });
    desiredGroups.push({ section, items, ids });
    const index = desiredNodes.indexOf(desiredSection);
    desiredNodes[index] = section;
  }

  for (const { items, ids } of desiredGroups) {
    for (const article of [...items.children]) {
      if (!ids.has(article.dataset.superProductId)) article.remove();
    }
  }
  desiredNodes.forEach((node, index) => {
    if (content.children[index] !== node) content.insertBefore(node, content.children[index] || null);
  });
  for (const node of [...content.children].slice(desiredNodes.length)) node.remove();
  if (active?.isConnected && document.activeElement !== active) {
    active.focus({ preventScroll: true });
    if (caret !== null && caret !== undefined && active.setSelectionRange) {
      try { active.setSelectionRange(caret, caret); } catch (_) { /* Number inputs do not expose a text selection. */ }
    }
  }
}
function renderSupermercadoList() {
  if (!supermercadoData) return;
  const { categorias, productos, resumen } = supermercadoData;
  const global = resumen.global;
  document.getElementById('supermercado-summary').textContent = `${global.productos} productos · ${global.a_reponer} a comprar · ${global.vacios} vacíos · ${global.reponer} reponer · ${global.ok} OK`;
  document.getElementById('supermercado-general-chart').innerHTML = superCountChart(global, 'Estado general', productos);
  document.getElementById('supermercado-category-summary').innerHTML = resumen.categorias.filter(cat => cat.productos).map(cat =>
    `<div><strong>${escapeHtml(cat.nombre)}</strong>${superCountChart(cat, cat.nombre, productos.filter(row => row.categoria_id === cat.id))}</div>`).join('') || '<p class="empty-state">Todavía no hay productos por categoría.</p>';
  const categoriesMarkup = categorias.length ? categorias.map(cat => `
    <div class="super-category"><span>${escapeHtml(cat.nombre)} · orden ${cat.orden}</span>
    <button type="button" data-super-write onclick="editSuperCategory(${cat.id})" aria-label="Editar categoría ${escapeHtml(cat.nombre)}">Editar</button>
    <button type="button" data-super-write onclick="deleteSuperCategory(${cat.id})" aria-label="Dar de baja categoría ${escapeHtml(cat.nombre)}">Dar de baja</button></div>`).join('') : '<p class="empty-state">Todavía no hay categorías.</p>';
  const categoryList = document.getElementById('supermercado-categories');
  if (categoryList.innerHTML !== categoriesMarkup) categoryList.innerHTML = categoriesMarkup;
  const select = document.getElementById('supermercado-category-select');
  const previous = select.value;
  const optionsMarkup = '<option value="">Sin categoría</option>' + categorias.map(cat => `<option value="${cat.id}">${escapeHtml(cat.nombre)}</option>`).join('');
  if (select.innerHTML !== optionsMarkup) { select.innerHTML = optionsMarkup; select.value = previous; }
  const query = document.getElementById('supermercado-search').value.trim().toLocaleLowerCase('es-AR');
  const shown = productos.filter(row => row.producto.toLocaleLowerCase('es-AR').includes(query));
  const content = document.getElementById('supermercado-content');
  const orphanDrafts = [...superStockDrafts].filter(([id, draft]) => draft.dirty && !productos.some(row => row.id === id)).map(([id, draft]) => `<p class="super-orphan" data-super-orphan-id="${id}">El producto #${id} ya no está disponible. Borrador conservado: ${escapeHtml(draft.value)}. <button type="button" onclick="discardSuperStock(${id})">Descartar borrador</button></p>`).join('');
  if (!productos.length) { content.innerHTML = orphanDrafts + '<p class="empty-state">No hay productos. Abrí «Administrar productos y categorías» para cargar el primero.</p>'; return; }
  if (!shown.length) { content.innerHTML = orphanDrafts + '<p class="empty-state">No hay productos que coincidan.</p>'; return; }
  const groups = resumen.categorias.filter(cat => shown.some(row => row.categoria_id === cat.id));
  if (!groups.length && shown.length) groups.push({ id: null, nombre: 'Sin categoría' });
  const markup = orphanDrafts + groups.map(cat => {
    const rows = shown.filter(row => row.categoria_id === cat.id);
    return `<section class="super-group" data-super-category-id="${cat.id ?? 'none'}" aria-labelledby="super-group-${cat.id ?? 'none'}"><header class="super-group-head"><h4 id="super-group-${cat.id ?? 'none'}">${escapeHtml(cat.nombre)}</h4><span>${rows.length} producto${rows.length === 1 ? '' : 's'} · ${rows.filter(row => row.a_comprar > 0).length} a comprar</span></header>
      <div class="super-group-items">${rows.map(row => {
        const coverage = superCoverage(row);
        const draft = superStockDrafts.get(row.id);
        return `<article class="super-item" data-super-product-id="${row.id}"><div class="super-item-main"><strong>${escapeHtml(row.producto)}</strong><span class="super-badge super-badge-${row.estado === 'Vacío' ? 'empty' : row.estado === 'Reponer' ? 'low' : 'ok'}">${escapeHtml(row.estado)}</span><span>Deseado: ${escapeHtml(superQuantity(row.stock_deseado, row.unidad))} · Actual: ${escapeHtml(superQuantity(row.stock_actual, row.unidad))}</span><span>${escapeHtml(coverage.text)}</span>${coverage.percent === null ? '' : `<div class="super-coverage" role="meter" aria-label="Cobertura de ${escapeHtml(row.producto)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(coverage.percent)}"><span style="width:${coverage.percent}%"></span></div>`}</div>
        <div class="super-stock-control"><label for="super-stock-${row.id}">Stock actual (${escapeHtml(row.unidad)})</label><div class="super-step-row"><input type="number" data-super-write min="0" max="1000000000" step="any" value="${escapeHtml(draft?.value ?? row.stock_actual)}" id="super-stock-${row.id}" aria-describedby="super-stock-status-${row.id}" oninput="handleSuperStockInput(event, ${row.id})" onblur="handleSuperStockBlur(${row.id}, event)" onkeydown="handleSuperStockKeydown(event, ${row.id})" ${supermercadoWriteAvailable && !supermercadoMutationPending ? '' : 'disabled'}><div class="super-step-actions"><button type="button" data-super-write data-super-step="-1" data-super-stock-target="super-stock-${row.id}" aria-label="Restar 1 al stock actual de ${escapeHtml(row.producto)}" onclick="handleSuperStockStep(${row.id}, -1)">−</button><button type="button" data-super-write data-super-step="1" data-super-stock-target="super-stock-${row.id}" aria-label="Sumar 1 al stock actual de ${escapeHtml(row.producto)}" onclick="handleSuperStockStep(${row.id}, 1)">+</button></div></div><div id="super-stock-status-${row.id}" class="super-stock-status" role="status" aria-live="polite">${superStockStatus(row.id)}</div></div>
        <div class="super-item-actions"><button type="button" data-super-write onclick="editSuperProduct(${row.id})">Editar</button><button type="button" id="super-history-button-${row.id}" onclick="showSuperHistory(${row.id}, null, this)">Historial</button><button type="button" data-super-write onclick="deleteSuperProduct(${row.id})">Dar de baja</button></div></article>`;
      }).join('')}</div></section>`;
  }).join('');
  if (document.createElement && content.querySelectorAll) reconcileSupermercadoContent(content, markup);
  else content.innerHTML = markup;
  setSuperWriteAvailable(supermercadoWriteAvailable);
}
async function superMutate(method, path, payload, success) {
  if (!requireSuperWrite()) return false;
  supermercadoMutationPending = true;
  setSuperWriteAvailable(supermercadoWriteAvailable);
  try {
    while (supermercadoLoadPromise) await supermercadoLoadPromise;
    if (!supermercadoWriteAvailable) { superStatus('No se pudo verificar el stock. El formulario conserva tus datos.', true); return false; }
    superStatus('Guardando…');
    await superRequest(method, path, payload);
    supermercadoDeferredRefresh = false;
    const loaded = await loadSupermercado();
    if (!loaded) { superStatus('Se guardó, pero no se pudo verificar la lectura. Revisá la conexión.', true); return true; }
    superStatus(success);
    return true;
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      ++supermercadoLoadRevision;
      setSuperWriteAvailable(false);
      superStatus(`${error.message} Supermercado en solo lectura/no disponible.`, true);
      return false;
    }
    if (error.status === 409) {
      supermercadoDeferredRefresh = false;
      await loadSupermercado();
      superStatus(`${error.message} Revisá los datos recargados antes de volver a guardar.`, true);
    } else superStatus(error.message, true);
    return false;
  } finally {
    supermercadoMutationPending = false;
    setSuperWriteAvailable(supermercadoWriteAvailable);
    if (supermercadoStockQueue.length) startSuperStockQueue();
    else if (supermercadoDeferredRefresh) { supermercadoDeferredRefresh = false; ensureComprasLoaded(true); }
  }
}
function editSuperCategory(id) {
  if (!requireSuperWrite()) return;
  const row = supermercadoData?.categorias.find(item => item.id === id);
  if (!row) return;
  document.getElementById('supermercado-admin').open = true;
  document.getElementById('supermercado-category-editor').open = true;
  const form = document.getElementById('supermercado-category-form');
  form.elements.id.value = row.id;
  form.elements.nombre.value = row.nombre;
  form.elements.orden.value = row.orden;
  form.elements.nombre.focus();
}
function editSuperProduct(id) {
  if (!requireSuperWrite()) return;
  const row = supermercadoData?.productos.find(item => item.id === id);
  if (!row) return;
  document.getElementById('supermercado-admin').open = true;
  document.getElementById('supermercado-product-editor').open = true;
  const form = document.getElementById('supermercado-product-form');
  for (const key of ['id', 'producto', 'unidad', 'stock_deseado', 'stock_actual']) form.elements[key].value = row[key];
  form.elements.categoria_id.value = row.categoria_id ?? '';
  form.dataset.version = String(row.version);
  refreshSuperStockStepButtons();
  form.elements.producto.focus();
}
async function deleteSuperCategory(id) {
  if (!requireSuperWrite()) return;
  const row = supermercadoData?.categorias.find(item => item.id === id);
  if (!row || !confirm(`¿Dar de baja la categoría ${row.nombre}? Sus productos quedarán sin categoría.`)) return;
  await superMutate('DELETE', `/api/supermercado/categorias/${id}`, undefined, 'Categoría dada de baja.');
}
async function deleteSuperProduct(id) {
  if (!requireSuperWrite()) return;
  const row = supermercadoData?.productos.find(item => item.id === id);
  if (!row || !confirm(`¿Dar de baja el producto ${row.producto}? Quedará en el historial.`)) return;
  await superMutate('DELETE', `/api/supermercado/productos/${id}`, { expected_version: row.version }, 'Producto dado de baja.');
}
function validSuperStock(raw) {
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(raw)) return false;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && value <= 1000000000;
}
function stepSuperStock(raw, direction) {
  if (!validSuperStock(raw) || ![-1, 1].includes(direction)) return null;
  const [whole, fraction = ''] = raw.split('.');
  const scale = 1000000n;
  const scaled = BigInt(whole) * scale + BigInt(fraction.padEnd(6, '0') || '0');
  const next = scaled + BigInt(direction) * scale;
  if (next < 0n || next > 1000000000n * scale) return null;
  const nextWhole = String(next / scale);
  return fraction ? `${nextWhole}.${String(next % scale).padStart(6, '0').slice(0, fraction.length)}` : nextWhole;
}
function refreshSuperStockStepButtons() {
  document.querySelectorAll('[data-super-step]').forEach(button => {
    if (!button.dataset || button.dataset.superStep === undefined) return;
    const input = document.getElementById(button.dataset.superStockTarget);
    button.disabled = !supermercadoWriteAvailable || supermercadoMutationPending || !input || input.disabled ||
      stepSuperStock(input.value, Number(button.dataset.superStep)) === null;
  });
}
function handleSuperStockStep(id, direction) {
  const input = document.getElementById(`super-stock-${id}`);
  if (!input || input.disabled || !supermercadoWriteAvailable || supermercadoMutationPending) return;
  const next = stepSuperStock(input.value, direction);
  if (next === null) return;
  input.value = next;
  handleSuperStockInput({ target: input }, id);
}
function handleSuperStockInput(event, id) {
  const row = supermercadoData?.productos.find(item => item.id === id);
  if (!row) return;
  const value = event.target.value;
  let draft = superStockDrafts.get(id);
  if (!draft) { draft = { value, version: row.version, dirty: true, saving: false, conflict: false, error: '', timer: null }; superStockDrafts.set(id, draft); }
  draft.value = value;
  draft.dirty = true;
  draft.unchanged = false;
  clearTimeout(draft.timer);
  if (!validSuperStock(value)) draft.error = 'Ingresá una cantidad válida (0 a 1.000.000.000, hasta 6 decimales).';
  else if (draft.retryRequired) {
    if (!draft.error || draft.error.startsWith('Ingresá una cantidad válida')) draft.error = 'Guardado pausado. Reintentá explícitamente.';
  } else if (!draft.conflict) {
    draft.error = '';
    draft.timer = setTimeout(() => saveSuperStock(id), 900);
  }
  updateSuperStockStatus(id);
  refreshSuperStockStepButtons();
}
function handleSuperStockBlur(id, event) {
  if (event?.relatedTarget?.dataset?.superStockTarget === `super-stock-${id}`) return;
  const draft = superStockDrafts.get(id);
  if (draft && validSuperStock(draft.value) && !draft.conflict) saveSuperStock(id);
  if (!draft || !draft.dirty) renderSupermercadoList();
}
function handleSuperStockKeydown(event, id) {
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
    event.preventDefault();
    handleSuperStockStep(id, event.key === 'ArrowUp' ? 1 : -1);
    return;
  }
  if (event.key !== 'Enter') return;
  event.preventDefault();
  event.target.blur();
  handleSuperStockBlur(id);
}
function handleSuperFormStockStep(input, direction) {
  if (input.disabled || !supermercadoWriteAvailable || supermercadoMutationPending) return;
  const next = stepSuperStock(input.value, direction);
  if (next === null) return;
  input.value = next;
  refreshSuperStockStepButtons();
}
function configureSuperProductStockControls() {
  const form = document.getElementById('supermercado-product-form');
  if (!form?.elements) return;
  for (const [name, labelText] of [['stock_deseado', 'deseado'], ['stock_actual', 'actual']]) {
    const input = form.elements[name];
    if (!input) continue;
    input.step = 'any';
    input.id = `super-form-${name}`;
    input.addEventListener?.('keydown', event => {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
      event.preventDefault();
      handleSuperFormStockStep(input, event.key === 'ArrowUp' ? 1 : -1);
    });
    input.addEventListener?.('input', refreshSuperStockStepButtons);
    const label = input.closest?.('label');
    if (!label || !document.createElement) continue;
    const group = document.createElement('div');
    group.className = 'super-form-stock-control';
    label.before(group);
    group.appendChild(label);
    const actions = document.createElement('div');
    actions.className = 'super-step-actions';
    for (const [direction, text, action] of [[-1, '−', 'Restar'], [1, '+', 'Sumar']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = text;
      button.setAttribute('data-super-write', '');
      button.dataset.superStep = String(direction);
      button.dataset.superStockTarget = input.id;
      button.setAttribute('aria-label', `${action} 1 al stock ${labelText}`);
      button.addEventListener('click', () => handleSuperFormStockStep(input, direction));
      actions.appendChild(button);
    }
    group.appendChild(actions);
  }
  refreshSuperStockStepButtons();
}
function enqueueSuperStock(id) {
  if (!supermercadoStockQueued.has(id)) {
    supermercadoStockQueued.add(id);
    supermercadoStockQueue.push(id);
  }
}
function startSuperStockQueue() {
  if (supermercadoStockQueuePromise || supermercadoMutationPending || !supermercadoStockQueue.length) return supermercadoStockQueuePromise;
  const pending = drainSuperStockQueue();
  supermercadoStockQueuePromise = pending;
  pending.then(() => {
    if (supermercadoStockQueuePromise === pending) supermercadoStockQueuePromise = null;
    if (supermercadoStockQueue.length) startSuperStockQueue();
  }, error => {
    if (supermercadoStockQueuePromise === pending) supermercadoStockQueuePromise = null;
    supermercadoStockQueue.length = 0;
    supermercadoStockQueued.clear();
    supermercadoStockTransaction = false;
    for (const [id, draft] of superStockDrafts) {
      if (!draft.dirty || draft.conflict) continue;
      clearTimeout(draft.timer);
      draft.saving = false;
      draft.retryRequired = true;
      draft.error = 'Guardado interrumpido. Reintentá explícitamente.';
      updateSuperStockStatus(id);
    }
    superStatus(`No se pudo completar la cola de stock: ${error.message}`, true);
  });
  return pending;
}
function saveSuperStock(id) {
  const draft = superStockDrafts.get(id);
  if (!draft || !draft.dirty || draft.conflict || draft.error || !validSuperStock(draft.value)) return Promise.resolve(false);
  clearTimeout(draft.timer);
  if (!supermercadoWriteAvailable || !superOnline()) {
    draft.retryRequired = true;
    draft.error = 'Sin conexión verificada. Reintentá cuando vuelva.';
    updateSuperStockStatus(id);
    return Promise.resolve(false);
  }
  if (draft.saving) return supermercadoStockQueuePromise || Promise.resolve(false);
  enqueueSuperStock(id);
  return startSuperStockQueue() || Promise.resolve(false);
}
async function drainSuperStockQueue() {
  let completed = true;
  while (supermercadoStockQueue.length) {
    const id = supermercadoStockQueue.shift();
    supermercadoStockQueued.delete(id);
    if (await writeSuperStock(id) === false) {
      completed = false;
      supermercadoStockQueue.length = 0;
      supermercadoStockQueued.clear();
      for (const [pendingId, draft] of superStockDrafts) {
        if (!draft.dirty || draft.saving || draft.conflict || draft.error) continue;
        clearTimeout(draft.timer);
        draft.retryRequired = true;
        draft.error = 'Guardado pausado por un error anterior. Reintentá explícitamente.';
        updateSuperStockStatus(pendingId);
      }
      break;
    }
  }
  if (supermercadoDeferredRefresh) {
    supermercadoDeferredRefresh = false;
    await loadSupermercado();
  }
  return completed;
}
async function writeSuperStock(id) {
  const draft = superStockDrafts.get(id);
  if (!draft || !draft.dirty || draft.conflict || draft.error || !validSuperStock(draft.value)) return true;
  while (supermercadoLoadPromise) await supermercadoLoadPromise;
  if (!supermercadoWriteAvailable || !superOnline()) {
    draft.retryRequired = true;
    draft.error = 'Sin conexión verificada. Reintentá cuando vuelva.';
    updateSuperStockStatus(id);
    return false;
  }
  const row = supermercadoData.productos.find(item => item.id === id);
  if (!row) { draft.conflict = true; draft.server = null; updateSuperStockStatus(id); return false; }
  if (row.version !== draft.version) { draft.conflict = true; draft.server = row; updateSuperStockStatus(id); return false; }
  if (Number(draft.value) === row.stock_actual) { draft.dirty = false; draft.unchanged = true; draft.error = ''; updateSuperStockStatus(id); return true; }
  const sentValue = draft.value;
  draft.saving = true;
  supermercadoStockTransaction = true;
  clearTimeout(draft.timer);
  updateSuperStockStatus(id);
  try {
    const response = await superRequest('PATCH', `/api/supermercado/productos/${id}/stock`, { stock_actual: Number(sentValue), expected_version: draft.version });
    if (response?.registro?.version !== draft.version + 1) throw new Error('Respuesta de guardado inválida.');
    supermercadoDeferredRefresh = false;
    const loaded = await loadSupermercado();
    const verified = loaded && supermercadoData?.productos.find(item => item.id === id);
    if (!verified) throw new Error('El guardado no se pudo verificar. Recargá el stock antes de decidir.');
    if (verified.version !== response.registro.version || verified.stock_actual !== Number(sentValue)) {
      draft.conflict = true;
      draft.server = verified;
      draft.conflictMessage = 'El servidor aceptó tu guardado, pero el stock cambió después. Revisá el valor actual antes de decidir.';
      return false;
    }
    draft.version = verified.version;
    if (draft.value === sentValue) draft.error = '';
    draft.unchanged = false;
    draft.dirty = draft.value !== sentValue;
    if (draft.dirty && !draft.error && validSuperStock(draft.value)) {
      clearTimeout(draft.timer);
      enqueueSuperStock(id);
    }
  } catch (error) {
    draft.dirty = true;
    if (error.status === 401 || error.status === 403) { ++supermercadoLoadRevision; setSuperWriteAvailable(false); }
    if (error.status === 409) {
      draft.conflict = true;
      supermercadoDeferredRefresh = false;
      const refreshed = await loadSupermercado();
      draft.server = refreshed ? (supermercadoData?.productos.find(item => item.id === id) || null) : null;
      draft.error = '';
    } else if (error.message.startsWith('El guardado no se pudo verificar')) {
      draft.conflict = true;
      draft.server = null;
      draft.conflictMessage = error.message;
    } else {
      draft.retryRequired = true;
      draft.error = error.message;
    }
    return false;
  } finally {
    draft.saving = false;
    supermercadoStockTransaction = false;
    updateSuperStockStatus(id);
    renderSupermercadoList();
  }
  return true;
}
function retrySuperStock(id) {
  const draft = superStockDrafts.get(id);
  const row = supermercadoData?.productos.find(item => item.id === id);
  if (!draft || !row || !validSuperStock(draft.value) || !requireSuperWrite()) return;
  draft.version = row.version;
  draft.conflict = false;
  draft.conflictMessage = '';
  draft.retryRequired = false;
  draft.error = '';
  saveSuperStock(id);
}
function discardSuperStock(id) {
  const draft = superStockDrafts.get(id);
  if (!draft || draft.saving) return;
  clearTimeout(draft.timer);
  superStockDrafts.delete(id);
  const row = supermercadoData?.productos.find(item => item.id === id);
  const input = document.getElementById(`super-stock-${id}`);
  if (input && row) input.value = row.stock_actual;
  updateSuperStockStatus(id);
  renderSupermercadoList();
  document.getElementById(`super-stock-${id}`)?.focus?.();
}
function superHistoryLabel(value) {
  return value === null || value === undefined ? '—' : String(value);
}
function superHistoryDate(raw) {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return `${new Intl.DateTimeFormat('es-AR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(date)} UTC`;
}
function superHistoryCategoryLabel(snapshot) {
  const id = snapshot?.categoria_id;
  if (id === null) return 'Sin categoría';
  if (!Number.isSafeInteger(id) || id <= 0) return 'Categoría no registrada';
  if (typeof snapshot.categoria_nombre === 'string' && snapshot.categoria_nombre.trim()) {
    return `Categoría #${id} (${snapshot.categoria_nombre}; nombre registrado en auditoría)`;
  }
  const current = supermercadoData?.categorias.find(cat => cat.id === id);
  return current ? `Categoría #${id} (nombre actual: ${current.nombre}; nombre histórico no registrado)`
    : `Categoría #${id} (no disponible hoy; nombre histórico no registrado)`;
}
function superHistoryChart(events, unit) {
  const points = [...events].sort((a, b) => a.fecha_utc.localeCompare(b.fecha_utc) || a.id - b.id)
    .filter(event => event.despues && event.despues.stock_actual != null && event.despues.stock_deseado != null && (!unit || event.despues.unidad === unit))
    .map(event => ({ id: event.id, date: event.fecha_utc, actual: Number(event.despues.stock_actual), desired: Number(event.despues.stock_deseado) }))
    .filter(point => Number.isFinite(point.actual) && Number.isFinite(point.desired));
  if (!points.length) return `<p class="empty-state">No hay puntos de stock auditados con unidad ${escapeHtml(unit || 'conocida')} para graficar. Los cambios de unidad figuran en la lista.</p>`;
  const max = Math.max(1, ...points.flatMap(point => [point.actual, point.desired]));
  const x = i => points.length === 1 ? 50 : 5 + i * 90 / (points.length - 1);
  const y = value => 90 - value / max * 80;
  const line = field => points.map((point, i) => `${x(i)},${y(point[field])}`).join(' ');
  const first = points[0], last = points.at(-1);
  const summary = `${points.length} ${points.length === 1 ? 'punto auditado' : 'puntos auditados'} con unidad ${unit || 'sin especificar'}, de ${superHistoryDate(first.date)} a ${superHistoryDate(last.date)}. Stock actual ${superQuantity(last.actual, unit)} y deseado ${superQuantity(last.desired, unit)} en el último evento.`;
  return `<figure class="super-timeline"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(summary)}"><polyline points="${line('desired')}" class="super-line-desired"/><polyline points="${line('actual')}" class="super-line-actual"/>${points.map((point, i) => `<circle cx="${x(i)}" cy="${y(point.actual)}" r="1.5"/>`).join('')}</svg><figcaption><strong>Stock actual</strong> · <span>Deseado (línea punteada)</span>. ${escapeHtml(summary)} Los cambios de unidad figuran en la lista y no se mezclan en esta línea.</figcaption></figure>`;
}
function renderSuperHistory() {
  const row = supermercadoData?.productos.find(item => item.id === superHistoryProductId);
  const latest = superHistoryRows[0]?.despues || superHistoryRows[0]?.antes;
  const name = row?.producto || latest?.producto || 'Producto';
  const unit = row?.unidad || latest?.unidad || '';
  document.getElementById('super-history-title').textContent = `Historial de ${name} (${unit})`;
  document.getElementById('super-history-chart').innerHTML = superHistoryChart(superHistoryRows, unit);
  document.getElementById('super-history-events').innerHTML = superHistoryRows.length ? `<ol class="super-events">${[...superHistoryRows].sort((a,b) => b.fecha_utc.localeCompare(a.fecha_utc) || b.id - a.id).map(event => {
    const before = event.antes, after = event.despues;
    const operation = { alta: 'Alta', stock: 'Cambio de stock', edicion: 'Edición de producto', categoria_baja: 'Categoría dada de baja', baja: 'Baja de producto' }[event.operacion] || event.operacion;
    const qty = (value, snapshot) => value == null ? '—' : escapeHtml(superQuantity(value, snapshot?.unidad || unit));
    const detail = event.operacion === 'stock' ? `Stock actual: ${qty(before?.stock_actual, before)} → ${qty(after?.stock_actual, after)}` :
      `Antes: ${escapeHtml(superHistoryLabel(before?.producto))} · actual ${qty(before?.stock_actual, before)} · deseado ${qty(before?.stock_deseado, before)}. Después: ${escapeHtml(superHistoryLabel(after?.producto))} · actual ${qty(after?.stock_actual, after)} · deseado ${qty(after?.stock_deseado, after)}.`;
    return `<li><time datetime="${escapeHtml(event.fecha_utc)}">${escapeHtml(superHistoryDate(event.fecha_utc))}</time><strong>${escapeHtml(operation)}</strong><p>${detail}</p>${before && after && before.unidad !== after.unidad ? `<p>Unidad: ${escapeHtml(before.unidad)} → ${escapeHtml(after.unidad)}</p>` : ''}${before && after && before.categoria_id !== after.categoria_id ? `<p>Categoría: ${escapeHtml(superHistoryCategoryLabel(before))} → ${escapeHtml(superHistoryCategoryLabel(after))}</p>` : ''}</li>`;
  }).join('')}</ol>` : '<p class="empty-state">Sin cambios registrados.</p>';
  document.getElementById('supermercado-history-next').hidden = superHistoryCursor === null;
}
function closeSuperHistory() {
  const id = superHistoryProductId;
  ++superHistoryRevision;
  const panel = document.getElementById('supermercado-history');
  if (panel.open) panel.close();
  superHistoryProductId = null;
  superHistoryCursor = null;
  superHistoryRows = [];
  superHistoryPagePending = false;
  const returnTarget = superHistoryOrigin?.isConnected === false ? document.getElementById(`super-history-button-${id}`) : superHistoryOrigin;
  returnTarget?.focus?.();
  superHistoryOrigin = null;
}
async function showSuperHistory(id, cursor = null, origin = null) {
  const panel = document.getElementById('supermercado-history');
  if (cursor !== null && superHistoryPagePending) return;
  if (cursor === null) {
    ++superHistoryRevision;
    superHistoryPagePending = false;
    document.getElementById('supermercado-history-next').disabled = false;
    superHistoryProductId = id;
    superHistoryRows = [];
    superHistoryCursor = null;
    superHistoryOrigin = origin || document.activeElement;
    if (!panel.open) panel.showModal();
    document.getElementById('super-history-x').focus();
  }
  const revision = superHistoryRevision;
  if (cursor !== null) { superHistoryPagePending = true; document.getElementById('supermercado-history-next').disabled = true; }
  document.getElementById('super-history-status').textContent = 'Cargando historial…';
  try {
    const query = cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`;
    const page = await superRequest('GET', `/api/supermercado/productos/${id}/historial${query}`);
    if (revision !== superHistoryRevision || !panel.open || superHistoryProductId !== id) return;
    if (!Array.isArray(page.historial)) throw new Error('Historial inválido');
    const known = new Set(superHistoryRows.map(event => event.id));
    superHistoryRows.push(...page.historial.filter(event => !known.has(event.id)));
    superHistoryCursor = page.has_more ? page.next_cursor : null;
    renderSuperHistory();
    document.getElementById('super-history-status').textContent = `${superHistoryRows.length} eventos cargados.`;
  } catch (error) {
    if (revision === superHistoryRevision && panel.open) document.getElementById('super-history-status').textContent = `No se pudo cargar el historial: ${error.message}`;
  } finally {
    if (revision === superHistoryRevision) { superHistoryPagePending = false; document.getElementById('supermercado-history-next').disabled = false; }
  }
}
async function downloadSupermercadoPdf() {
  if (!supermercadoData) { superStatus('Cargá el stock antes de generar la lista.', true); return; }
  try {
    superStatus('Generando PDF…');
    const response = await fetch('/api/supermercado/lista.pdf', { credentials: 'same-origin' });
    if (!response.ok) { const body = await response.json(); throw new Error(body.error || `HTTP ${response.status}`); }
    if (!response.headers.get('content-type')?.startsWith('application/pdf')) throw new Error('Respuesta PDF inválida.');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = url; link.download = 'lista-supermercado.pdf'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    superStatus('PDF descargado.');
  } catch (error) { superStatus(error.message, error.message !== 'No falta nada'); }
}
function handleSuperFormReset(event) {
  delete event.currentTarget.dataset.version;
  if (typeof setTimeout === 'function') setTimeout(refreshSuperStockStepButtons, 0);
}
document.getElementById('supermercado-category-form')?.addEventListener('reset', handleSuperFormReset);
document.getElementById('supermercado-product-form')?.addEventListener('reset', handleSuperFormReset);
configureSuperProductStockControls();
document.getElementById('supermercado-category-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!requireSuperWrite()) return;
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const id = form.elements.id.value;
  const nombre = form.elements.nombre.value.trim();
  const orden = Number(form.elements.orden.value);
  if (!nombre || !/^\d+$/.test(form.elements.orden.value) || orden > 1000000) { superStatus('Revisá nombre y orden.', true); return; }
  if (await superMutate(id ? 'PATCH' : 'POST', `/api/supermercado/categorias${id ? '/' + id : ''}`,
    { nombre, orden }, 'Categoría guardada.')) form.reset();
});
document.getElementById('supermercado-product-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!requireSuperWrite()) return;
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const id = form.elements.id.value;
  const desired = form.elements.stock_deseado.value;
  const actual = form.elements.stock_actual.value;
  if (!validSuperStock(desired) || !validSuperStock(actual)) { superStatus('Revisá las cantidades del producto.', true); return; }
  const payload = { producto: form.elements.producto.value.trim(), unidad: form.elements.unidad.value.trim(),
    categoria_id: form.elements.categoria_id.value ? Number(form.elements.categoria_id.value) : null,
    stock_deseado: Number(desired), stock_actual: Number(actual) };
  if (!payload.producto || !payload.unidad) { superStatus('Ingresá producto y unidad.', true); return; }
  if (id) {
    if (!/^\d+$/.test(form.dataset.version || '')) { superStatus('Recargá el producto antes de guardar.', true); return; }
    payload.expected_version = Number(form.dataset.version);
  }
  if (await superMutate(id ? 'PATCH' : 'POST', `/api/supermercado/productos${id ? '/' + id : ''}`, payload, 'Producto guardado.')) form.reset();
});
document.getElementById('super-history-x')?.addEventListener('click', closeSuperHistory);
document.getElementById('super-history-close')?.addEventListener('click', closeSuperHistory);
document.getElementById('supermercado-history')?.addEventListener('cancel', event => { event.preventDefault(); closeSuperHistory(); });
document.getElementById('supermercado-history-next')?.addEventListener('click', () => {
  if (superHistoryProductId !== null && superHistoryCursor !== null) showSuperHistory(superHistoryProductId, superHistoryCursor);
});
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { if (currentView === 'supermercado') ensureComprasLoaded(true); });
  window.addEventListener('offline', () => { ++supermercadoLoadRevision; setSuperWriteAvailable(false); superStatus('Sin conexión. Stock conservado en pantalla; no actualizado.', true); });
  window.addEventListener('focus', () => { if (currentView === 'supermercado' && document.visibilityState === 'visible') ensureComprasLoaded(true); });
  document.addEventListener('visibilitychange', () => { if (currentView === 'supermercado' && document.visibilityState === 'visible') ensureComprasLoaded(true); });
  window.setInterval(() => { if (currentView === 'supermercado' && document.visibilityState === 'visible' && superOnline()) ensureComprasLoaded(true); }, 60000);
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

// ── VISTA INVENTARIO ─────────────────────────────────────────────────────

// Cotización USD→ARS "de hoy": persiste en localStorage (brief t_0e38e74e
// punto 3), nunca en DATA.inventario — es un dato de UI, no del dominio.
function getInventarioCotizacion() {
  try {
    const stored = parseFloat(localStorage.getItem(INVENTARIO_COTIZACION_STORAGE_KEY));
    if (Number.isFinite(stored) && stored > 0) return stored;
  } catch { /* localStorage puede no estar disponible (modo privado, etc.) */ }
  return INVENTARIO_COTIZACION_DEFAULT;
}

// Único "Cot. hoy" para toda la tabla (como el legacy): este handler sirve
// tanto para el input de la barra superior como para el input inline de CADA
// fila (mismo patrón que onCotizacionChange en reference-legacy/inventario-
// index.html). En vez de volver a renderizar toda la vista (lo que reconstruye
// los <input> y le hace perder el foco/cursor al que el usuario está
// tipeando), actualiza en el lugar: sincroniza el resto de los inputs "Cot.
// hoy" sin tocar el que tiene el foco (document.activeElement), vuelve a
// pintar las 4 cards (no tienen inputs, así que no hay foco que perder) y
// recalcula sólo las celdas Reventa/Venta JD/Venta Pinki de cada fila por id —
// el resto de las columnas (ARS pagado, USD compra, % JD/Pinki, ARS JD/Pinki)
// no depende de la cotización de hoy.
function setInventarioCotizacion(raw) {
  const value = parseFloat(raw);
  if (!Number.isFinite(value) || value <= 0) return;
  try { localStorage.setItem(INVENTARIO_COTIZACION_STORAGE_KEY, String(value)); } catch { /* ver getInventarioCotizacion */ }
  if (currentView !== 'inventario') return;

  const globalInput = document.getElementById('inventario-cotizacion-input');
  if (globalInput && document.activeElement !== globalInput) globalInput.value = value;
  inventarioRowsRendered.forEach((row) => {
    const input = document.getElementById(`inv-cot-${row.id}`);
    if (input && document.activeElement !== input) input.value = value;
  });

  const estadoRows = inventarioFiltroEstado
    ? DATA.inventario.filter((item) => (item.estado || 'Activo') === inventarioFiltroEstado)
    : DATA.inventario;
  renderInventarioCards(estadoRows, value);

  inventarioRowsRendered.forEach((row) => {
    if (row.usd === null) return;
    const pctPinki = 100 - row.pctJD;
    const reventa = row.usd * value;
    const ventaJD = row.usd * value * row.pctJD / 100;
    const ventaPinki = row.usd * value * pctPinki / 100;
    const reventaEl = document.getElementById(`inv-reventa-${row.id}`);
    const jdEl = document.getElementById(`inv-venta-jd-${row.id}`);
    const pinkiEl = document.getElementById(`inv-venta-pinki-${row.id}`);
    if (reventaEl) reventaEl.textContent = fmtARS(Math.round(reventa));
    if (jdEl) jdEl.textContent = fmtARS(Math.round(ventaJD));
    if (pinkiEl) pinkiEl.textContent = fmtARS(Math.round(ventaPinki));
  });
}

function setInventarioFiltroEstado(estado) {
  inventarioFiltroEstado = estado;
  if (currentView === 'inventario') renderInventarioView();
}

// USD "de compra" de un bien, misma cuenta que el legacy (usdCompra en
// reference-legacy/inventario-index.html): precio_usd_compra si viene
// explícito (incluido 0: se chequea con Number.isFinite, nunca `> 0`, para
// no tratar un 0 real como "sin dato" — hallazgo 2 del revisor 46d4f3d5); si
// falta, se deriva de precio_ars/cotizacion_usd_compra (la cotización de LA
// COMPRA, no la de hoy). Si tampoco hay esos dos datos, devuelve `null`: no
// hay forma de saber el USD sin inventar un valor mezclando el valor en ARS
// con la cotización de HOY (eso haría parecer un recálculo real donde no lo
// hay). El caller lo muestra como "—" (brief t_0e38e74e v2, punto 1).
function inventarioUsdCompra(item) {
  const explicito = parseFloat(item.precio_usd_compra);
  if (item.precio_usd_compra !== null && item.precio_usd_compra !== undefined && Number.isFinite(explicito)) {
    return explicito;
  }
  const ars = parseFloat(item.precio_ars);
  const cotCompra = parseFloat(item.cotizacion_usd_compra);
  if (item.precio_ars !== null && item.precio_ars !== undefined && Number.isFinite(ars) && Number.isFinite(cotCompra) && cotCompra > 0) {
    return ars / cotCompra;
  }
  return null;
}

// proporcion_jd es nullable (bienes migrados antes de esta extensión o sin
// backfill legacy aplicado): sin valor numérico válido entre 0 y 100, se
// asume 50/50 — mismo default que insert_inventario_bien aplica al crear un
// bien nuevo sin especificarlo, y que la fórmula del legacy (proporcion_jd ??
// 50).
function inventarioPctJD(item) {
  const pct = parseFloat(item.proporcion_jd);
  return Number.isFinite(pct) && pct >= 0 && pct <= 100 ? pct : 50;
}

// Repuebla los <select> de categoría/ubicación con los valores presentes en
// DATA.inventario, preservando la selección actual si sigue siendo válida.
function renderInventarioOptions() {
  const catSelect = document.getElementById('inventario-filtro-categoria');
  const locSelect = document.getElementById('inventario-filtro-ubicacion');
  if (!catSelect || !locSelect) return;
  const categorias = [...new Set(DATA.inventario.map((item) => item.categoria).filter(Boolean))].sort();
  const ubicaciones = [...new Set(DATA.inventario.map((item) => item.ubicacion).filter(Boolean))].sort();
  const catValue = catSelect.value;
  const locValue = locSelect.value;
  catSelect.innerHTML = '<option value="">Todas las categorías</option>' +
    categorias.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  locSelect.innerHTML = '<option value="">Todas las ubicaciones</option>' +
    ubicaciones.map((u) => `<option value="${escapeHtml(u)}">${escapeHtml(u)}</option>`).join('');
  if (categorias.includes(catValue)) catSelect.value = catValue;
  if (ubicaciones.includes(locValue)) locSelect.value = locValue;
}

// Las 4 cards reflejan el filtro de ESTADO actual (igual que el legacy, cuyo
// render() recalcula sobre `filtered` = items del estado elegido), pero no los
// filtros de búsqueda/categoría/ubicación de la tabla — mismo criterio que el
// resto de los cards de totales del dashboard. La 4ta card ("Ítems activos")
// es la excepción: cuenta TODO DATA.inventario en estado Activo, sin importar
// qué pestaña de estado esté seleccionada (igual que el legacy).
// `inventarioUsdCompra(item) || 0`: un bien sin USD conocido no aporta nada a
// la suma (sumar 0 u omitirlo da el mismo total) — no hace falta filtrar la
// lista aparte, igual que usdCompra() en el legacy (siempre devuelve un
// número, nunca null).
function renderInventarioCards(items, cotizacionHoy) {
  const totalUsd = items.reduce((acc, item) => acc + (inventarioUsdCompra(item) || 0), 0);
  const jdUsd = items.reduce((acc, item) => acc + (inventarioUsdCompra(item) || 0) * inventarioPctJD(item) / 100, 0);
  const pinkiUsd = totalUsd - jdUsd;
  const activos = DATA.inventario.filter((item) => (item.estado || 'Activo') === 'Activo').length;

  // Math.round antes de formatear: igual que el legacy (fmtARS/fmtUSD ahí
  // redondean siempre a entero), para que coincida con la captura de Juan.
  document.getElementById('inv-total-usd').textContent = fmtUSD(Math.round(totalUsd));
  document.getElementById('inv-total-ars').textContent = `≈ ${fmtARS(Math.round(totalUsd * cotizacionHoy))} ARS hoy`;
  document.getElementById('inv-jd-usd').textContent = fmtUSD(Math.round(jdUsd));
  document.getElementById('inv-jd-ars').textContent = `≈ ${fmtARS(Math.round(jdUsd * cotizacionHoy))} ARS hoy`;
  document.getElementById('inv-pinki-usd').textContent = fmtUSD(Math.round(pinkiUsd));
  document.getElementById('inv-pinki-ars').textContent = `≈ ${fmtARS(Math.round(pinkiUsd * cotizacionHoy))} ARS hoy`;
  document.getElementById('inv-count-activos').textContent = String(activos);
  document.getElementById('inv-count-sub').textContent = `${activos} bien${activos === 1 ? '' : 'es'} activo${activos === 1 ? '' : 's'}`;
}

// Tabla idéntica al legacy (columnas y orden — brief t_0e38e74e v2, punto 1),
// más la columna Reventa (ARS hoy) que agregó Juan en el ajuste final (QA de
// Juan 2026-10-23): Descripción | Categoría | Fecha | ARS pagado | Cot. compra |
// USD compra | % JD | % Pinki | ARS JD | ARS Pinki | Cot. hoy |
// Reventa (ARS hoy) | Venta JD | Venta Pinki | Estado | acciones. La
// ubicación y las notas van como subtexto bajo la descripción (no son columna
// propia del legacy). Reventa = USD de compra (el mismo que usan Venta
// JD/Pinki, incluido el derivado) × la cotización de hoy, sin repartir por
// persona.
function renderInventarioView() {
  renderInventarioOptions();
  const content = document.getElementById('inventario-content');
  if (!content) return;

  const cotizacionHoy = getInventarioCotizacion();
  const cotizacionInput = document.getElementById('inventario-cotizacion-input');
  // No pisar el input mientras el usuario está escribiendo en él.
  if (cotizacionInput && document.activeElement !== cotizacionInput) cotizacionInput.value = cotizacionHoy;

  document.querySelectorAll('#inventario-estado-filter .persona-btn').forEach((b) => {
    const active = b.dataset.estado === inventarioFiltroEstado;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });

  const estadoRows = inventarioFiltroEstado
    ? DATA.inventario.filter((item) => (item.estado || 'Activo') === inventarioFiltroEstado)
    : DATA.inventario;
  renderInventarioCards(estadoRows, cotizacionHoy);

  const query = (document.getElementById('inventario-search')?.value || '').trim().toLowerCase();
  const catFiltro = document.getElementById('inventario-filtro-categoria')?.value || '';
  const locFiltro = document.getElementById('inventario-filtro-ubicacion')?.value || '';

  const rows = estadoRows.filter((item) => {
    if (catFiltro && item.categoria !== catFiltro) return false;
    if (locFiltro && item.ubicacion !== locFiltro) return false;
    if (query) {
      const haystack = `${item.nombre || ''} ${item.notas || ''}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  }).sort((a, b) => (a.nombre || '').localeCompare(b.nombre || '', 'es'));

  const countEl = document.getElementById('inventario-count');
  if (countEl) countEl.textContent = `${rows.length} de ${estadoRows.length}`;

  const disabled = !liveMode || !inventoryAvailable || writePending || reloadPending || reloadFailed;

  if (!DATA.inventario.length) {
    inventarioRowsRendered = [];
    content.innerHTML = liveMode
      ? '<div class="empty-state">Todavía no hay bienes cargados.</div>'
      : '<div class="empty-state">Snapshot de solo lectura: sin datos de inventario disponibles sin conexión autenticada.</div>';
    return;
  }
  if (!rows.length) {
    inventarioRowsRendered = [];
    content.innerHTML = '<div class="empty-state">Sin bienes que coincidan con la búsqueda o los filtros.</div>';
    return;
  }

  const rowsForLiveUpdate = [];
  const bodyHtml = rows.map((item) => {
    const rowId = canonicalId(item.id);
    const ars = parseFloat(item.precio_ars) || 0;
    const cotCompra = parseFloat(item.cotizacion_usd_compra) || 0;
    const usd = inventarioUsdCompra(item);
    const pctJD = inventarioPctJD(item);
    const pctPinki = 100 - pctJD;
    const arsJD = ars * pctJD / 100;
    const arsPinki = ars * pctPinki / 100;
    const reventa = usd === null ? null : usd * cotizacionHoy;
    const ventaJD = usd === null ? null : usd * cotizacionHoy * pctJD / 100;
    const ventaPinki = usd === null ? null : usd * cotizacionHoy * pctPinki / 100;
    const estado = item.estado || 'Activo';
    rowsForLiveUpdate.push({ id: rowId, usd, pctJD });

    return `<tr>
      <td data-label="Descripción" class="td-desc"><strong>${escapeHtml(item.nombre)}</strong>${item.ubicacion ? `<div class="td-muted td-ubicacion">${escapeHtml(item.ubicacion)}</div>` : ''}${item.notas ? `<div class="td-muted">${escapeHtml(item.notas)}</div>` : ''}</td>
      <td data-label="Categoría" class="td-muted">${escapeHtml(item.categoria)}</td>
      <td data-label="Fecha" class="td-muted">${escapeHtml(item.fecha_adquisicion ? item.fecha_adquisicion.slice(0, 7) : null)}</td>
      <td data-label="ARS pagado" class="td-amount">${ars ? fmtARS(Math.round(ars)) : '—'}</td>
      <td data-label="Cot. compra" class="td-amount td-muted">${cotCompra ? fmtARS(Math.round(cotCompra)) : '—'}</td>
      <td data-label="USD compra" class="td-amount">${usd === null ? '—' : fmtUSD(Math.round(usd))}</td>
      <td data-label="% JD" class="td-amount td-muted">${pctJD}%</td>
      <td data-label="% Pinki" class="td-amount td-muted">${pctPinki}%</td>
      <td data-label="ARS JD" class="td-amount inv-color-jd">${ars ? fmtARS(Math.round(arsJD)) : '—'}</td>
      <td data-label="ARS Pinki" class="td-amount inv-color-pinki">${ars ? fmtARS(Math.round(arsPinki)) : '—'}</td>
      <td data-label="Cot. hoy" class="td-amount">
        <input type="number" class="cot-inline" id="inv-cot-${rowId}" value="${cotizacionHoy}" min="1" step="1"
          oninput="setInventarioCotizacion(this.value)" aria-label="Cotización de hoy para ${escapeHtml(item.nombre)}">
      </td>
      <td data-label="Reventa (ARS hoy)" class="td-amount" id="inv-reventa-${rowId}">${reventa === null ? '—' : fmtARS(Math.round(reventa))}</td>
      <td data-label="Venta JD" class="td-amount inv-color-jd" id="inv-venta-jd-${rowId}">${ventaJD === null ? '—' : fmtARS(Math.round(ventaJD))}</td>
      <td data-label="Venta Pinki" class="td-amount inv-color-pinki" id="inv-venta-pinki-${rowId}">${ventaPinki === null ? '—' : fmtARS(Math.round(ventaPinki))}</td>
      <td data-label="Estado"><span class="badge badge-${estado.toLowerCase()}">${escapeHtml(estado.toUpperCase())}</span></td>
      <td data-label="Acciones">
        <button type="button" class="fijos-secondary table-action" data-write-action data-requires="inventory" data-id="${escapeHtml(rowId)}" onclick="openForm('inventory-edit', this.dataset.id)" aria-label="Editar bien ${escapeHtml(item.nombre)}" ${disabled ? 'disabled' : ''}>Editar</button>
        <button type="button" class="fijos-secondary table-action btn-delete" data-write-action data-requires="inventory" data-id="${escapeHtml(rowId)}" onclick="openForm('inventory-delete', this.dataset.id)" aria-label="Borrar bien ${escapeHtml(item.nombre)}" ${disabled ? 'disabled' : ''}>borrar</button>
      </td>
    </tr>`;
  }).join('');
  inventarioRowsRendered = rowsForLiveUpdate;

  content.innerHTML = `<div class="table-scroll"><table id="tabla-inventario">
    <thead><tr>
      <th>Descripción</th><th>Categoría</th><th>Fecha</th>
      <th class="td-amount">ARS pagado</th><th class="td-amount">Cot. compra</th><th class="td-amount">USD compra</th>
      <th class="td-amount">% JD</th><th class="td-amount">% Pinki</th>
      <th class="td-amount">ARS JD</th><th class="td-amount">ARS Pinki</th>
      <th class="td-amount">Cot. hoy</th><th class="td-amount">Reventa (ARS hoy)</th>
      <th class="td-amount">Venta JD</th><th class="td-amount">Venta Pinki</th>
      <th>Estado</th><th>Acciones</th>
    </tr></thead>
    <tbody>${bodyHtml}</tbody>
  </table></div>`;
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
    <p>Período: <strong>${escapeHtml(periodLabel)}</strong> · filtro: ${escapeHtml(PERSONA_FILTRO_LABELS[personaFiltro])} · generado el ${escapeHtml(generatedAt)}</p>`;

  if (DATA.loadErrors.gastos) {
    html += '<p class="print-missing">⚠ No se pudo cargar data/gastos.json: sin datos de gastos, cuotas ni desglose JD/Pinki para este resumen.</p>';
  } else {
    const rows = applyPersonaFiltro(filterGastosPeriod(period.from, period.to));
    const varRows = rows.filter((r) => (parseInt(r.cuota_nro, 10) || 1) === 1);
    const varTotal = varRows.reduce((total, row) => total + expenseAmount(row), 0);
    let sub1 = 0, sub2 = 0;
    varRows.forEach((r) => {
      const monto = parseFloat(r.monto) || 0;
      const { pct1, pct2 } = getRowPct(r);
      sub1 += monto * pct1 / 100;
      sub2 += monto * pct2 / 100;
    });
    const cuotasRows = applyPersonaFiltro(filterCuotasComprometidas(period.from, period.to))
      .sort((a, b) => (a.fecha || '').localeCompare(b.fecha || ''));
    const cuotasTotal = cuotasRows.reduce((total, row) => total + expenseAmount(row), 0);

    const months = fixedMonths().length;
    const fijos = DATA.loadErrors.fijos ? [] : activeFijos()
      .filter((row) => fixedAmount(row, fixedCutoffDate().slice(0, 7), personaFiltro) !== null);
    const fijosTotal = DATA.loadErrors.fijos ? null : computeFixedForPersona(personaFiltro);
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
                <td>${fixedAmountLabel(f, fixedCutoffDate().slice(0, 7), personaFiltro)}</td>
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
              <td>${expenseAmountLabel(r)}</td>
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

// ── ATAJOS DE iPHONE (deep links ?accion=) ─────────────────────────────────
// Los accesos directos de Juan llegan como ?accion=gasto|ingreso|fijo|fijos.
// En vivo abren el alta correspondiente (o la pestaña Fijos); en snapshot o
// sin esa capability (liveMode en falso cubre ambos casos, ver loadAll), avisan
// y no abren ni cambian nada. Un valor desconocido se ignora sin tocar la URL.
// Para los valores conocidos, el parámetro se limpia con history.replaceState
// en los dos casos (vivo o aviso), para no dejarlo colgado al refrescar.
const DEEP_LINK_FORM_KIND = Object.assign(Object.create(null), { gasto: 'expense', ingreso: 'income', fijo: 'fixed' });

function consumeAccionDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const accion = params.get('accion');
  if (accion !== 'fijos' && !(accion !== null && Object.hasOwn(DEEP_LINK_FORM_KIND, accion))) return;
  if (!liveMode) {
    window.alert('Para usar este atajo iniciá sesión en la app · estás en modo snapshot de solo lectura.');
  } else if (accion === 'fijos') {
    switchView('fijos');
  } else {
    openForm(DEEP_LINK_FORM_KIND[accion]);
  }
  params.delete('accion');
  const query = params.toString();
  window.history.replaceState(null, '', window.location.pathname + (query ? `?${query}` : '') + window.location.hash);
}

loadAll().then(consumeAccionDeepLink);
