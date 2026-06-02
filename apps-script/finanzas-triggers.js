/**
 * LIFE — Finanzas: Triggers automáticos
 *
 * Este archivo maneja tres automatizaciones que corren en la Sheet:
 *   1. Auto-generación de ID (LOG-00001) cuando AppSheet agrega una fila nueva en Log
 *   2. Expansión de cuotas: si cuotas_total > 1, crea las N filas automáticamente
 *   3. Auto-generación de ID (GF-001) cuando AppSheet agrega una fila nueva en GastosFijos
 *      (sobreescribe el ID propio de AppSheet si no tiene formato GF-XXX)
 *
 * SETUP (ejecutar UNA sola vez):
 *   1. Abrí el editor de Apps Script (Extensions > Apps Script)
 *   2. Pegá este archivo o creá uno nuevo con este contenido
 *   3. Ejecutá la función: setupTriggers()
 *   4. Aceptá los permisos que pide
 *   5. Listo — los triggers quedan instalados permanentemente
 *
 * Para verificar que los triggers están activos:
 *   Apps Script → Triggers (ícono del reloj) → deben aparecer "onLogChange" y "onGastosFijosChange"
 */

const SPREADSHEET_ID_T = '1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg';

// ─── SETUP ────────────────────────────────────────────────────────────────────

/**
 * Instala los triggers de onChange para Log y GastosFijos.
 * Ejecutar UNA sola vez desde el editor (o re-ejecutar para reinstalar).
 */
function setupTriggers() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID_T);

  // Eliminar triggers existentes para evitar duplicados
  const handlers = ['onLogChange', 'onGastosFijosChange'];
  ScriptApp.getProjectTriggers().forEach(t => {
    if (handlers.includes(t.getHandlerFunction())) ScriptApp.deleteTrigger(t);
  });

  // Trigger para Log: genera IDs LOG-XXXXX y expande cuotas
  ScriptApp.newTrigger('onLogChange')
    .forSpreadsheet(ss)
    .onChange()
    .create();

  // Trigger para GastosFijos: genera IDs GF-XXX (pisa IDs de AppSheet si no tienen formato correcto)
  ScriptApp.newTrigger('onGastosFijosChange')
    .forSpreadsheet(ss)
    .onChange()
    .create();

  SpreadsheetApp.getUi().alert('✅ Triggers instalados correctamente.\n- onLogChange: ID LOG-XXXXX + expansión de cuotas\n- onGastosFijosChange: ID GF-XXX en GastosFijos');
}

// ─── TRIGGER HANDLER ─────────────────────────────────────────────────────────

/**
 * Se ejecuta automáticamente cuando algo cambia en la Sheet.
 * Busca filas nuevas sin ID y las procesa.
 */
