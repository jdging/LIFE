/**
 * finanzas-seed.js v2
 * Clears the Log completely and repopulates with 7 months of realistic test data
 * covering Oct 2025 – Apr 2026. Designed to exercise ALL dashboard features:
 *   - Proportion evolution (salaries grow over time → ratio changes month to month)
 *   - Variables with mixed tipo_proporcion: dinamica / 50/50 / custom
 *   - Personal expenses (pagó = JD or Pinki, not Común)
 *   - 4 cuota groups (cross-month installments, different titulares / proportions)
 *   - Investments by subcategory (Plazo fijo, FCI, MEP, Crypto)
 *   - GastosFijos history: 3 price versions per active gasto for the evolution chart
 *
 * Log columns (18):
 *   id | fecha | tipo | categoria | subcategoria | descripcion | monto_total |
 *   cuotas_total | cuota_nro | cuota_ref | medio_pago | tarjeta | pago |
 *   es_fijo | notas | borrado | tipo_proporcion | proporcion_jd
 *
 * Run from Apps Script editor: populateTestData()
 */


// =============================================================================
// HELPERS
// =============================================================================

/** Random amount rounded to nearest 1.000, between min and max */
function rnd(min, max) {
  return Math.round((min + Math.random() * (max - min)) / 1000) * 1000;
}

/**
 * Adds n months to a 'YYYY-MM' string. Handles year rollover automatically.
 * Example: addMonthsStr('2025-11', 2) → '2026-01'
 */
