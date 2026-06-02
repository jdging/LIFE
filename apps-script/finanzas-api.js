/**
 * LIFE — Finanzas: Apps Script API
 * Spreadsheet ID: 1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg
 *
 * Instrucciones de deploy:
 *   1. Abrí la Google Sheet → Extensions > Apps Script
 *   2. Creá un archivo nuevo llamado "api" y pegá este código
 *   3. Deploy > New deployment > Web App
 *      - Execute as: Me
 *      - Who has access: Anyone
 *   4. Copiá la URL del deployment (la vas a pegar en el dashboard)
 *
 * Endpoints disponibles:
 *   GET ?action=log                        → todo el log (sin borrados)
 *   GET ?action=log&month=YYYY-MM          → log filtrado por mes
 *   GET ?action=config                     → config + tarjetas + categorías
 *   GET ?action=proportions&month=YYYY-MM  → proporciones JD/Pinki para ese mes
 *   GET ?action=delete&id=LOG-XXXXX        → soft delete de una entrada
 */

const SPREADSHEET_ID = '1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg';

// ─── ROUTER ──────────────────────────────────────────────────────────────────

function doGet(e) {
  const params = e.parameter;
  const action = params.action;

  let result;

  try {
    switch (action) {
      case 'log':
        result = getLog(params.month || null);
        break;
      case 'config':
        result = getConfig();
        break;
      case 'proportions':
        result = getProportions(params.month || null);
        break;
      case 'fixed':
        result = getFixed(params.month || null);
        break;
      case 'delete':
        result = softDelete(params.id);
        break;
      case 'saldar':
        result = saldarDeuda(params.id);
        break;
      default:
        result = { ok: false, error: 'Acción desconocida: ' + action };
    }
  } catch (err) {
    result = { ok: false, error: err.message };
  }

  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}


// ─── GET LOG ─────────────────────────────────────────────────────────────────

/**
 * Devuelve el Log como array de objetos.
 * Excluye filas con borrado=TRUE.
 * Si se pasa month (YYYY-MM), filtra por fecha.
 */
function getLog(month) {
  const rows = getSheetData('Log');

  let filtered = rows.filter(row => row.borrado !== true);

  if (month) {
    filtered = filtered.filter(row => {
      const fecha = row.fecha ? String(row.fecha).substring(0, 7) : '';
      return fecha === month;
    });
  }

  return { ok: true, month: month || 'all', count: filtered.length, data: filtered };
}


// ─── GET CONFIG ──────────────────────────────────────────────────────────────

/**
 * Devuelve la configuración completa:
 *   - config: objeto clave/valor desde la hoja Config
 *   - tarjetas: array de objetos desde la hoja Tarjetas
 *   - categorias: array de objetos desde la hoja Categorías
 */
function getConfig() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);

  // Config → objeto plano
  const configSheet = ss.getSheetByName('Config');
  const configRows = configSheet.getDataRange().getValues();
  const config = {};
  for (let i = 1; i < configRows.length; i++) {
    const key = configRows[i][0];
    const val = configRows[i][1];
    if (key && !String(key).startsWith('//')) config[key] = val;
  }

  // Tarjetas → array de objetos
  const tarjetas = getSheetData('Tarjetas');

  // Categorías → array de objetos + árbol estructurado
  const categoriasRaw = getSheetData('Categorías');
  const categoriasTree = buildCategoriasTree(categoriasRaw);

  return { ok: true, config, tarjetas, categorias: categoriasRaw, categorias_tree: categoriasTree };
}

/**
 * Convierte el array plano de categorías en un árbol:
 * { Gasto: { Hogar: ['Alquiler', ...], ... }, Inversión: {...}, Ingreso: {...} }
 */
function buildCategoriasTree(rows) {
  const tree = {};
  rows.forEach(row => {
    const tipo = row.tipo;
    const cat  = row.categoria;
    const sub  = row.subcategoria;
    if (!tree[tipo]) tree[tipo] = {};
    if (!tree[tipo][cat]) tree[tipo][cat] = [];
    if (sub) tree[tipo][cat].push(sub);
  });
  return tree;
}


