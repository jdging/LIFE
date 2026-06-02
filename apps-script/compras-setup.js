/**
 * LIFE — Compras: Apps Script Setup
 *
 * Qué hace: crea la hoja ListaCompras en el Spreadsheet indicado,
 * configura columnas, validaciones y formato condicional.
 * También instala el trigger que auto-genera IDs tipo COMP-00001.
 */

// ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

const COMPRAS_SPREADSHEET_ID = '1yW2qy_COYbiP3D-Mq_Z_N7aAcnepyWnRaA2Xkux4Ajk';
const COMPRAS_SHEET_NAME     = 'ListaCompras';

// ─── SETUP PRINCIPAL ─────────────────────────────────────────────────────────

function setupComprasSheet() {
  const ss = SpreadsheetApp.openById(COMPRAS_SPREADSHEET_ID);

  const existing = ss.getSheetByName(COMPRAS_SHEET_NAME);
  if (existing) {
    ss.deleteSheet(existing);
    SpreadsheetApp.flush();
  }

  const sheet = ss.insertSheet(COMPRAS_SHEET_NAME);

  const headers = ['id', 'nombre', 'cantidad', 'unidad', 'categoria',
                   'urgente', 'estado', 'origen', 'notas', 'borrado'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange
    .setFontWeight('bold')
    .setBackground('#2a2a2a')
    .setFontColor('#ffffff');

  sheet.setFrozenRows(1);

  const widths = [100, 220, 80, 70, 120, 70, 100, 140, 200, 70];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  const unidades = ['u', 'kg', 'g', 'l', 'ml'];
  sheet.getRange(2, 4, 999, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(unidades, true)
      .setAllowInvalid(false)
      .build()
  );

  const categorias = ['Verduras', 'Carnes', 'Lácteos', 'Panadería',
                      'Almacén', 'Bebidas', 'Limpieza', 'Otro'];
  sheet.getRange(2, 5, 999, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(categorias, true)
      .setAllowInvalid(false)
      .build()
  );

  const estados = ['pendiente', 'comprado'];
  sheet.getRange(2, 7, 999, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(estados, true)
      .setAllowInvalid(false)
      .build()
  );

  sheet.getRange(2, 6, 999, 1).insertCheckboxes();
  sheet.getRange(2, 10, 999, 1).insertCheckboxes();

  const compradoRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$G2="comprado"')
    .setFontColor('#888888')
    .setStrikethrough(true)
    .setRanges([sheet.getRange(2, 1, 999, headers.length)])
    .build();

  const borradoRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$J2=TRUE')
    .setBackground('#1a1a1a')
    .setFontColor('#444444')
    .setRanges([sheet.getRange(2, 1, 999, headers.length)])
    .build();

  sheet.setConditionalFormatRules([compradoRule, borradoRule]);
  sheet.getRange(2, 3, 999, 1).setNumberFormat('0.##');

  Logger.log('✓ Hoja ' + COMPRAS_SHEET_NAME + ' creada correctamente.');
}

// ─── TRIGGER AUTO-ID ─────────────────────────────────────────────────────────

function setupComprasTrigger() {
  const ss = SpreadsheetApp.openById(COMPRAS_SPREADSHEET_ID);

  // 1. Limpiamos cualquier trigger anterior para evitar que se ejecute doble
  const triggers = ScriptApp.getUserTriggers(ss);
  triggers.forEach(t => {
    if (t.getHandlerFunction() === 'onComprasChange' || t.getHandlerFunction() === 'onComprasEdit') {
      ScriptApp.deleteTrigger(t);
    }
  });

  // 2. Creamos el nuevo trigger onChange
  ScriptApp.newTrigger('onComprasChange') 
    .forSpreadsheet(ss)
    .onChange()
    .create();

  Logger.log('✓ Trigger onChange para Compras instalado correctamente.');
}

function onComprasChange(e) {
  // LockService igual que en Finanzas para evitar colisiones de AppSheet
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
  } catch (err) {
    Logger.log('No se pudo obtener el lock: ' + err.message);
    return;
  }

  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(COMPRAS_SHEET_NAME);
    if (!sheet) return;

    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    
    const cols = {
      id: headers.indexOf('id'),
      nombre: headers.indexOf('nombre'),
      estado: headers.indexOf('estado'),
      origen: headers.indexOf('origen')
    };

    if (cols.id === -1 || cols.nombre === -1) return;

    let dataChanged = false;

    // Recorrer todas las filas igual que en Finanzas
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      const nombre = row[cols.nombre];
      const id = row[cols.id];

      // Si no hay nombre, saltar
      if (!nombre || String(nombre).trim() === '') continue;

      // Si hay nombre pero no hay ID, lo generamos
      if (!id || String(id).trim() === '') {
        const newId = generateNextComprasId(data, cols.id);
        
        sheet.getRange(i + 1, cols.id + 1).setValue(newId);
        row[cols.id] = newId; // Actualizar caché local
        
        if (cols.estado !== -1 && !row[cols.estado]) {
          sheet.getRange(i + 1, cols.estado + 1).setValue('pendiente');
        }
        if (cols.origen !== -1 && !row[cols.origen]) {
          sheet.getRange(i + 1, cols.origen + 1).setValue('appsheet');
        }
        
        dataChanged = true;
      }
    }

    if (dataChanged) SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
}

/**
 * Helper para generar el ID (Mismo patrón que Finanzas)
 */
function generateNextComprasId(data, idCol) {
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const val = String(data[i][idCol] || '');
    const match = val.match(/^COMP-(\d+)$/);
    if (match) max = Math.max(max, parseInt(match[1]));
  }
  return 'COMP-' + String(max + 1).padStart(5, '0');
}