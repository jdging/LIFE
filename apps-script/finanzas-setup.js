/**
 * LIFE — Finanzas: Setup inicial de Google Sheet
 *
 * Instrucciones:
 *   1. Abrí una Google Sheet nueva (dale el nombre que quieras, ej: "LIFE - Finanzas")
 *   2. Extensions > Apps Script
 *   3. Borrá el contenido del editor y pegá este archivo completo
 *   4. Guardá (Ctrl+S) y ejecutá la función: setupFinanzasSheet()
 *   5. La primera vez te va a pedir permisos — aceptalos
 *   6. Listo: vas a ver las 4 hojas creadas con toda la estructura
 *
 * IMPORTANTE: Solo ejecutar UNA vez. Si volvés a ejecutar, borra y recrea todo.
 */

function setupFinanzasSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  setupConfig(ss);
  setupTarjetas(ss);
  setupCategorias(ss);
  setupLog(ss);

  // Eliminar hoja vacía por defecto si quedó
  ['Sheet1', 'Hoja 1', 'Hoja1'].forEach(name => {
    const s = ss.getSheetByName(name);
    if (s && ss.getSheets().length > 1) ss.deleteSheet(s);
  });

  // Ir a la hoja Log al terminar
  ss.setActiveSheet(ss.getSheetByName('Log'));

  SpreadsheetApp.flush();
  SpreadsheetApp.getUi().alert('✅ LIFE Finanzas — Sheet configurada correctamente.\n\nHojas creadas: Config, Tarjetas, Categorías, Log.');
}


// ─── CONFIG ──────────────────────────────────────────────────────────────────

function setupConfig(ss) {
  let sheet = ss.getSheetByName('Config');
  if (!sheet) sheet = ss.insertSheet('Config');
  sheet.clear();
  sheet.clearConditionalFormatRules();

  const data = [
    ['Campo',          'Valor'],
    ['nombre_persona1', 'JD'],
    ['nombre_persona2', 'Pinki'],
    ['moneda',          'ARS'],
  ];

  sheet.getRange(1, 1, data.length, 2).setValues(data);

  styleHeader(sheet.getRange(1, 1, 1, 2));
  sheet.setColumnWidth(1, 220);
  sheet.setColumnWidth(2, 180);
  sheet.setFrozenRows(1);
  sheet.setTabColor('#4a86e8');

  // Nota aclaratoria
  sheet.getRange(6, 1).setValue('// Los salarios NO van acá. La proporción se calcula dinámicamente desde el Log.');
  sheet.getRange(6, 1).setFontColor('#888888').setFontStyle('italic');
}


// ─── TARJETAS ────────────────────────────────────────────────────────────────

function setupTarjetas(ss) {
  let sheet = ss.getSheetByName('Tarjetas');
  if (!sheet) sheet = ss.insertSheet('Tarjetas');
  sheet.clear();
  sheet.clearConditionalFormatRules();

  const headers = ['id', 'nombre', 'tipo', 'banco', 'titular', 'dia_cierre', 'dia_vencimiento'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  styleHeader(sheet.getRange(1, 1, 1, headers.length));

  const ROWS = 100;

  // tipo: Crédito / Débito
  sheet.getRange(2, 3, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Crédito', 'Débito'], true)
      .setAllowInvalid(false)
      .setHelpText('Seleccioná el tipo de tarjeta')
      .build()
  );

  // titular: JD / Pinki
  sheet.getRange(2, 5, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['JD', 'Pinki'], true)
      .setAllowInvalid(false)
      .build()
  );

  // dia_cierre y dia_vencimiento: 1–31
  const diaRule = SpreadsheetApp.newDataValidation()
    .requireNumberBetween(1, 31)
    .setAllowInvalid(false)
    .setHelpText('Ingresá un día entre 1 y 31')
    .build();
  sheet.getRange(2, 6, ROWS, 2).setDataValidation(diaRule);

  const widths = [80, 160, 100, 160, 100, 110, 140];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.setFrozenRows(1);
  sheet.setTabColor('#6aa84f');
}