// ─── GET PROPORTIONS ─────────────────────────────────────────────────────────

/**
 * Calcula la proporción JD/Pinki para un mes dado.
 *
 * Lógica:
 *   1. Filtra Log: tipo="Ingreso" AND subcategoria="Salario", mes=month
 *      (estructura real del Log: col C tipo="Ingreso", col D categoria="Ingreso", col E subcategoria="Salario")
 *   2. Suma montos por persona (campo "pagó")
 *   3. Calcula porcentaje de cada una sobre el total
 *   4. Fallback: si el mes no tiene salarios, busca el último mes anterior que sí tenga
 *
 * Si no pasa month, usa el mes actual.
 */
function getProportions(month) {
  const targetMonth = month || getCurrentMonth();
  const rows = getSheetData('Log');

  const salaryRows = rows.filter(row =>
    row.tipo === 'Ingreso' &&
    row.subcategoria === 'Salario' &&
    !row.borrado
  );

  // Intentar con el mes pedido, luego hacer fallback
  let result = calcProportionsForMonth(salaryRows, targetMonth);

  if (!result) {
    // Buscar el último mes disponible con salarios (hacia atrás)
    const availableMonths = [...new Set(
      salaryRows.map(r => String(r.fecha).substring(0, 7))
    )].sort().reverse();

    const fallbackMonth = availableMonths.find(m => m < targetMonth) || availableMonths[0];

    if (fallbackMonth) {
      result = calcProportionsForMonth(salaryRows, fallbackMonth);
      result.source       = 'fallback';
      result.fallback_month = fallbackMonth;
    } else {
      // Sin datos históricos: 50/50
      return {
        ok: true,
        month: targetMonth,
        source: 'default_50_50',
        JD:    { monto: 0, porcentaje: 50 },
        Pinki: { monto: 0, porcentaje: 50 },
        total: 0,
      };
    }
  }

  result.ok    = true;
  result.month = targetMonth;
  return result;
}

/**
 * Calcula proporciones para un mes específico.
 * Devuelve null si no hay datos.
 */
function calcProportionsForMonth(salaryRows, month) {
  const monthRows = salaryRows.filter(row => String(row.fecha).substring(0, 7) === month);
  if (monthRows.length === 0) return null;

  const totals = { JD: 0, Pinki: 0 };
  monthRows.forEach(row => {
    const person = row.pago;
    const amount = parseFloat(row.monto_total) || 0;
    if (totals[person] !== undefined) totals[person] += amount;
  });

  const total = totals.JD + totals.Pinki;
  if (total === 0) return null;

  const pctJD = Math.round(totals.JD / total * 100);
  return {
    source: 'current',
    JD:    { monto: totals.JD,    porcentaje: pctJD },
    Pinki: { monto: totals.Pinki, porcentaje: 100 - pctJD },
    total,
  };
}


// ─── GET FIXED ───────────────────────────────────────────────────────────────

/**
 * Devuelve los gastos fijos vigentes para el mes dado.
 *
 * Lógica de versionado:
 *   Para cada descripción única en GastosFijos (activo=TRUE):
 *     - Filtra las versiones cuya vigente_desde <= primer día del mes
 *     - Toma la más reciente (mayor vigente_desde)
 *     - Si es_bimestral=TRUE: monto_mensual = monto / 2
 *
 * También devuelve `history`: { [descripcion]: [{vigente_desde, monto}, ...] }
 * ordenado ascendente, para renderizar gráficos de evolución sin llamadas extra.
 */