function addMonthsStr(yyyymm, n) {
  const [y, m] = yyyymm.split('-').map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

/** Converts 'YYYY-MM-DD' string to a Date object (local timezone safe) */
function fmtDate(s) {
  const [y, mo, d] = s.split('-').map(Number);
  return new Date(y, mo - 1, d);
}


// =============================================================================
// MAIN FUNCTION
// =============================================================================

function populateTestData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const logSheet    = ss.getSheetByName('Log');
  const tarjSheet   = ss.getSheetByName('Tarjetas');
  const fijosSheet  = ss.getSheetByName('GastosFijos');

  if (!logSheet || !tarjSheet) {
    SpreadsheetApp.getUi().alert('❌ No se encontraron las hojas Log o Tarjetas.');
    return;
  }

  // === READ CARDS (dynamically — never hardcode IDs) ===
  const tarjData = tarjSheet.getDataRange().getValues();
  const creditCards = [];
  const debitCards  = [];
  for (let i = 1; i < tarjData.length; i++) {
    const r = tarjData[i];
    if (!r[0]) continue;
    if (r[2] === 'Crédito') creditCards.push(String(r[0]));
    if (r[2] === 'Débito')  debitCards.push(String(r[0]));
  }
  if (!creditCards.length || !debitCards.length) {
    SpreadsheetApp.getUi().alert('❌ Se necesitan al menos 1 tarjeta de Crédito y 1 Débito en la hoja Tarjetas.');
    return;
  }
  const cc  = creditCards[0];
  const cc2 = creditCards[1] || creditCards[0]; // secondary credit card for variety
  const dc  = debitCards[0];

  // === CLEAR LOG (keep header row 1, delete all data rows) ===
  const lastRow = logSheet.getLastRow();
  if (lastRow > 1) {
    logSheet.deleteRows(2, lastRow - 1);
  }

  // === ID COUNTER — starts fresh from 1 ===
  let maxId = 0;
  function nextId() {
    maxId++;
    return 'LOG-' + String(maxId).padStart(5, '0');
  }

  /**
   * Row builder — returns an 18-element array matching Log column order.
   * tipo_proporcion: 'dinamica' (default) | '50/50' | 'custom'
   * proporcion_jd:   0–100 number, only used when tipo_proporcion = 'custom'.
   *                  Pass 0 to assign 100% to Pinki — handled as a valid value (not falsy skip).
   */
  function mkR(id, fecha, tipo, cat, subcat, desc, monto,
               cuotasTotal, cuotaNro, cuotaRef,
               medioPago, tarjeta, pago, esFijo, notas,
               tipoProp, propJd) {
    return [
      id,
      fmtDate(fecha),
      tipo, cat, subcat, desc,
      monto, cuotasTotal, cuotaNro, cuotaRef,
      medioPago, tarjeta, pago, esFijo, notas,
      false,                                         // borrado
      tipoProp || 'dinamica',                        // tipo_proporcion
      (propJd !== undefined && propJd !== null) ? propJd : '' // proporcion_jd
    ];
  }

  const rows = [];


  // =============================================================================
  // MONTHLY LOOP — Oct 2025 → Apr 2026 (7 months)
  // =============================================================================
  // Salary levels grow deliberately to show proportion evolution in the dashboard.
  // JD: 1.8M → 2.5M / Pinki: 600k → 900k (ratio shifts slightly each month)
  const months = [
    { m: '2025-10', jd: 1800000, pinki: 600000  },
    { m: '2025-11', jd: 1900000, pinki: 620000  },
    { m: '2025-12', jd: 2000000, pinki: 700000  }, // December: aguinaldo bonus
    { m: '2026-01', jd: 2100000, pinki: 750000  },
    { m: '2026-02', jd: 2250000, pinki: 800000  },
    { m: '2026-03', jd: 2400000, pinki: 850000  },
    { m: '2026-04', jd: 2500000, pinki: 900000  },
  ];

  months.forEach(({ m, jd: jdSalary, pinki: pinkiSalary }) => {
    // Helper: returns 'YYYY-MM-DD' from a day number
    const day = (n) => m + '-' + String(n).padStart(2, '0');

    // ── INGRESOS ────────────────────────────────────────────────────────────
    rows.push(mkR(nextId(), day(5), 'Ingreso', 'Salario', '', 'Sueldo ' + m + ' JD',    jdSalary,    1, 1, '', 'Transferencia', '', 'JD',    false, ''));
    rows.push(mkR(nextId(), day(5), 'Ingreso', 'Salario', '', 'Sueldo ' + m + ' Pinki', pinkiSalary, 1, 1, '', 'Transferencia', '', 'Pinki', false, ''));

    // SAC (aguinaldo) en diciembre — agrega ingresos extra para ejercitar ese mes
    if (m === '2025-12') {
      rows.push(mkR(nextId(), day(20), 'Ingreso', 'Salario', '', 'Aguinaldo JD',    Math.round(jdSalary * 0.5),    1, 1, '', 'Transferencia', '', 'JD',    false, 'SAC 2do semestre'));
      rows.push(mkR(nextId(), day(20), 'Ingreso', 'Salario', '', 'Aguinaldo Pinki', Math.round(pinkiSalary * 0.5), 1, 1, '', 'Transferencia', '', 'Pinki', false, 'SAC 2do semestre'));
    }
    // Ingreso extra freelance en algunos meses (para variedad en categorías de Ingresos)
    if (m === '2025-11' || m === '2026-02') {
      rows.push(mkR(nextId(), day(15), 'Ingreso', 'Freelance', '', 'Trabajo freelance', rnd(100000, 300000), 1, 1, '', 'Transferencia', '', 'JD', false, ''));
    }

    // ── GASTOS VARIABLES COMUNES ─────────────────────────────────────────────
    // Mix deliberado de tipo_proporcion para ejercitar la distribución F-04/F-05:
    //   - Supermercado, farmacia, limpieza → dinamica (proporcional a salarios)
    //   - Verdulería, SUBE, streaming, cine → 50/50 (se divide en partes iguales)

    rows.push(mkR(nextId(), day(8),  'Gasto', 'Comida',          'Supermercado',     'Compras supermercado',    rnd(250000, 380000), 1, 1, '', 'Débito',        dc,  'Común', false, '', 'dinamica'));
    rows.push(mkR(nextId(), day(12), 'Gasto', 'Comida',          'Verdulería',       'Verdulería semanal',      rnd(30000,   60000), 1, 1, '', 'Efectivo',      '',  'Común', false, '', '50/50'));
    rows.push(mkR(nextId(), day(14), 'Gasto', 'Comida',          'Delivery',         'Pedidos Ya',              rnd(40000,   90000), 1, 1, '', 'Crédito',       cc,  'Común', false, '', 'dinamica'));
    rows.push(mkR(nextId(), day(20), 'Gasto', 'Entretenimiento', 'Restaurantes',     'Cena salida',             rnd(60000,  130000), 1, 1, '', 'Crédito',       cc2, 'Común', false, '', '50/50'));
    rows.push(mkR(nextId(), day(18), 'Gasto', 'Salud',           'Farmacia',         'Remedios / vitaminas',    rnd(20000,   50000), 1, 1, '', 'Débito',        dc,  'Común', false, '', 'dinamica'));
    rows.push(mkR(nextId(), day(10), 'Gasto', 'Hogar',           'Limpieza',         'Productos limpieza',      rnd(20000,   40000), 1, 1, '', 'Efectivo',      '',  'Común', false, '', 'dinamica'));
    rows.push(mkR(nextId(), day(15), 'Gasto', 'Transporte',      'SUBE',             'Carga SUBE',              rnd(8000,    15000), 1, 1, '', 'Débito',        dc,  'Común', false, '', '50/50'));
    rows.push(mkR(nextId(), day(3),  'Gasto', 'Entretenimiento', 'Streaming',        'Netflix + Spotify',       rnd(15000,   25000), 1, 1, '', 'Crédito',       cc,  'Común', false, '', '50/50'));
    // Salud / obra social — aparece la mayoría de los meses
    if (m !== '2025-10') {
      rows.push(mkR(nextId(), day(10), 'Gasto', 'Salud', 'Obra social', 'Obra social prepaga', rnd(30000, 60000), 1, 1, '', 'Transferencia', '', 'Común', false, '', 'dinamica'));
    }

    // ── GASTOS PERSONALES JD ────────────────────────────────────────────────
    rows.push(mkR(nextId(), day(17), 'Gasto', 'Transporte', 'Nafta',      'Carga nafta JD',      rnd(40000, 80000), 1, 1, '', 'Débito',  dc, 'JD', false, ''));
    if (Math.random() > 0.4) {
      rows.push(mkR(nextId(), day(22), 'Gasto', 'Personal', 'Educación', 'Curso / suscripción', rnd(20000, 70000), 1, 1, '', 'Crédito', cc, 'JD', false, ''));
    }

    // ── GASTOS PERSONALES PINKI ─────────────────────────────────────────────
    rows.push(mkR(nextId(), day(24), 'Gasto', 'Personal', 'Cuidado personal', 'Peluquería / skincare', rnd(30000, 80000), 1, 1, '', 'Crédito', cc2, 'Pinki', false, ''));
    if (Math.random() > 0.5) {
      rows.push(mkR(nextId(), day(26), 'Gasto', 'Mascotas', 'Alimento', 'Comida mascotas', rnd(15000, 35000), 1, 1, '', 'Efectivo', '', 'Pinki', false, ''));
    }

    // ── INVERSIONES ─────────────────────────────────────────────────────────
    // Plazo fijo siempre (linea principal del gráfico acumulado)
    rows.push(mkR(nextId(), day(28), 'Inversión', 'Plazo fijo', '', 'Plazo fijo 30 días',  rnd(500000, 900000), 1, 1, '', 'Transferencia', '', 'JD',    false, ''));
    rows.push(mkR(nextId(), day(28), 'Inversión', 'FCI',        '', 'Fondo money market',  rnd(150000, 400000), 1, 1, '', 'Transferencia', '', 'Común', false, ''));
    if (Math.random() > 0.35) {
      rows.push(mkR(nextId(), day(28), 'Inversión', 'Dólar/MEP', '', 'Compra dólar MEP',    rnd(200000, 500000), 1, 1, '', 'Transferencia', '', 'JD',    false, ''));
    }
    if (Math.random() > 0.5) {
      rows.push(mkR(nextId(), day(28), 'Inversión', 'Crypto',    '', 'Bitcoin / ETH',        rnd(100000, 300000), 1, 1, '', 'Transferencia', '', 'Pinki', false, ''));
    }
  });


  // =============================================================================
  // CUOTA GROUPS (4 compras en cuotas, distintos titulares y proporciones)
  // =============================================================================
  // Convención: primera cuota tiene cuota_ref = su propio id (self-reference).
  // Las cuotas siguientes referencian ese firstId.
  // El trigger de Apps Script NO re-expande estas filas porque cuota_nro ya está seteado.

  // 1. TV 65" — 6 cuotas de $133.000 (total ~$800k)
  //    Iniciada Nov 2025 — vence en Abr 2026 → cuotas 5 y 6 aparecen como "comprometidas"
  //    Común | dinamica
  {
    const firstId = nextId();
    const base = '2025-11';
    rows.push(mkR(firstId, addMonthsStr(base, 0) + '-10', 'Gasto', 'Hogar', 'Decoración', 'TV 65" - cuota 1/6', 133000, 6, 1, firstId, 'Crédito', cc, 'Común', false, 'Total $800k en 6 cuotas', 'dinamica'));
    for (let i = 2; i <= 6; i++) {
      rows.push(mkR(nextId(), addMonthsStr(base, i - 1) + '-10', 'Gasto', 'Hogar', 'Decoración', 'TV 65" - cuota ' + i + '/6', 133000, 6, i, firstId, 'Crédito', cc, 'Común', false, 'Total $800k en 6 cuotas', 'dinamica'));
    }
  }

  // 2. Zapatillas JD — 3 cuotas de $55.000 (total $165k)
  //    Iniciada Ene 2026 | pagó = JD | custom 100% JD (proporcion_jd = 100)
  {
    const firstId = nextId();
    const base = '2026-01';
    rows.push(mkR(firstId, base + '-15', 'Gasto', 'Personal', 'Ropa', 'Zapatillas JD - cuota 1/3', 55000, 3, 1, firstId, 'Crédito', cc2, 'JD', false, '', 'custom', 100));
    for (let i = 2; i <= 3; i++) {
      rows.push(mkR(nextId(), addMonthsStr(base, i - 1) + '-15', 'Gasto', 'Personal', 'Ropa', 'Zapatillas JD - cuota ' + i + '/3', 55000, 3, i, firstId, 'Crédito', cc2, 'JD', false, '', 'custom', 100));
    }
  }

  // 3. Silla de escritorio — 4 cuotas de $75.000 (total $300k)
  //    Iniciada Feb 2026 | Común | 50/50 (gasto del espacio de trabajo compartido)
  {
    const firstId = nextId();
    const base = '2026-02';
    rows.push(mkR(firstId, base + '-20', 'Gasto', 'Hogar', 'Decoración', 'Silla escritorio - cuota 1/4', 75000, 4, 1, firstId, 'Crédito', cc, 'Común', false, 'Total $300k en 4 cuotas', '50/50'));
    for (let i = 2; i <= 4; i++) {
      rows.push(mkR(nextId(), addMonthsStr(base, i - 1) + '-20', 'Gasto', 'Hogar', 'Decoración', 'Silla escritorio - cuota ' + i + '/4', 75000, 4, i, firstId, 'Crédito', cc, 'Común', false, 'Total $300k en 4 cuotas', '50/50'));
    }
  }

  // 4. Tablet Pinki — 3 cuotas de $90.000 (total $270k)
  //    Iniciada Mar 2026 | pagó = Pinki | custom 0% JD (proporcion_jd = 0 → 100% Pinki)
  {
    const firstId = nextId();
    const base = '2026-03';
    rows.push(mkR(firstId, base + '-12', 'Gasto', 'Personal', 'Educación', 'Tablet Pinki - cuota 1/3', 90000, 3, 1, firstId, 'Crédito', cc2, 'Pinki', false, '', 'custom', 0));
    for (let i = 2; i <= 3; i++) {
      rows.push(mkR(nextId(), addMonthsStr(base, i - 1) + '-12', 'Gasto', 'Personal', 'Educación', 'Tablet Pinki - cuota ' + i + '/3', 90000, 3, i, firstId, 'Crédito', cc2, 'Pinki', false, '', 'custom', 0));
    }
  }


  // =============================================================================
  // WRITE TO LOG SHEET
  // =============================================================================
  if (rows.length > 0) {
    logSheet.getRange(2, 1, rows.length, 18).setValues(rows);
    logSheet.getRange(2, 2, rows.length, 1).setNumberFormat('yyyy-mm-dd');
  }


  // =============================================================================
  // SEED GASTOS FIJOS HISTORY
  // =============================================================================
  // Agrega 3 versiones históricas de precios por cada gasto activo en GastosFijos,
  // para que el gráfico de evolución (AJ-2) tenga datos con los que renderizar.
  let fijosMsg = '⚠ Hoja GastosFijos no encontrada — historial omitido.';
  if (fijosSheet) {
    clearSeedGastosFijosHistory(fijosSheet);
    seedGastosFijosHistory(fijosSheet);
    fijosMsg = '✅ Historial de GastosFijos generado (3 versiones por gasto activo).';
  }

  SpreadsheetApp.getUi().alert(
    '✅ Log borrado y recargado con ' + rows.length + ' filas.\n' +
    'Período: Oct 2025 – Abr 2026 (7 meses)\n' +
    '\n' +
    'Cuotas incluidas:\n' +
    '  TV 65"          6c × $133k  (Nov 2025 – Abr 2026)\n' +
    '  Zapatillas JD   3c × $55k   (Ene – Mar 2026)\n' +
    '  Silla escritorio 4c × $75k  (Feb – May 2026)\n' +
    '  Tablet Pinki    3c × $90k   (Mar – May 2026)\n' +
    '\n' +
    fijosMsg
  );
}