// ─── CATEGORÍAS ──────────────────────────────────────────────────────────────

function setupCategorias(ss) {
  let sheet = ss.getSheetByName('Categorías');
  if (!sheet) sheet = ss.insertSheet('Categorías');
  sheet.clear();
  sheet.clearConditionalFormatRules();

  const headers = ['tipo', 'categoria', 'subcategoria'];
  sheet.getRange(1, 1, 1, 3).setValues([headers]);
  styleHeader(sheet.getRange(1, 1, 1, 3));

  // Todas las filas de categorías/subcategorías
  const data = [
    // ── Gastos ──
    ['Gasto', 'Hogar',           'Alquiler'],
    ['Gasto', 'Hogar',           'Expensas'],
    ['Gasto', 'Hogar',           'Electricidad'],
    ['Gasto', 'Hogar',           'Gas'],
    ['Gasto', 'Hogar',           'Internet'],
    ['Gasto', 'Hogar',           'Ferretería'],
    ['Gasto', 'Hogar',           'Decoración'],
    ['Gasto', 'Hogar',           'Limpieza'],
    ['Gasto', 'Hogar',           'Mantenimiento'],
    ['Gasto', 'Comida',          'Supermercado'],
    ['Gasto', 'Comida',          'Verdulería'],
    ['Gasto', 'Comida',          'Carnicería'],
    ['Gasto', 'Comida',          'Delivery'],
    ['Gasto', 'Comida',          'Almacén'],
    ['Gasto', 'Entretenimiento', 'Restaurantes'],
    ['Gasto', 'Entretenimiento', 'Bares'],
    ['Gasto', 'Entretenimiento', 'Cine/Teatro'],
    ['Gasto', 'Entretenimiento', 'Streaming'],
    ['Gasto', 'Entretenimiento', 'Eventos'],
    ['Gasto', 'Transporte',      'Nafta'],
    ['Gasto', 'Transporte',      'Peajes'],
    ['Gasto', 'Transporte',      'SUBE'],
    ['Gasto', 'Transporte',      'Mantenimiento vehículo'],
    ['Gasto', 'Salud',           'Obra social'],
    ['Gasto', 'Salud',           'Farmacia'],
    ['Gasto', 'Salud',           'Consultas'],
    ['Gasto', 'Personal',        'Ropa'],
    ['Gasto', 'Personal',        'Cuidado personal'],
    ['Gasto', 'Personal',        'Educación'],
    ['Gasto', 'Mascotas',        'Veterinaria'],
    ['Gasto', 'Mascotas',        'Alimento'],
    // ── Inversiones ──
    ['Inversión', 'Inversión',   'Plazo fijo'],
    ['Inversión', 'Inversión',   'FCI'],
    ['Inversión', 'Inversión',   'Dólar/MEP'],
    ['Inversión', 'Inversión',   'Crypto'],
    ['Inversión', 'Inversión',   'Otro'],
    // ── Ingresos ──
    ['Ingreso', 'Ingreso',       'Salario'],
    ['Ingreso', 'Ingreso',       'Extra'],
    ['Ingreso', 'Ingreso',       'Freelance'],
    ['Ingreso', 'Ingreso',       'Otro'],
  ];

  sheet.getRange(2, 1, data.length, 3).setValues(data);

  // Validación en col A
  sheet.getRange(2, 1, 100, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Gasto', 'Inversión', 'Ingreso'], true)
      .setAllowInvalid(false)
      .build()
  );

  // Named range para que el API lo use fácil
  ss.setNamedRange('CATEGORIAS_DATA', sheet.getRange(2, 1, data.length, 3));

  const widths = [100, 180, 220];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.setFrozenRows(1);
  sheet.setTabColor('#e69138');
}


// ─── LOG ─────────────────────────────────────────────────────────────────────