function getFixed(month) {
  const targetMonth = month || getCurrentMonth();

  // Último día del mes como string YYYY-MM-DD (para comparar con vigente_desde).
  // Usando '-31' es seguro aunque el mes tenga 30 días: la comparación es lexicográfica
  // y cualquier fecha del mes siguiente (ej: '2026-05-XX') será mayor que '2026-04-31'.
  // Esto permite que gastos que arrancan a mitad de mes (ej: vigente_desde='2026-04-08')
  // sean correctamente incluidos en la consulta de ese mes.
  const lastDay = targetMonth + '-31';

  const rows = getSheetData('GastosFijos');

  // === Construir historial completo por descripción (incluye versiones inactivas) ===
  // Qué hace: agrupa TODAS las versiones de cada gasto para mostrar su evolución en el tiempo
  const historyMap = {};
  rows.forEach(row => {
    const desc = row.descripcion || '';
    if (!desc) return;
    if (!historyMap[desc]) historyMap[desc] = [];
    historyMap[desc].push({
      vigente_desde: row.vigente_desde || '',
      monto:         parseFloat(row.monto) || 0,
    });
  });
  // Ordenar cada historial cronológicamente
  Object.keys(historyMap).forEach(desc => {
    historyMap[desc].sort((a, b) => a.vigente_desde.localeCompare(b.vigente_desde));
  });

  // === Filtrar solo filas activas ===
  const activeRows = rows.filter(r =>
    r.activo === true || String(r.activo).toUpperCase() === 'TRUE'
  );

  // Descripciones únicas entre los activos
  const descriptions = [...new Set(
    activeRows.map(r => r.descripcion || '').filter(Boolean)
  )];

  // === Para cada descripción, tomar la versión vigente en el mes consultado ===
  const vigentes = [];

  descriptions.forEach(desc => {
    const versions = activeRows.filter(r => r.descripcion === desc);

    // Versiones elegibles: vigente_desde <= último día del mes
    // (incluye gastos que arrancan a mitad del mes consultado)
    const eligible = versions
      .filter(r => r.vigente_desde && r.vigente_desde <= lastDay)
      .sort((a, b) => b.vigente_desde.localeCompare(a.vigente_desde));

    // Sin versión aplicable para este mes (el gasto empezó después)
    if (eligible.length === 0) return;

    const current      = eligible[0];
    const monto        = parseFloat(current.monto) || 0;
    const esBimestral  = current.es_bimestral === true || String(current.es_bimestral).toUpperCase() === 'TRUE';
    const montoMensual = esBimestral ? monto / 2 : monto;

    vigentes.push({
      id:             current.id,
      descripcion:    desc,
      categoria:      current.categoria      || '',
      subcategoria:   current.subcategoria   || '',
      monto:          monto,
      monto_mensual:  round2(montoMensual),
      responsable:    current.responsable    || '',
      medio_pago:     current.medio_pago     || '',
      tarjeta:        current.tarjeta        || '',
      es_bimestral:   esBimestral,
      vigente_desde:  current.vigente_desde,
      tipo_proporcion: current.tipo_proporcion || 'dinamica',
      // Usar != null en lugar de || 50: el operador || trata 0 como falsy → proporcion_jd=0 (100% Pinki) devolvería 50 incorrectamente.
      proporcion_jd:  (current.proporcion_jd != null && current.proporcion_jd !== '') ? parseFloat(current.proporcion_jd) : 50,
    });
  });

  const total = round2(vigentes.reduce((acc, r) => acc + r.monto_mensual, 0));

  return {
    ok:      true,
    month:   targetMonth,
    data:    vigentes,
    total,
    history: historyMap,
  };
}


// ─── SOFT DELETE ─────────────────────────────────────────────────────────────

/**
 * Marca borrado=TRUE en la fila que tenga id=id.
 * No elimina la fila — soft delete.
 */
