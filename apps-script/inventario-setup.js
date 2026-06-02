// ============================================================
// MODULO INVENTARIO — Setup de hoja en Google Sheets
// Sheet ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw
// ------------------------------------------------------------
// INSTRUCCIONES:
//   1. Abrir el editor de Apps Script del Spreadsheet de Inventario
//   2. Pegar este archivo completo
//   3. Ejecutar setupInventarioSheet() — crea la hoja con headers y validaciones
//   4. Ejecutar setupInventarioTrigger() — instala el trigger de auto-ID
//      (requiere autorización la primera vez)
// ============================================================

const INVENTARIO_SHEET_ID = '1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw';
const INVENTARIO_SHEET_NAME = 'Inventario';

// ------------------------------------------------------------
// setupInventarioSheet()
// Crea (o recrea) la hoja Inventario con headers, validaciones
// y formato. No toca datos si la hoja ya existe — primero borra
// y recrea solo si el usuario lo ejecuta explicitamente.
// ------------------------------------------------------------
function setupInventarioSheet() {
  const ss = SpreadsheetApp.openById(INVENTARIO_SHEET_ID);

  // Crear hoja si no existe; si existe, limpiar todo
  let sheet = ss.getSheetByName(INVENTARIO_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(INVENTARIO_SHEET_NAME);
    Logger.log('Hoja "Inventario" creada.');
  } else {
    sheet.clear();
    sheet.clearFormats();
    Logger.log('Hoja "Inventario" existente limpiada y reconfigurada.');
  }

  // ----------------------------------------------------------
  // 1. Headers
  // ----------------------------------------------------------
  const headers = [
    'id',                       // A — INV-00001 (auto via trigger)
    'descripcion',              // B — texto libre
    'categoria',                // C — lista
    'fecha_compra',             // D — fecha
    'precio_ars',               // E — monto pagado en ARS
    'cotizacion_usd_compra',    // F — tipo de cambio ARS/USD en la fecha de compra
    'precio_usd_compra',        // G — valor en USD (ingresable; sugerido = precio_ars / cotizacion)
    'proporcion_jd',            // H — % que le corresponde a JD (0-100); Pinki = 100 - este valor
    'precio_venta_estimado_usd',// I — estimacion subjetiva de precio de reventa en USD
    'estado',                   // J — Activo / Vendido / Donado / Desechado
    'notas',                    // K — texto libre
    'borrado',                  // L — soft delete (checkbox, default FALSE)
  ];

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#1a1a2e');
  headerRange.setFontColor('#8fb87a');
  headerRange.setHorizontalAlignment('center');

  sheet.setFrozenRows(1);

  // ----------------------------------------------------------
  // 2. Anchos de columna
  // ----------------------------------------------------------
  const colWidths = [
    100,  // A id
    220,  // B descripcion
    140,  // C categoria
    110,  // D fecha_compra
    120,  // E precio_ars
    160,  // F cotizacion_usd_compra
    150,  // G precio_usd_compra
    120,  // H proporcion_jd
    190,  // I precio_venta_estimado_usd
    110,  // J estado
    220,  // K notas
    80,   // L borrado
  ];
  colWidths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  // ----------------------------------------------------------
  // 3. Validaciones de datos (filas 2..1000)
  // ----------------------------------------------------------
  const DATA_ROWS = 999;
  const startRow = 2;

  // C — categoria
  const categorias = [
    'Electronica',
    'Muebles',
    'Electrodomesticos',
    'Vehiculo',
    'Ropa',
    'Arte',
    'Herramientas',
    'Otro',
  ];
  sheet.getRange(startRow, 3, DATA_ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(categorias, true)
      .setAllowInvalid(false)
      .setHelpText('Selecciona una categoria de la lista.')
      .build()
  );

  // H — proporcion_jd (0 a 100)
  sheet.getRange(startRow, 8, DATA_ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireNumberBetween(0, 100)
      .setAllowInvalid(false)
      .setHelpText('Ingresa un numero entre 0 y 100 (porcentaje de JD). El porcentaje de Pinki se calcula como 100 menos este valor.')
      .build()
  );

  // J — estado
  const estados = ['Activo', 'Vendido', 'Donado', 'Desechado'];
  sheet.getRange(startRow, 10, DATA_ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(estados, true)
      .setAllowInvalid(false)
      .setHelpText('Estado actual del bien.')
      .build()
  );

  // L — borrado (checkbox)
  sheet.getRange(startRow, 12, DATA_ROWS, 1).insertCheckboxes();

  // ----------------------------------------------------------
  // 4. Formato de columnas numericas
  // ----------------------------------------------------------
  // E precio_ars — formato de moneda ARS sin simbolo (numero con separadores)
  sheet.getRange(startRow, 5, DATA_ROWS, 1).setNumberFormat('#,##0');

  // F cotizacion_usd_compra — 2 decimales
  sheet.getRange(startRow, 6, DATA_ROWS, 1).setNumberFormat('#,##0.00');

  // G precio_usd_compra — 2 decimales
  sheet.getRange(startRow, 7, DATA_ROWS, 1).setNumberFormat('#,##0.00');

  // H proporcion_jd — numero entero
  sheet.getRange(startRow, 8, DATA_ROWS, 1).setNumberFormat('0');

  // I precio_venta_estimado_usd — 2 decimales
  sheet.getRange(startRow, 9, DATA_ROWS, 1).setNumberFormat('#,##0.00');

  // D fecha_compra — formato de fecha
  sheet.getRange(startRow, 4, DATA_ROWS, 1).setNumberFormat('yyyy-mm-dd');

  // ----------------------------------------------------------
  // 5. Notas de encabezado para orientar al usuario
  // ----------------------------------------------------------
  sheet.getRange(1, 7).setNote(
    'precio_usd_compra: ingresar directamente o calcular como precio_ars / cotizacion_usd_compra.'
  );
  sheet.getRange(1, 8).setNote(
    'proporcion_jd: % del bien que le corresponde a JD (0-100). El % de Pinki = 100 - proporcion_jd.'
  );
  sheet.getRange(1, 9).setNote(
    'precio_venta_estimado_usd: estimacion subjetiva del precio de reventa actual en USD.'
  );

  SpreadsheetApp.flush();
  Logger.log('Setup completado. Hoja "Inventario" lista.');
  Logger.log('Proximos pasos:');
  Logger.log('  1. Ejecutar setupInventarioTrigger() para activar el auto-ID.');
  Logger.log('  2. Configurar AppSheet apuntando a esta Sheet.');
}

