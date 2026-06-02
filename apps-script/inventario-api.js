/**
 * LIFE — Inventario: Apps Script API
 * Spreadsheet ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw
 *
 * Instrucciones de deploy:
 *   1. Abrí la Google Sheet de Inventario → Extensions > Apps Script
 *   2. Creá un archivo nuevo llamado "api" y pegá este código
 *   3. Deploy > New deployment > Web App
 *      - Execute as: Me
 *      - Who has access: Anyone
 *   4. Copiá la URL del deployment y pegala en src/inventario/index.html → constante API_URL
 *
 * Endpoints:
 *   GET ?action=inventario          → todos los ítems (excluye borrado=TRUE)
 *   GET ?action=delete&id=INV-XXXXX → soft delete
 */

const INV_SPREADSHEET_ID = '1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw';
const INV_SHEET_NAME = 'Inventario';

// ─── ROUTER ──────────────────────────────────────────────────────────────────

function doGet(e) {
  const action = e.parameter.action;
  let result;

  try {
    switch (action) {
      case 'inventario':
        result = getInventario();
        break;
      case 'delete':
        result = softDelete(e.parameter.id);
        break;
      default:
        result = { ok: false, error: 'Accion desconocida: ' + action };
    }
  } catch (err) {
    result = { ok: false, error: err.message };
  }

  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─── GET INVENTARIO ───────────────────────────────────────────────────────────

/**
 * Devuelve todos los ítems del inventario.
 * Excluye filas con borrado=TRUE.
 */
function getInventario() {
  const rows = getSheetData(INV_SHEET_NAME);
  const data = rows.filter(r => r.borrado !== true && String(r.borrado).toUpperCase() !== 'TRUE');
  return { ok: true, count: data.length, data };
}

// ─── SOFT DELETE ─────────────────────────────────────────────────────────────

/**
 * Marca borrado=TRUE en la fila con id=id.
 */
function softDelete(id) {
  if (!id) return { ok: false, error: 'Falta el parametro id' };

  const ss    = SpreadsheetApp.openById(INV_SPREADSHEET_ID);
  const sheet = ss.getSheetByName(INV_SHEET_NAME);
  const data  = sheet.getDataRange().getValues();
  const headers = data[0];

  const idCol      = headers.indexOf('id');
  const borradoCol = headers.indexOf('borrado');

  if (idCol === -1 || borradoCol === -1) {
    return { ok: false, error: 'No se encontraron las columnas id o borrado' };
  }

  for (let i = 1; i < data.length; i++) {
    if (data[i][idCol] === id) {
      sheet.getRange(i + 1, borradoCol + 1).setValue(true);
      return { ok: true, id, row: i + 1 };
    }
  }

  return { ok: false, error: 'No se encontro ninguna entrada con id: ' + id };
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Lee una hoja y devuelve array de objetos usando la primera fila como keys.
 * Convierte fechas a string YYYY-MM-DD.
 */
function getSheetData(sheetName) {
  const ss    = SpreadsheetApp.openById(INV_SPREADSHEET_ID);
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) throw new Error('Hoja no encontrada: ' + sheetName);

  const data    = sheet.getDataRange().getValues();
  const headers = data[0];
  const rows    = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    if (row.every(cell => cell === '' || cell === null || cell === undefined)) continue;

    const obj = {};
    headers.forEach((header, j) => {
      let val = row[j];
      if (val instanceof Date) {
        val = Utilities.formatDate(val, Session.getScriptTimeZone(), 'yyyy-MM-dd');
      }
      obj[header] = val === '' ? null : val;
    });

    rows.push(obj);
  }

  return rows;
}

// ─── TEST LOCAL ───────────────────────────────────────────────────────────────

function testGetInventario() { Logger.log(JSON.stringify(getInventario())); }