function onLogChange(e) {
  // Usar lock para evitar ejecuciones simultáneas (ej: AppSheet escribe varias filas a la vez)
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
  } catch (err) {
    Logger.log('No se pudo obtener el lock: ' + err.message);
    return;
  }

  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID_T);
    const sheet = ss.getSheetByName('Log');
    if (!sheet) return;

    const data    = sheet.getDataRange().getValues();
    const headers = data[0];

    // Índices de columnas
    const cols = {
      id:           headers.indexOf('id'),
      fecha:        headers.indexOf('fecha'),
      tipo:         headers.indexOf('tipo'),
      categoria:    headers.indexOf('categoria'),
      subcategoria: headers.indexOf('subcategoria'),
      descripcion:  headers.indexOf('descripcion'),
      monto_total:  headers.indexOf('monto_total'),
      cuotas_total: headers.indexOf('cuotas_total'),
      cuota_nro:    headers.indexOf('cuota_nro'),
      cuota_ref:    headers.indexOf('cuota_ref'),
      medio_pago:   headers.indexOf('medio_pago'),
      tarjeta:      headers.indexOf('tarjeta'),
      pago:         headers.indexOf('pago'),
      es_fijo:      headers.indexOf('es_fijo'),
      notas:        headers.indexOf('notas'),
      borrado:         headers.indexOf('borrado'),
      tipo_proporcion:  headers.indexOf('tipo_proporcion'),
      proporcion_jd:    headers.indexOf('proporcion_jd'),
      corresponde_a:    headers.indexOf('corresponde_a'),
    };

    // Procesar cada fila sin ID (= fila nueva de AppSheet)
    for (let i = 1; i < data.length; i++) {
      const row = data[i];

      // Saltar filas completamente vacías (incluye false de checkboxes no inicializados)
      if (isEmptyRow(row)) continue;

      // Saltar filas sin los campos mínimos requeridos (tipo + fecha)
      if (!row[cols.tipo] || !row[cols.fecha]) continue;

      // Saltar filas que ya tienen ID (ya fueron procesadas)
      if (row[cols.id] && String(row[cols.id]).startsWith('LOG-')) continue;

      // ── 1. GENERAR ID ──────────────────────────────────────────────────────
      const newId = generateNextId(data, cols.id);
      sheet.getRange(i + 1, cols.id + 1).setValue(newId);
      row[cols.id] = newId; // actualizar cache local

      // ── 2. EXPANDIR CUOTAS ────────────────────────────────────────────────
      const cuotasTotal = parseInt(row[cols.cuotas_total]) || 1;
      const cuotaRef    = row[cols.cuota_ref];

      if (cuotasTotal > 1 && !cuotaRef) {
        expandCuotas(sheet, data, headers, cols, i, row, cuotasTotal, newId);
        // Recargamos data porque acabamos de agregar filas
        break;
      } else {
        // Sin cuotas: marcar cuota_nro=1 y cuota_ref='' si no están seteados
        if (!row[cols.cuota_nro]) sheet.getRange(i + 1, cols.cuota_nro + 1).setValue(1);
        if (!row[cols.borrado]) sheet.getRange(i + 1, cols.borrado + 1).setValue(false);
      }

      // ── 3. CORREGIR proporcion_jd VACÍO ──────────────────────────────────
      // AppSheet puede enviar proporcion_jd vacío cuando el usuario elige
      // tipo_proporcion=custom pero no toca el campo. En ese caso se asume 0
      // (100% de la proporción pertenece a la otra persona).
      if (cols.tipo_proporcion >= 0 && cols.proporcion_jd >= 0) {
        const tipoProp = String(row[cols.tipo_proporcion] || '').toLowerCase().trim();
        const pjd = row[cols.proporcion_jd];
        if (tipoProp === 'custom' && (pjd === '' || pjd === null || pjd === undefined)) {
          sheet.getRange(i + 1, cols.proporcion_jd + 1).setValue(0);
        }
      }
    }

    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
}

// ─── GASTOS FIJOS TRIGGER ────────────────────────────────────────────────────

/**
 * Se ejecuta automáticamente cuando algo cambia en la Sheet.
 * Busca filas nuevas en GastosFijos sin ID válido (GF-XXX) y les asigna uno.
 * Sobreescribe cualquier ID que no tenga el prefijo GF- (incluyendo IDs propios de AppSheet).
 */
function onGastosFijosChange(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
  } catch (err) {
    Logger.log('onGastosFijosChange: no se pudo obtener el lock: ' + err.message);
    return;
  }

  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID_T);
    const sheet = ss.getSheetByName('GastosFijos');
    if (!sheet) return;

    const data    = sheet.getDataRange().getValues();
    const headers = data[0];

    const idCol          = headers.indexOf('id');
    const descripcionCol = headers.indexOf('descripcion');

    if (idCol === -1) return;

    for (let i = 1; i < data.length; i++) {
      const row = data[i];

      // Saltar filas completamente vacías
      if (isEmptyRow(row)) continue;

      // Saltar filas sin descripción (campo mínimo requerido)
      if (descripcionCol >= 0 && !row[descripcionCol]) continue;

      // Saltar filas que ya tienen ID con formato correcto
      const currentId = String(row[idCol] || '');
      if (currentId.startsWith('GF-')) continue;

      // Generar nuevo GF-XXX y pisarlo (incluye IDs propios de AppSheet sin formato GF-)
      const newId = generateNextGfId(data, idCol);
      sheet.getRange(i + 1, idCol + 1).setValue(newId);
      data[i][idCol] = newId; // actualizar cache local para evitar duplicados en el mismo ciclo
    }

    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
}

// ─── CUOTAS ───────────────────────────────────────────────────────────────────

/**
 * Expande una fila con cuotas_total > 1 en N filas:
 *   - Fila original: cuota_nro=1, cuota_ref=su propio id
 *   - Filas nuevas:  cuota_nro=2..N, fechas mensuales consecutivas, monto = total/N
 */