// ------------------------------------------------------------
// setupInventarioTrigger()
// Instala el trigger onChange que asigna ID automatico (INV-XXXXX)
// a cada fila nueva que no tenga ID.
// Ejecutar UNA SOLA VEZ desde el editor de Apps Script.
// ------------------------------------------------------------
function setupInventarioTrigger() {
  const ss = SpreadsheetApp.openById(INVENTARIO_SHEET_ID);

  // Eliminar triggers previos del mismo handler para evitar duplicados
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'onInventarioChange') {
      ScriptApp.deleteTrigger(trigger);
      Logger.log('Trigger previo eliminado.');
    }
  });

  ScriptApp.newTrigger('onInventarioChange')
    .forSpreadsheet(ss)
    .onChange()
    .create();

  Logger.log('Trigger onInventarioChange instalado correctamente.');
}

// ------------------------------------------------------------
// onInventarioChange(e)
// Handler del trigger: recorre la hoja Inventario y asigna
// INV-XXXXX a todas las filas con columna A vacia que tengan
// algun dato en columna B (descripcion) o posterior.
// ------------------------------------------------------------
function onInventarioChange(e) {
  const ss = e.source;
  const sheet = ss.getSheetByName(INVENTARIO_SHEET_NAME);
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  // Leer columnas A (id) y B (descripcion) en un solo batch
  const data = sheet.getRange(2, 1, lastRow - 1, 2).getValues();

  // Determinar el proximo numero de ID disponible
  // Busca el maximo existente entre los INV-XXXXX ya asignados
  let maxNum = 0;
  data.forEach(([id]) => {
    if (id && String(id).startsWith('INV-')) {
      const num = parseInt(String(id).replace('INV-', ''), 10);
      if (!isNaN(num) && num > maxNum) maxNum = num;
    }
  });

  // Asignar IDs a filas sin ID que tengan al menos descripcion
  data.forEach(([id, descripcion], i) => {
    const rowIndex = i + 2; // fila real en la Sheet (1-indexed, +1 por header)
    if (!id && descripcion) {
      maxNum++;
      const newId = 'INV-' + String(maxNum).padStart(5, '0');
      sheet.getRange(rowIndex, 1).setValue(newId);
      Logger.log('ID asignado: ' + newId + ' en fila ' + rowIndex);
    }
  });
}

// ------------------------------------------------------------
// testSetup() — funcion de prueba rapida
// Verifica que la hoja existe y muestra sus headers.
// ------------------------------------------------------------
function testSetup() {
  const ss = SpreadsheetApp.openById(INVENTARIO_SHEET_ID);
  const sheet = ss.getSheetByName(INVENTARIO_SHEET_NAME);
  if (!sheet) {
    Logger.log('ERROR: hoja "Inventario" no encontrada. Ejecutar setupInventarioSheet() primero.');
    return;
  }
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  Logger.log('Headers encontrados: ' + headers.join(' | '));
  Logger.log('Filas de datos: ' + (sheet.getLastRow() - 1));
}
