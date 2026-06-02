/**
 * LIFE — Recetario: Apps Script API (solo lectura)
 *
 * Qué hace: expone los datos de Recetas e Ingredientes como JSON para el dashboard.
 *   La escritura (agregar recetas/ingredientes) se hace desde AppSheet.
 *   El agregado al super se hace desde el dashboard llamando a compras-api.js.
 *
 * Instrucciones de deploy:
 *   1. Abrí el Spreadsheet de Compras → Extensions > Apps Script
 *   2. Creá un archivo nuevo llamado "recetario-api" y pegá este código
 *   3. Deploy > New deployment > Web App
 *      - Execute as: Me
 *      - Who has access: Anyone
 *   4. Copiá la URL y pegala en src/recetario/index.html → constante RECETARIO_API_URL
 *
 * IMPORTANTE: Cambios al código requieren NEW deployment (la URL cambia).
 *
 * Endpoints:
 *   GET ?action=lista            → todas las recetas con borrado=FALSE, orden categoria+nombre
 *   GET ?action=detalle&id=RECETA-XXXXX → receta + sus ingredientes (join por receta_id)
 */

// ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

// Mismo ID que en compras-setup.js y compras-api.js
const COMPRAS_SS_ID_R         = '1yW2qy_COYbiP3D-Mq_Z_N7aAcnepyWnRaA2Xkux4Ajk';
const RECETAS_SHEET           = 'Recetas';
const INGREDIENTES_SHEET      = 'Ingredientes';

// ─── ROUTER ──────────────────────────────────────────────────────────────────

function doGet(e) {
  const action = (e.parameter.action || '').toLowerCase();
  let result;

  try {
    switch (action) {
      case 'lista':
        result = getLista();
        break;
      case 'detalle':
        result = getDetalle(e.parameter.id);
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

// ─── GET LISTA ────────────────────────────────────────────────────────────────

/**
 * Retorna todas las recetas con borrado=FALSE.
 * Orden: categoria ASC, luego nombre ASC.
 * No incluye ingredientes (para evitar payloads grandes en el listado).
 */
function getLista() {
  const rows = getSheetData(RECETAS_SHEET)
    .filter(r => r.borrado !== true && String(r.borrado).toUpperCase() !== 'TRUE');

  rows.sort((a, b) => {
    const catCmp = String(a.categoria || '').localeCompare(String(b.categoria || ''));
    if (catCmp !== 0) return catCmp;
    return String(a.nombre || '').localeCompare(String(b.nombre || ''));
  });

  return { ok: true, count: rows.length, data: rows };
}

// ─── GET DETALLE ─────────────────────────────────────────────────────────────

/**
 * Retorna una receta específica junto con sus ingredientes.
 * Join: Ingredientes.receta_id === Recetas.id
 * Excluye ingredientes con borrado=TRUE.
 *
 * Response shape:
 * {
 *   ok: true,
 *   receta: { id, nombre, porciones_base, categoria, instrucciones, borrado },
 *   ingredientes: [{ id, receta_id, nombre, cantidad, unidad }, ...]
 * }
 */
function getDetalle(id) {
  if (!id) return { ok: false, error: 'Falta el parametro id' };

  // Buscar la receta
  const recetas = getSheetData(RECETAS_SHEET);
  const receta  = recetas.find(r => r.id === id);

  if (!receta) return { ok: false, error: 'Receta no encontrada: ' + id };
  if (receta.borrado === true || String(receta.borrado).toUpperCase() === 'TRUE') {
    return { ok: false, error: 'Receta borrada: ' + id };
  }

  // Buscar sus ingredientes (join por receta_id)
  const ingredientes = getSheetData(INGREDIENTES_SHEET)
    .filter(r => {
      const borrado = r.borrado === true || String(r.borrado).toUpperCase() === 'TRUE';
      return r.receta_id === id && !borrado;
    });

  // Asegurar que porciones_base sea número
  receta.porciones_base = parseFloat(receta.porciones_base) || 1;

  // Asegurar que cantidad sea número en cada ingrediente
  ingredientes.forEach(ing => {
    ing.cantidad = parseFloat(ing.cantidad) || 0;
  });

  return { ok: true, receta, ingredientes };
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Lee una hoja y devuelve array de objetos.
 * Versión robusta: normaliza cabeceras y filtra filas sin ID/Nombre.
 */
function getSheetData(sheetName) {
  const ss    = SpreadsheetApp.openById(COMPRAS_SS_ID);
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) throw new Error('Hoja no encontrada: ' + sheetName);

  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return []; // Solo hay cabeceras o la hoja está vacía

  // Normalizar cabeceras (quitar espacios extra y pasar a minúscula) para evitar desajustes
  const headers = data[0].map(h => String(h || '').trim().toLowerCase());
  const rows = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const obj = {};

    headers.forEach((header, j) => {
      if (!header) return; // Saltar columnas sin título
      let val = row[j];
      if (val instanceof Date) {
        val = Utilities.formatDate(val, Session.getScriptTimeZone(), 'yyyy-MM-dd');
      }
      obj[header] = val === '' ? null : val;
    });

    // Validación estricta: la fila DEBE tener un ID o un nombre válido.
    // Si ambos están vacíos, se asume que es una fila en blanco o con restos de checkboxes.
    const tieneId = obj.id && String(obj.id).trim() !== '';
    const tieneNombre = obj.nombre && String(obj.nombre).trim() !== '';

    if (!tieneId && !tieneNombre) continue;

    rows.push(obj);
  }

  return rows;
}

// ─── TEST LOCAL ───────────────────────────────────────────────────────────────

function testGetLista()   { Logger.log(JSON.stringify(getLista())); }
function testGetDetalle() { Logger.log(JSON.stringify(getDetalle('RECETA-00001'))); }