function expandCuotas(sheet, data, headers, cols, rowIndex, originalRow, cuotasTotal, baseId) {
  const montoTotal  = parseFloat(originalRow[cols.monto_total]) || 0;
  const montoCuota  = parseFloat((montoTotal / cuotasTotal).toFixed(2));
  const fechaBase   = parseFecha(originalRow[cols.fecha]);

  // Actualizar la fila original: cuota_nro=1, cuota_ref=baseId, monto=montoCuota
  const originalRowNum = rowIndex + 1; // 1-based
  sheet.getRange(originalRowNum, cols.cuota_nro + 1).setValue(1);
  sheet.getRange(originalRowNum, cols.cuota_ref  + 1).setValue(baseId);
  sheet.getRange(originalRowNum, cols.monto_total + 1).setValue(montoCuota);
  if (!originalRow[cols.borrado]) sheet.getRange(originalRowNum, cols.borrado + 1).setValue(false);

  // Insertar filas 2..N después de la fila original
  const numNewRows = cuotasTotal - 1;
  const insertAfter = rowIndex + 1; // insertar después de la fila original (0-based = rowIndex, insertAfter = rowIndex+1)
  sheet.insertRowsAfter(originalRowNum, numNewRows);

  for (let c = 2; c <= cuotasTotal; c++) {
    const newRowNum  = originalRowNum + (c - 1);
    const fechaCuota = addMonths(fechaBase, c - 1);
    const newId      = generateNextId(sheet.getDataRange().getValues(), cols.id);

    // Construir la nueva fila copiando todos los valores de la fila original
    const newRow = [];
    headers.forEach((_, j) => {
      newRow.push(originalRow[j]);
    });

    // Sobreescribir los campos propios de esta cuota
    newRow[cols.id]          = newId;
    newRow[cols.fecha]       = Utilities.formatDate(fechaCuota, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    newRow[cols.monto_total] = montoCuota;
    newRow[cols.cuotas_total]= cuotasTotal;
    newRow[cols.cuota_nro]   = c;
    newRow[cols.cuota_ref]   = baseId;
    newRow[cols.borrado]     = false;
    sheet.getRange(newRowNum, 1, 1, newRow.length).setValues([newRow]);
  }

  Logger.log('Cuotas expandidas: ' + cuotasTotal + ' filas a partir de ' + baseId);
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Genera el próximo ID en formato LOG-00001, buscando el máximo existente.
 */
function generateNextId(data, idCol) {
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const val = String(data[i][idCol] || '');
    const match = val.match(/^LOG-(\d+)$/);
    if (match) max = Math.max(max, parseInt(match[1]));
  }
  return 'LOG-' + String(max + 1).padStart(5, '0');
}

/**
 * Genera el próximo ID en formato GF-001, buscando el máximo existente en la hoja GastosFijos.
 */
function generateNextGfId(data, idCol) {
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const val = String(data[i][idCol] || '');
    const match = val.match(/^GF-(\d+)$/);
    if (match) max = Math.max(max, parseInt(match[1]));
  }
  return 'GF-' + String(max + 1).padStart(3, '0');
}

/**
 * Parsea una fecha que puede ser un Date, string YYYY-MM-DD, o Date de Sheets.
 */
function parseFecha(val) {
  if (val instanceof Date) return val;
  if (typeof val === 'string' && val.match(/^\d{4}-\d{2}-\d{2}$/)) {
    const [y, m, d] = val.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date();
}

/**
 * Agrega N meses a una fecha sin cambiar el día.
 */
function addMonths(date, months) {
  const d = new Date(date);
  d.setMonth(d.getMonth() + months);
  return d;
}

/**
 * Devuelve true si la fila está completamente vacía o solo tiene FALSE/0.
 */
function isEmptyRow(row) {
  return row.every(cell => cell === '' || cell === null || cell === undefined || cell === false);
}

// ─── TEST ─────────────────────────────────────────────────────────────────────

/** Probar generación de ID desde el editor */
function testGenerateId() {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID_T);
  const sheet = ss.getSheetByName('Log');
  const data  = sheet.getDataRange().getValues();
  const idCol = data[0].indexOf('id');
  Logger.log('Próximo ID: ' + generateNextId(data, idCol));
}
