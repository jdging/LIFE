/**
 * LIFE — Recetario: Apps Script Setup
 *
 * Qué hace: crea las hojas Recetas e Ingredientes en el MISMO Spreadsheet
 *   que ya se usa para Compras (DEC-B1). Las tres hojas conviven ahí:
 *   ListaCompras / Recetas / Ingredientes.
 *
 * Instrucciones:
 *   1. Abrí el Spreadsheet de Compras (el mismo donde ejecutaste compras-setup.js).
 *   2. Abrí Extensions > Apps Script en ese Spreadsheet.
 *   3. Creá un archivo nuevo llamado "recetario-setup" y pegá este código.
 *   4. Reemplazá COMPRAS_SPREADSHEET_ID con el ID del Spreadsheet de Compras.
 *   5. Ejecutá setupRecetarioSheets() una sola vez.
 *   6. Ejecutá setupRecetarioTriggers() una sola vez.
 *
 * IMPORTANTE: No ejecutar setupRecetarioSheets() más de una vez sobre
 *   hojas con datos — borra y recrea ambas hojas completas.
 */

// ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

// Mismo ID que en compras-setup.js (el Spreadsheet compartido Compras + Recetario)
//const COMPRAS_SPREADSHEET_ID = '1yW2qy_COYbiP3D-Mq_Z_N7aAcnepyWnRaA2Xkux4Ajk';

const RECETAS_SHEET_NAME      = 'Recetas';
const INGREDIENTES_SHEET_NAME = 'Ingredientes';

// ─── SETUP PRINCIPAL ─────────────────────────────────────────────────────────

/**
 * Crea (o recrea) las hojas Recetas e Ingredientes con el schema completo.
 *
 * Hoja Recetas:
 *   A: id            — texto auto RECETA-00001 (trigger)
 *   B: nombre        — texto libre
 *   C: porciones_base — número (ej: 4)
 *   D: categoria     — dropdown: Desayuno / Almuerzo / Cena / Merienda / Postre / Otro
 *   E: instrucciones — texto largo (libre)
 *   F: borrado       — checkbox (default FALSE, soft delete)
 *
 * Hoja Ingredientes:
 *   A: id         — texto auto ING-00001 (trigger)
 *   B: receta_id  — FK texto (referencia a Recetas.id, ej: RECETA-00001)
 *   C: nombre     — texto libre (ej: "Harina")
 *   D: cantidad   — número
 *   E: unidad     — dropdown: u / kg / g / l / ml / cdita / cda / taza
 *   F: borrado    — checkbox (default FALSE)
 */
function setupRecetarioSheets() {
  const ss = SpreadsheetApp.openById(COMPRAS_SPREADSHEET_ID);

  _setupRecetas(ss);
  _setupIngredientes(ss);

  Logger.log('✓ Hojas Recetas e Ingredientes creadas correctamente.');
}

// ─── SETUP HOJA RECETAS ──────────────────────────────────────────────────────

