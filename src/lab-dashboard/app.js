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
const iconFor = (categoria) => CATEGORY_ICONS[categoria] || '🔸';

const FONT = { family: 'Work Sans', size: 11.5 };
const INK = '#332d22';
const LINE = '#e6dcc4';

const fmtARS = (n) =>
  new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n);

let gastos = [];
let sortState = { key: 'fecha', dir: 'desc' };

async function loadGastos() {
  try {
    const res = await fetch('data/gastos.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    gastos = await res.json();
  } catch (err) {
    document.querySelector('main').innerHTML = `
      <div class="panel" style="border-color: var(--danger);">
        <h2 style="color: var(--danger);">No se pudo cargar data/gastos.json</h2>
        <p>Si abriste este archivo directamente con file://, el navegador puede
        bloquear la lectura del JSON local por política de CORS.
        Serví la carpeta con un servidor estático simple, por ejemplo:</p>
        <p><code>python3 -m http.server 8000</code> y abrí
        <code>http://localhost:8000/index.html</code></p>
        <p style="color: var(--ink-soft); font-size: 11px;">Detalle técnico: ${err}</p>
      </div>`;
    return;
  }
  renderAll();
}

function renderAll() {
  renderCards(gastos);
  renderChartSafe(() => renderCategoriaChart(gastos), 'chart-categoria');
  renderChartSafe(() => renderMesChart(gastos), 'chart-mes');
  renderChartSafe(() => renderPersonaChart(gastos), 'chart-persona');
  renderTabla(gastos);
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
    `<p class="chart-error">No se pudo dibujar este gráfico (Chart.js no cargó desde el CDN).
    <span class="detail">Detalle técnico: ${err.message || err}</span></p>`
  );
}

function renderCards(rows) {
  const total = rows.reduce((sum, g) => sum + g.monto, 0);
  document.getElementById('card-total').textContent = fmtARS(total);
  document.getElementById('card-count').textContent = rows.length;
  document.getElementById('card-avg').textContent = fmtARS(rows.length ? total / rows.length : 0);

  const porCategoria = {};
  rows.forEach((g) => {
    porCategoria[g.categoria] = (porCategoria[g.categoria] || 0) + g.monto;
  });
  const topCat = Object.entries(porCategoria).sort((a, b) => b[1] - a[1])[0];
  if (topCat) {
    document.getElementById('card-top-icon').textContent = iconFor(topCat[0]);
    document.getElementById('card-top-cat').textContent = topCat[0];
  }
}

function renderCategoriaChart(rows) {
  const porCategoria = {};
  rows.forEach((g) => {
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

function renderMesChart(rows) {
  const porMes = {};
  rows.forEach((g) => {
    const mes = g.fecha.slice(0, 7);
    porMes[mes] = (porMes[mes] || 0) + g.monto;
  });
  const labels = Object.keys(porMes).sort();
  const data = labels.map((m) => porMes[m]);

  new Chart(document.getElementById('chart-mes'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Total gastado', data, backgroundColor: '#7c9a6b', borderRadius: 8, maxBarThickness: 42 }],
    },
    options: {
      scales: {
        x: { ticks: { color: INK, font: FONT }, grid: { display: false } },
        y: { ticks: { color: INK, font: FONT }, grid: { color: LINE } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderPersonaChart(rows) {
  const porPersona = { JD: 0, Pinki: 0, Común: 0 };
  rows.forEach((g) => {
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

function renderTabla(rows) {
  const sorted = [...rows].sort((a, b) => {
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
      <td><span class="pill">${iconFor(g.categoria)} ${g.categoria}</span></td>
      <td>${fmtARS(g.monto)}</td>
      <td>${g.medio_pago}</td>
      <td>${g.pagado_por}</td>
    </tr>`
    )
    .join('');

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
    renderTabla(gastos);
  });
});

loadGastos();