// =============================================================================
// GASTOS FIJOS HISTORY — SEED & CLEAR
// =============================================================================

/**
 * Removes rows from GastosFijos where vigente_desde < 2026-01-01.
 * These are the historical rows added by a previous seed run.
 * Rows with vigente_desde >= 2026-01-01 (production prices) are preserved.
 *
 * Handles both Date objects and string values in vigente_desde (Sheets behavior varies).
 */
function clearSeedGastosFijosHistory(sheet) {
  const data = sheet.getDataRange().getValues();
  // Columns: descripcion | monto | vigente_desde | es_bimestral | activo | tarjeta
  const rowsToDelete = [];
  for (let i = 1; i < data.length; i++) {
    const vigRaw = data[i][2];
    let vigStr;
    if (vigRaw instanceof Date) {
      vigStr = Utilities.formatDate(vigRaw, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    } else {
      vigStr = String(vigRaw).substring(0, 10); // take YYYY-MM-DD part if needed
    }
    if (vigStr < '2026-01-01') {
      rowsToDelete.push(i + 1); // sheet rows are 1-indexed
    }
  }
  // Delete from bottom to top to avoid index shifting
  for (let i = rowsToDelete.length - 1; i >= 0; i--) {
    sheet.deleteRow(rowsToDelete[i]);
  }
}

/**
 * Reads the current (latest) active price per descripcion in GastosFijos.
 * For each active gasto, inserts 3 historical rows at past dates:
 *   2025-01-01 → 65% of current monto
 *   2025-07-01 → 80% of current monto
 *   2025-10-01 → 92% of current monto
 *
 * This gives the evolution chart (AJ-2) enough data points to draw a meaningful
 * stepped line showing how each fixed expense has grown over time.
 */
function seedGastosFijosHistory(sheet) {
  const data = sheet.getDataRange().getValues();
  // Columns: descripcion | monto | vigente_desde | es_bimestral | activo | tarjeta

  // Find the latest (most recent vigente_desde) active row per descripcion
  const latest = {};
  for (let i = 1; i < data.length; i++) {
    const [desc, monto, vigRaw, esBim, activo, tarjeta] = data[i];
    if (!desc || !activo) continue;
    let vigStr;
    if (vigRaw instanceof Date) {
      vigStr = Utilities.formatDate(vigRaw, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    } else {
      vigStr = String(vigRaw).substring(0, 10);
    }
    if (!latest[desc] || vigStr > latest[desc].vigStr) {
      latest[desc] = { monto: parseFloat(monto) || 0, esBim, tarjeta: tarjeta || '', vigStr };
    }
  }

  // Historical dates and price factors (simulate inflation / rent increases)
  const histDates   = ['2025-01-01', '2025-07-01', '2025-10-01'];
  const histFactors = [0.65, 0.80, 0.92];

  // Build new rows
  const newRows = [];
  Object.entries(latest).forEach(([desc, { monto, esBim, tarjeta }]) => {
    histFactors.forEach((factor, idx) => {
      // Round to nearest 1.000 for realistic-looking amounts
      const raw = monto * factor;
      const histMonto = raw >= 1000 ? Math.round(raw / 1000) * 1000 : Math.round(raw);
      newRows.push([desc, histMonto, fmtDate(histDates[idx]), esBim, true, tarjeta]);
    });
  });

  if (newRows.length > 0) {
    const startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, newRows.length, 6).setValues(newRows);
    sheet.getRange(startRow, 3, newRows.length, 1).setNumberFormat('yyyy-mm-dd');
  }
}