function setupLog(ss) {
  let sheet = ss.getSheetByName('Log');
  if (!sheet) sheet = ss.insertSheet('Log');
  sheet.clear();
  sheet.clearConditionalFormatRules();

  const headers = [
    'id',           // A — LOG-00001
    'fecha',        // B — Date YYYY-MM-DD
    'tipo',         // C — Gasto / Ingreso / Inversión
    'categoria',    // D — según tipo
    'subcategoria', // E — según categoría
    'descripcion',  // F — texto libre
    'monto_total',  // G — número
    'cuotas_total', // H — default 1
    'cuota_nro',    // I — 1 si sin cuotas
    'cuota_ref',    // J — id de la fila original (vincula cuotas)
    'medio_pago',   // K — Crédito / Débito / Efectivo / Transferencia
    'tarjeta',      // L — id de tarjeta (solo si K = Crédito o Débito)
    'pago',         // M — Común / JD / Pinki
    'es_fijo',      // N — checkbox (gastos recurrentes)
    'notas',           // O — texto libre
    'borrado',         // P — checkbox (soft delete, default FALSE)
    'tipo_proporcion', // Q — "dinamica" / "50/50" / "custom" (F-04)
    'proporcion_jd',   // R — número 0-100, solo cuando tipo_proporcion = "custom"
    'corresponde_a',   // S — Común / JD / Pinki: a quién corresponde el gasto (H4)
  ];

  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  styleHeader(sheet.getRange(1, 1, 1, headers.length));

  const ROWS = 2000; // reservar filas para datos

  // C — tipo
  sheet.getRange(2, 3, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Gasto', 'Ingreso', 'Inversión'], true)
      .setAllowInvalid(false)
      .build()
  );

  // K — medio_pago
  sheet.getRange(2, 11, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Crédito', 'Débito', 'Efectivo', 'Transferencia'], true)
      .setAllowInvalid(false)
      .build()
  );

  // M — pagó
  sheet.getRange(2, 13, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Común', 'JD', 'Pinki'], true)
      .setAllowInvalid(false)
      .build()
  );

  // S — corresponde_a (H4): a quién corresponde el gasto
  sheet.getRange(2, 19, ROWS, 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['Común', 'JD', 'Pinki'], true)
      .setAllowInvalid(false)
      .build()
  );

  // N — es_fijo (checkbox)
  sheet.getRange(2, 14, ROWS, 1).insertCheckboxes();

  // P — borrado (checkbox, soft delete)
  sheet.getRange(2, 16, ROWS, 1).insertCheckboxes();

  // B — formato fecha
  sheet.getRange(2, 2, ROWS, 1).setNumberFormat('yyyy-mm-dd');

  // G, H, I — formato número
  sheet.getRange(2, 7, ROWS, 1).setNumberFormat('#,##0.00');  // monto_total
  sheet.getRange(2, 8, ROWS, 2).setNumberFormat('0');         // cuotas_total, cuota_nro

  // Formato condicional: filas borradas en gris
  const deletedRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$P2=TRUE')
    .setFontColor('#666666')
    .setBackground('#1a1a1a')
    .setRanges([sheet.getRange(2, 1, ROWS, headers.length)])
    .build();
  sheet.setConditionalFormatRules([deletedRule]);

  // Congelar header y primera columna
  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(1);

  const widths = [100, 110, 100, 140, 190, 220, 130, 105, 100, 120, 130, 120, 80, 72, 210, 72, 120, 100, 100];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  sheet.setTabColor('#cc0000');
}


// ─── HELPERS ─────────────────────────────────────────────────────────────────

function styleHeader(range) {
  range
    .setBackground('#1a1a2e')
    .setFontColor('#8fb87a')
    .setFontWeight('bold')
    .setHorizontalAlignment('left')
    .setBorder(
      false, false, true, false, false, false,
      '#8fb87a',
      SpreadsheetApp.BorderStyle.SOLID_MEDIUM
    );
}