function _setupRecetas(ss) {
  const existing = ss.getSheetByName(RECETAS_SHEET_NAME);
  if (existing) {
    ss.deleteSheet(existing);
    SpreadsheetApp.flush();
  }

  const sheet = ss.insertSheet(RECETAS_SHEET_NAME);

  // Cabeceras
  const headers = ['id', 'nombre', 'porciones_base', 'categoria', 'instrucciones', 'borrado'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

  // Formato cabecera
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#2a2a2a')
    .setFontColor('#ffffff');
  sheet.setFrozenRows(1);

  // Anchos de columna
  const widths = [110, 220, 100, 110, 350, 70];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  // Validaciones

  // Col D: categoria
  const categorias = ['Desayuno', 'Almuerzo', 'Cena', 'Merienda', 'Postre', 'Otro'];
  sheet.getRange(2, 4, 999, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(categorias, true)
      .setAllowInvalid(false)
      .build()
  );

  // Col C: porciones_base — número entero positivo
  sheet.getRange(2, 3, 999, 1).setNumberFormat('0');

  // Col F: borrado — checkbox
  sheet.getRange(2, 6, 999, 1).insertCheckboxes();

  // Formato condicional: borrado=TRUE → gris
  const borradoRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$F2=TRUE')
    .setBackground('#1a1a1a')
    .setFontColor('#444444')
    .setRanges([sheet.getRange(2, 1, 999, headers.length)])
    .build();

  sheet.setConditionalFormatRules([borradoRule]);

  Logger.log('  ✓ Hoja ' + RECETAS_SHEET_NAME + ' creada.');
}

// ─── SETUP HOJA INGREDIENTES ─────────────────────────────────────────────────

function _setupIngredientes(ss) {
  const existing = ss.getSheetByName(INGREDIENTES_SHEET_NAME);
  if (existing) {
    ss.deleteSheet(existing);
    SpreadsheetApp.flush();
  }

  const sheet = ss.insertSheet(INGREDIENTES_SHEET_NAME);

  // Cabeceras
  const headers = ['id', 'receta_id', 'nombre', 'cantidad', 'unidad', 'borrado'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

  // Formato cabecera
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#2a2a2a')
    .setFontColor('#ffffff');
  sheet.setFrozenRows(1);

  // Anchos de columna
  const widths = [100, 130, 220, 80, 70, 70];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  // Validaciones

  // Col E: unidad
  const unidades = ['u', 'kg', 'g', 'l', 'ml', 'cdita', 'cda', 'taza'];
  sheet.getRange(2, 5, 999, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(unidades, true)
      .setAllowInvalid(false)
      .build()
  );

  // Col D: cantidad — número con decimales
  sheet.getRange(2, 4, 999, 1).setNumberFormat('0.##');

  // Col F: borrado — checkbox
  sheet.getRange(2, 6, 999, 1).insertCheckboxes();

  // Formato condicional: borrado=TRUE → gris
  const borradoRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$F2=TRUE')
    .setBackground('#1a1a1a')
    .setFontColor('#444444')
    .setRanges([sheet.getRange(2, 1, 999, headers.length)])
    .build();

  sheet.setConditionalFormatRules([borradoRule]);

  Logger.log('  ✓ Hoja ' + INGREDIENTES_SHEET_NAME + ' creada.');
}

// ─── TRIGGERS AUTO-ID ────────────────────────────────────────────────────────

/**
 * Instala los dos triggers onEdit: uno para auto-ID en Recetas,
 * otro para auto-ID en Ingredientes. Ejecutar una sola vez.
 */
function setupRecetarioTriggers() {
  const ss = SpreadsheetApp.openById(COMPRAS_SPREADSHEET_ID);
  const existing = ScriptApp.getUserTriggers(ss).map(t => t.getHandlerFunction());

  ['onRecetasEdit', 'onIngredientesEdit'].forEach(fn => {
    if (existing.includes(fn)) {
      Logger.log('  ⚠ Trigger ' + fn + ' ya existe — no se duplica.');
    } else {
      ScriptApp.newTrigger(fn).forSpreadsheet(ss).onEdit().create();
      Logger.log('  ✓ Trigger ' + fn + ' instalado.');
    }
  });
}

/**
 * Trigger onEdit para la hoja Recetas.
 * Genera ID RECETA-XXXXX cuando se escribe el nombre (col B) y col A está vacía.
 */
function onRecetasEdit(e) {
  const sheet = e.range.getSheet();
  if (sheet.getName() !== RECETAS_SHEET_NAME) return;

  const row = e.range.getRow();
  const col = e.range.getColumn();

  // Solo si se editó col B (nombre) y es fila de datos
  if (col !== 2 || row < 2) return;

  const idCell = sheet.getRange(row, 1);
  if (idCell.getValue() !== '') return;

  const nombre = sheet.getRange(row, 2).getValue();
  if (!nombre || String(nombre).trim() === '') return;

  idCell.setValue(_generateId(sheet, 'RECETA-'));
}

/**
 * Trigger onEdit para la hoja Ingredientes.
 * Genera ID ING-XXXXX cuando se escribe el nombre (col C) y col A está vacía.
 * Col B (receta_id) debería estar completada antes o después — no bloqueamos.
 */
function onIngredientesEdit(e) {
  const sheet = e.range.getSheet();
  if (sheet.getName() !== INGREDIENTES_SHEET_NAME) return;

  const row = e.range.getRow();
  const col = e.range.getColumn();

  // Solo si se editó col C (nombre del ingrediente) y es fila de datos
  if (col !== 3 || row < 2) return;

  const idCell = sheet.getRange(row, 1);
  if (idCell.getValue() !== '') return;

  const nombre = sheet.getRange(row, 3).getValue();
  if (!nombre || String(nombre).trim() === '') return;

  idCell.setValue(_generateId(sheet, 'ING-'));
}

/**
 * Helper: genera el próximo ID correlativo con el prefijo dado.
 * Ejemplo: 'RECETA-' → 'RECETA-00001', 'ING-' → 'ING-00001'.
 */
function _generateId(sheet, prefix) {
  const data    = sheet.getDataRange().getValues();
  const headers = data[0];
  const idCol   = headers.indexOf('id');
  let   maxId   = 0;

  for (let i = 1; i < data.length; i++) {
    const val = String(data[i][idCol] || '');
    if (val.startsWith(prefix)) {
      const num = parseInt(val.replace(prefix, ''), 10);
      if (!isNaN(num) && num > maxId) maxId = num;
    }
  }

  return prefix + String(maxId + 1).padStart(5, '0');
}
