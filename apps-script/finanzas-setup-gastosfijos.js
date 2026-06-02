/**
 * LIFE — Finanzas: Setup hoja GastosFijos
 *
 * Qué hace:
 *   Crea la hoja "GastosFijos" en la Google Sheet del proyecto con la
 *   estructura correcta y 6 gastos fijos iniciales en $0 (el usuario
 *   los actualiza con los montos reales después).
 *
 * Cómo usar:
 *   1. Abrí la Google Sheet → Extensions > Apps Script
 *   2. Creá un archivo nuevo llamado "setup-gastosfijos" y pegá este código
 *   3. Ejecutá setupGastosFijos() desde el editor
 *   ⚠ Si ya existe la hoja GastosFijos, te va a preguntar si querés reemplazarla.
 *
 * Lógica de versionado (importante):
 *   Cuando el monto de un gasto fijo cambia (ej: el alquiler sube), NO se edita
 *   la fila existente. En su lugar se agrega una NUEVA fila con el nuevo monto
 *   y una nueva fecha vigente_desde. Esto preserva el historial completo.
 *   El endpoint ?action=fixed toma siempre la versión más reciente aplicable al mes.
 */

// === SPREADSHEET ID ===
// Si este archivo vive en el mismo proyecto que finanzas-api.js,
// SPREADSHEET_ID ya está definido globalmente. Si no, definilo acá:
const SETUP_SPREADSHEET_ID = (typeof SPREADSHEET_ID !== 'undefined')
  ? SPREADSHEET_ID
  : '1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg';


// ─── SETUP PRINCIPAL ─────────────────────────────────────────────────────────

/**
 * Crea la hoja GastosFijos con encabezados y 6 filas iniciales.
 * Ejecutar UNA SOLA VEZ. Si la hoja ya existe, pide confirmación antes de borrarla.
 */
function setupGastosFijos() {
  const ss = SpreadsheetApp.openById(SETUP_SPREADSHEET_ID);

  // === Manejar hoja existente ===
  const existing = ss.getSheetByName('GastosFijos');
  if (existing) {
    const resp = Browser.msgBox(
      '⚠ Hoja existente',
      'Ya existe la hoja GastosFijos. ¿Querés reemplazarla? Esto borra todos los datos actuales.',
      Browser.Buttons.YES_NO
    );
    if (resp !== 'yes') {
      Logger.log('Operación cancelada.');
      return;
    }
    ss.deleteSheet(existing);
  }

  // === Crear hoja nueva ===
  const sheet = ss.insertSheet('GastosFijos');

  // === Encabezados ===
  // Nombres en minúsculas sin acentos para compatibilidad con getSheetData()
  const headers = [
    'id', 'categoria', 'subcategoria', 'descripcion',
    'monto', 'responsable', 'medio_pago', 'tarjeta',
    'es_bimestral', 'vigente_desde', 'activo'
  ];
  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#1e1e1b');
  headerRange.setFontColor('#8fb87a');

  // === Datos iniciales ===
  // Montos en $0 — el usuario los actualiza con los valores reales.
  // vigente_desde = 2026-01-01 como punto de partida del historial.
  // Para actualizar un monto en el futuro: agregar NUEVA fila, no editar esta.
  const desde = '2026-01-01';

  // [id, categoria, subcategoria, descripcion, monto, responsable, medio_pago, tarjeta, es_bimestral, vigente_desde, activo]
  const rows = [
    ['GF-001', 'Hogar', 'Alquiler',      'Alquiler',            0, 'Común', 'Transferencia', '',  false, desde, true],
    ['GF-002', 'Hogar', 'Expensas',      'Expensas ordinarias', 0, 'Común', 'Transferencia', '',  false, desde, true],
    ['GF-003', 'Hogar', 'Mantenimiento', 'Seguro departamento', 0, 'Común', 'Transferencia', '',  false, desde, true],
    ['GF-004', 'Hogar', 'Internet',      'Internet',            0, 'Común', 'Débito',        '',  false, desde, true],
    ['GF-005', 'Hogar', 'Gas',           'Gas',                 0, 'Común', 'Débito',        '',  true,  desde, true],
    ['GF-006', 'Hogar', 'Electricidad',  'Electricidad',        0, 'Común', 'Débito',        '',  true,  desde, true],
  ];

  sheet.getRange(2, 1, rows.length, headers.length).setValues(rows);

  // === Formato ===
  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, headers.length);

  // Formato fecha para la columna vigente_desde (columna 10)
  sheet.getRange(2, 10, rows.length + 50, 1).setNumberFormat('yyyy-mm-dd');

  // Validación dropdown para columna tarjeta (col 8): lista desde hoja Tarjetas columna Nombre
  // Así el usuario elige de la lista en lugar de tipear a mano (igual que en la hoja Log)
  const tarjetasSheet = ss.getSheetByName('Tarjetas');
  if (tarjetasSheet && tarjetasSheet.getLastRow() > 1) {
    const tarjetasRange = tarjetasSheet.getRange(2, 2, tarjetasSheet.getLastRow() - 1, 1);
    const tarjetaRule = SpreadsheetApp.newDataValidation()
      .requireValueInRange(tarjetasRange, true)
      .setAllowInvalid(true)   // permite dejar la celda vacía sin error
      .build();
    sheet.getRange(2, 8, rows.length + 50, 1).setDataValidation(tarjetaRule);
    Logger.log('✅ Validación dropdown configurada en columna tarjeta (desde hoja Tarjetas).');
  } else {
    Logger.log('⚠  Hoja Tarjetas no encontrada o vacía — la columna tarjeta queda como texto libre.');
  }

  Logger.log('✅ Hoja GastosFijos creada con ' + rows.length + ' gastos iniciales.');
  Logger.log('⚠  Los montos están en $0. Actualizalos en la hoja antes de usar el dashboard.');
  Logger.log('');
  Logger.log('Próximo paso: crear un NUEVO deployment en Apps Script para activar el endpoint fixed.');
}


// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Agrega una nueva versión de un gasto fijo (para actualizar su monto).
 * Preserva la fila anterior como historial.
 * Uso: llámalo manualmente o desde una acción de AppSheet.
 *
 * @param {string} descripcion - Descripción exacta del gasto fijo existente
 * @param {number} nuevoMonto  - Nuevo monto mensual
 * @param {string} desde       - Fecha de vigencia en formato YYYY-MM-DD (default: hoy)
 */
function actualizarMontoFijo(descripcion, nuevoMonto, desde) {
  const ss    = SpreadsheetApp.openById(SETUP_SPREADSHEET_ID);
  const sheet = ss.getSheetByName('GastosFijos');
  if (!sheet) { Logger.log('❌ Hoja GastosFijos no encontrada'); return; }

  const data    = sheet.getDataRange().getValues();
  const headers = data[0];
  const descIdx = headers.indexOf('descripcion');

  // Buscar la fila más reciente de este gasto para copiar sus datos
  let sourceRow = null;
  for (let i = 1; i < data.length; i++) {
    if (data[i][descIdx] === descripcion) sourceRow = data[i];
  }
  if (!sourceRow) { Logger.log('❌ No se encontró: ' + descripcion); return; }

  // Generar nuevo ID
  const idIdx  = headers.indexOf('id');
  const ids    = data.slice(1).map(r => r[idIdx]).filter(Boolean);
  const maxNum = Math.max(...ids.map(id => parseInt(id.replace('GF-', '')) || 0));
  const newId  = 'GF-' + String(maxNum + 1).padStart(3, '0');

  // Armar nueva fila copiando los metadatos y actualizando monto y vigente_desde
  const newRow = [...sourceRow];
  newRow[idIdx]                          = newId;
  newRow[headers.indexOf('monto')]       = nuevoMonto;
  newRow[headers.indexOf('vigente_desde')] = desde || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');

  sheet.appendRow(newRow);
  Logger.log('✅ Nueva versión agregada: ' + descripcion + ' → $' + nuevoMonto + ' desde ' + (desde || 'hoy'));
}


// ─── AJUSTE POST-SETUP ───────────────────────────────────────────────────────

/**
 * Aplica la validación dropdown en la columna `tarjeta` de GastosFijos
 * para hojas que ya existen (sin necesidad de recrear la hoja).
 *
 * Cuándo usar: si ejecutaste setupGastosFijos() antes de que esta validación
 * existiera, o si querés reaplicarla después de agregar nuevas tarjetas.
 *
 * Ejecutar manualmente desde el editor de Apps Script.
 */
function addTarjetaValidationToGastosFijos() {
  const ss    = SpreadsheetApp.openById(SETUP_SPREADSHEET_ID);
  const sheet = ss.getSheetByName('GastosFijos');
  if (!sheet) { Logger.log('❌ Hoja GastosFijos no encontrada'); return; }

  const tarjetasSheet = ss.getSheetByName('Tarjetas');
  if (!tarjetasSheet || tarjetasSheet.getLastRow() <= 1) {
    Logger.log('❌ Hoja Tarjetas no encontrada o sin datos — validación no aplicada.');
    return;
  }

  // Columna tarjeta = columna 8 (índice basado en 1)
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const tarjetaCol = headers.indexOf('tarjeta') + 1;
  if (tarjetaCol === 0) { Logger.log('❌ Columna tarjeta no encontrada en los encabezados'); return; }

  const lastDataRow = Math.max(sheet.getLastRow(), 2);
  const dataRows    = lastDataRow - 1;

  const tarjetasRange = tarjetasSheet.getRange(2, 2, tarjetasSheet.getLastRow() - 1, 1);
  const rule = SpreadsheetApp.newDataValidation()
    .requireValueInRange(tarjetasRange, true)
    .setAllowInvalid(true)   // permite celdas vacías sin error
    .build();

  // Aplica la validación a las filas de datos + 50 filas futuras
  sheet.getRange(2, tarjetaCol, dataRows + 50, 1).setDataValidation(rule);

  Logger.log('✅ Validación dropdown aplicada en columna tarjeta (' + (dataRows + 50) + ' filas desde fila 2).');
}


// ─── TEST ─────────────────────────────────────────────────────────────────────

/** Verifica que la hoja existe y tiene los encabezados correctos */
function testGastosFijos() {
  const ss    = SpreadsheetApp.openById(SETUP_SPREADSHEET_ID);
  const sheet = ss.getSheetByName('GastosFijos');
  if (!sheet) { Logger.log('❌ Hoja GastosFijos no encontrada'); return; }

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  Logger.log('✅ Hoja encontrada. Encabezados: ' + headers.join(', '));
  Logger.log('   Filas de datos: ' + (sheet.getLastRow() - 1));
}
