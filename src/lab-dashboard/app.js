const CHART_COLORS = ['#7c9a6b', '#c97d55', '#d1a13f', '#8a8a5c', '#a9926f', '#5f7d52'];
const PERSONA_COLORS = { JD: '#c97d55', Pinki: '#d1a13f', Común: '#7c9a6b' };
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
const iconFor = (categoria) => CATEGORY_ICONS[categoria] || '🔸';

const FONT = { family: 'Work Sans', size: 11.5 };
const INK = '#332d22';
const LINE = '#e6dcc4';

const fmtARS = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n);
const fmtARSCompact = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', notation: 'compact', maximumFractionDigits: 1 }).format(n);
const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function mesLabel(mesStr) {
  const [y, m] = mesStr.split('-').map(Number);
  return `${capitalize(MESES_LARGO[m - 1])} ${y}`;
}
function mesCorto(mesStr) {
  const [y, m] = mesStr.split('-').map(Number);
  return `${MESES_LARGO[m - 1].slice(0, 3)} '${String(y).slice(2)}`;
}

// El último mes con total_ingresos > 0 es el último mes "real"; los meses
// posteriores del export son proyecciones de gastos fijos/cuotas sin ingreso cargado.
function getLatestRealMonth(rows) {
  const sorted = [...rows].sort((a, b) => a.mes.localeCompare(b.mes));
  const real = sorted.filter((r) => r.total_ingresos > 0);
  return real.length ? real[real.length - 1] : sorted[sorted.length - 1];
}

let gastos, ingresos, gastosFijos, resumenMeses;
let sortState = { key: 'fecha', dir: 'desc' };
let mesFiltroTabla = '';