function softDelete(id) {
  if (!id) return { ok: false, error: 'Falta el parámetro id' };

  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return { ok: false, error: 'No se pudo obtener el lock: ' + err.message };
  }

  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = ss.getSheetByName('Log');
    const data  = sheet.getDataRange().getValues();
    const headers = data[0];

    const idCol      = headers.indexOf('id');
    const borradoCol = headers.indexOf('borrado');

    if (idCol === -1 || borradoCol === -1) {
      return { ok: false, error: 'No se encontraron las columnas id o borrado en Log' };
    }

    for (let i = 1; i < data.length; i++) {
      if (data[i][idCol] === id) {
        sheet.getRange(i + 1, borradoCol + 1).setValue(true);
        return { ok: true, id, row: i + 1 };
      }
    }

    return { ok: false, error: `No se encontró ninguna entrada con id: ${id}` };
  } finally {
    lock.releaseLock();
  }
}


// ─── SALDAR DEUDA ────────────────────────────────────────────────────────────

/**
 * Marca saldado=TRUE en la fila que tenga id=id.
 * No elimina la fila — la entrada sigue visible en historial, pero deja de computar en deuda neta.
 */
function saldarDeuda(id) {
  if (!id) return { ok: false, error: 'Falta el parámetro id' };

  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return { ok: false, error: 'No se pudo obtener el lock: ' + err.message };
  }

  try {
    const ss      = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet   = ss.getSheetByName('Log');
    const data    = sheet.getDataRange().getValues();
    const headers = data[0];

    const idCol      = headers.indexOf('id');
    const saldadoCol = headers.indexOf('saldado');

    if (idCol === -1)      return { ok: false, error: 'No se encontró la columna id en Log' };
    if (saldadoCol === -1) return { ok: false, error: 'No se encontró la columna saldado en Log. Agregala manualmente en la hoja.' };

    // Sesión 29 — DEUDA-08: escribir fecha YYYY-MM-DD en lugar de true.
    // La columna saldado pasa a ser fecha-o-boolean (legacy true sigue siendo truthy).
    // Permite distinguir cuándo se saldó la deuda sin agregar columna nueva.
    const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
    for (let i = 1; i < data.length; i++) {
      if (data[i][idCol] === id) {
        sheet.getRange(i + 1, saldadoCol + 1).setValue(today);
        return { ok: true, id, row: i + 1, saldado: today };
      }
    }

    return { ok: false, error: `No se encontró ninguna entrada con id: ${id}` };
  } finally {
    lock.releaseLock();
  }
}


// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Lee una hoja y devuelve un array de objetos usando la primera fila como keys.
 * Convierte fechas a string ISO (YYYY-MM-DD) para evitar problemas de serialización.
 */
function getSheetData(sheetName) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) throw new Error(`Hoja no encontrada: ${sheetName}`);

  const data    = sheet.getDataRange().getValues();
  const headers = data[0];
  const rows    = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];

    // Saltar filas completamente vacías
    if (row.every(cell => cell === '' || cell === null || cell === undefined)) continue;

    const obj = {};
    headers.forEach((header, j) => {
      let val = row[j];

      // Fechas → string YYYY-MM-DD
      if (val instanceof Date) {
        val = Utilities.formatDate(val, Session.getScriptTimeZone(), 'yyyy-MM-dd');
      }

      // Números vacíos → 0 para campos numéricos conocidos
      obj[header] = val === '' ? null : val;
    });

    rows.push(obj);
  }

  return rows;
}

/** Devuelve el mes actual como YYYY-MM */
function getCurrentMonth() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM');
}

/** Redondea a 2 decimales */
function round2(n) {
  return Math.round(n * 100) / 100;
}


// ─── TEST LOCAL ───────────────────────────────────────────────────────────────
// Funciones para probar desde el editor sin hacer un request HTTP

function testGetLog()         { Logger.log(JSON.stringify(getLog('2026-04'))); }
function testGetConfig()      { Logger.log(JSON.stringify(getConfig())); }
function testGetProportions() { Logger.log(JSON.stringify(getProportions('2026-04'))); }
function testGetFixed()       { Logger.log(JSON.stringify(getFixed('2026-04'))); }