async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP ${res.status} al cargar ${path}`);
  return res.json();
}

async function loadAll() {
  const [gastosR, ingresosR, fijosR, resumenR] = await Promise.allSettled([
    fetchJSON('data/gastos.json'),
    fetchJSON('data/ingresos.json'),
    fetchJSON('data/gastos_fijos.json'),
    fetchJSON('data/resumen_meses.json'),
  ]);

  if (gastosR.status === 'fulfilled') gastos = gastosR.value;
  else console.error('No se pudo cargar data/gastos.json', gastosR.reason);

  if (ingresosR.status === 'fulfilled') ingresos = ingresosR.value;
  else console.error('No se pudo cargar data/ingresos.json', ingresosR.reason);

  if (fijosR.status === 'fulfilled') gastosFijos = fijosR.value;
  else console.error('No se pudo cargar data/gastos_fijos.json', fijosR.reason);

  if (resumenR.status === 'fulfilled') resumenMeses = resumenR.value;
  else console.error('No se pudo cargar data/resumen_meses.json', resumenR.reason);

  renderAll();
}

function renderAll() {
  renderSafe(renderCardTotalGastos, '#card-total-gastos-wrap');
  renderSafe(renderCardTotalIngresos, '#card-total-ingresos-wrap');
  renderSafe(renderCardBalance, '#card-balance-wrap');
  renderSafe(renderCardProporcion, '#card-proporcion-wrap');

  renderSafe(renderDeudaActual, '#deuda-actual');
  renderSafe(renderDeudaHistorial, '#deuda-historial');

  renderChartSafe(renderEvolucionChart, 'chart-evolucion');
  renderChartSafe(renderProporcionChart, 'chart-proporcion');
  renderChartSafe(renderCategoriaChart, 'chart-categoria');
  renderChartSafe(renderPersonaChart, 'chart-persona');

  renderSafe(renderGastosFijos, '#fijos-panel');
  renderSafe(() => {
    setupFiltroMesTabla();
    renderTabla(gastos);
  }, '#tabla-panel');
}

// Envuelve el render de una sección no-chart: si los datos que necesita
// fallaron al cargar (quedan `undefined`), la sección explota acá adentro
// y el error queda contenido a ese bloque, sin tirar abajo el resto de la página.
function renderSafe(renderFn, selector) {
  try {
    renderFn();
  } catch (err) {
    showSectionError(selector, err);
  }
}

function showSectionError(selector, err) {
  const el = document.querySelector(selector);
  if (!el) return;
  const heading = el.querySelector('h2');
  const message = `<p class="section-error">No se pudo mostrar esta sección.
    <span class="detail">Detalle técnico: ${escapeHtml(err.message || err)}</span></p>`;
  el.innerHTML = heading ? heading.outerHTML + message : message;
}

function renderChartSafe(renderFn, canvasId) {
  try {
    renderFn();
  } catch (err) {
    showChartError(canvasId, err);
  }
}

function showChartError(canvasId, err) {
  const canvas = document.getElementById(canvasId);
  const panel = canvas?.closest('.panel');
  if (!panel) return;
  canvas.style.display = 'none';
  panel.insertAdjacentHTML(
    'beforeend',
    `<p class="chart-error">No se pudo dibujar este gráfico.
    <span class="detail">Detalle técnico: ${escapeHtml(err.message || err)}</span></p>`
  );
}

// ---------- Cards ----------

function renderCardTotalGastos() {
  const total = gastos.reduce((sum, g) => sum + g.monto, 0);
  document.getElementById('card-total-gastos').textContent = fmtARS(total);
}

function renderCardTotalIngresos() {
  const total = ingresos.reduce((sum, i) => sum + i.monto, 0);
  document.getElementById('card-total-ingresos').textContent = fmtARS(total);
}

function renderCardBalance() {
  const totalGastos = gastos.reduce((sum, g) => sum + g.monto, 0);
  const totalIngresos = ingresos.reduce((sum, i) => sum + i.monto, 0);
  const balance = totalIngresos - totalGastos;
  const el = document.getElementById('card-balance');
  el.textContent = fmtARS(balance);
  el.classList.toggle('value-negative', balance < 0);
}

function renderCardProporcion() {
  const mesActual = getLatestRealMonth(resumenMeses);
  document.getElementById('card-proporcion').textContent =
    `JD ${mesActual.proporcion_jd.toFixed(0)}% · Pinki ${mesActual.proporcion_pinki.toFixed(0)}%`;
  document.getElementById('card-proporcion-sub').textContent = mesLabel(mesActual.mes);
}

// ---------- Deudas ----------

function renderDeudaActual() {
  const mesActual = getLatestRealMonth(resumenMeses);
  const d = mesActual.deuda;
  const container = document.getElementById('deuda-actual');
  if (!d || !d.deudor) {
    container.innerHTML = `<p class="deuda-saldado">✓ Sin deuda pendiente en ${mesLabel(mesActual.mes)} — cuentas saldadas.</p>`;
    return;
  }
  container.innerHTML = `
    <div class="deuda-destacada">
      <div>
        <span class="deuda-mes">${mesLabel(mesActual.mes)}</span>
        <p class="deuda-texto"><strong>${escapeHtml(d.deudor)}</strong> le debe
          <strong class="deuda-monto">${fmtARS(d.monto)}</strong> a
          <strong>${escapeHtml(d.acreedor)}</strong></p>
      </div>
    </div>`;
}

function renderDeudaHistorial() {
  const mesActual = getLatestRealMonth(resumenMeses);
  const sorted = [...resumenMeses].sort((a, b) => a.mes.localeCompare(b.mes));
  const conDeuda = sorted.filter((r) => r.deuda && r.deuda.deudor && r.mes !== mesActual.mes);
  const ultimos = conDeuda.slice(-5).reverse();
  const container = document.getElementById('deuda-historial');
  if (!ultimos.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = `
    <h3>Meses anteriores</h3>
    <ul class="deuda-lista">
      ${ultimos
        .map(
          (r) => `<li><span class="deuda-lista-mes">${mesLabel(r.mes)}</span>
            <span>${escapeHtml(r.deuda.deudor)} le debe ${fmtARS(r.deuda.monto)} a ${escapeHtml(r.deuda.acreedor)}</span></li>`
        )
        .join('')}
    </ul>`;
}

// ---------- Charts ----------

function renderEvolucionChart() {
  const rows = [...resumenMeses].sort((a, b) => a.mes.localeCompare(b.mes));
  const labels = rows.map((r) => mesCorto(r.mes));

  new Chart(document.getElementById('chart-evolucion'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Ingresos', data: rows.map((r) => r.total_ingresos), backgroundColor: '#7c9a6b', borderRadius: 6, maxBarThickness: 26 },
        { label: 'Gastos', data: rows.map((r) => r.total_gastos), backgroundColor: '#c97d55', borderRadius: 6, maxBarThickness: 26 },
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

function renderProporcionChart() {
  const rows = [...resumenMeses].sort((a, b) => a.mes.localeCompare(b.mes)).filter((r) => r.total_ingresos > 0);
  const labels = rows.map((r) => mesCorto(r.mes));

  new Chart(document.getElementById('chart-proporcion'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'JD %', data: rows.map((r) => r.proporcion_jd), borderColor: '#c97d55', backgroundColor: '#c97d55', tension: 0.3, pointRadius: 3 },
        { label: 'Pinki %', data: rows.map((r) => r.proporcion_pinki), borderColor: '#d1a13f', backgroundColor: '#d1a13f', tension: 0.3, pointRadius: 3 },
      ],
    },
    options: {
      scales: {
        x: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        y: { min: 0, max: 100, ticks: { color: INK, font: FONT, callback: (v) => `${v}%` }, grid: { color: LINE } },
      },
      plugins: { legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12 } } },
    },
  });
}

function renderCategoriaChart() {
  const porCategoria = {};
  gastos.forEach((g) => {
    porCategoria[g.categoria] = (porCategoria[g.categoria] || 0) + g.monto;
  });
  const categorias = Object.keys(porCategoria);
  const labels = categorias.map((c) => `${iconFor(c)} ${c}`);
  const data = categorias.map((c) => porCategoria[c]);

  new Chart(document.getElementById('chart-categoria'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: CHART_COLORS, borderColor: '#fffdf7', borderWidth: 3 }],
    },
    options: {
      cutout: '58%',
      plugins: {
        legend: { position: 'bottom', labels: { color: INK, font: FONT, boxWidth: 12, padding: 12 } },
      },
    },
  });
}

function renderPersonaChart() {
  const porPersona = { JD: 0, Pinki: 0, Común: 0 };
  gastos.forEach((g) => {
    porPersona[g.pagado_por] = (porPersona[g.pagado_por] || 0) + g.monto;
  });
  const labels = Object.keys(porPersona);
  const data = labels.map((p) => porPersona[p]);
  const colors = labels.map((p) => PERSONA_COLORS[p] || '#8a8a5c');

  new Chart(document.getElementById('chart-persona'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderRadius: 8, maxBarThickness: 36 }],
    },
    options: {
      indexAxis: 'y',
      scales: {
        x: { ticks: { color: INK, font: FONT }, grid: { color: LINE } },
        y: { ticks: { color: INK, font: FONT }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ---------- Gastos fijos ----------

function renderGastosFijos() {
  const rows = [...gastosFijos].sort((a, b) => b.monto_estimado - a.monto_estimado);
  const tbody = document.getElementById('fijos-body');
  tbody.innerHTML = rows
    .map(
      (f) => `
    <tr>
      <td>${escapeHtml(f.nombre)}</td>
      <td><span class="pill">${iconFor(f.categoria)} ${escapeHtml(f.categoria)}${f.subcategoria ? ' · ' + escapeHtml(f.subcategoria) : ''}</span></td>
      <td>${fmtARS(f.monto_estimado)}</td>
      <td>${capitalize(f.periodicidad)}</td>
    </tr>`
    )
    .join('');

  // Los bimestrales se prorratean a mitad para que el total sea comparable con un mes tipo.
  const totalMensual = rows.reduce(
    (sum, f) => sum + (f.periodicidad === 'bimestral' ? f.monto_estimado / 2 : f.monto_estimado),
    0
  );
  document.getElementById('fijos-total').textContent = fmtARS(totalMensual);
}

// ---------- Tabla de detalle ----------

function setupFiltroMesTabla() {
  const meses = [...new Set(gastos.map((g) => g.fecha.slice(0, 7)))].sort().reverse();
  const select = document.getElementById('filtro-mes-tabla');
  select.innerHTML =
    '<option value="">Todos</option>' +
    meses.map((m) => `<option value="${m}">${mesLabel(m)}</option>`).join('');
  select.value = mesFiltroTabla;
  select.addEventListener('change', () => {
    mesFiltroTabla = select.value;
    renderTabla(gastos);
  });
}

function renderTabla(rows) {
  const filtered = mesFiltroTabla ? rows.filter((g) => g.fecha.slice(0, 7) === mesFiltroTabla) : rows;

  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortState.key];
    const vb = b[sortState.key];
    const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
    return sortState.dir === 'asc' ? cmp : -cmp;
  });

  const tbody = document.getElementById('tabla-body');
  tbody.innerHTML = sorted
    .map(
      (g) => `
    <tr>
      <td>${g.fecha}</td>
      <td><span class="pill">${iconFor(g.categoria)} ${escapeHtml(g.categoria)}</span></td>
      <td>${fmtARS(g.monto)}${g.cuotas_total > 1 ? ` <span class="cuota-tag">${g.cuota_nro}/${g.cuotas_total}</span>` : ''}</td>
      <td>${escapeHtml(g.medio_pago)}</td>
      <td>${escapeHtml(g.pagado_por)}</td>
    </tr>`
    )
    .join('');

  document.getElementById('tabla-count').textContent = `${sorted.length} de ${gastos.length} gastos`;

  document.querySelectorAll('#tabla-gastos thead th').forEach((th) => {
    th.querySelector('.arrow')?.remove();
    if (th.dataset.key === sortState.key) {
      th.insertAdjacentHTML('beforeend', `<span class="arrow">${sortState.dir === 'asc' ? '↑' : '↓'}</span>`);
    }
  });
}

document.querySelectorAll('#tabla-gastos thead th').forEach((th) => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (sortState.key === key) {
      sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    } else {
      sortState = { key, dir: 'asc' };
    }
    renderSafe(() => renderTabla(gastos), '#tabla-panel');
  });
});

loadAll();
