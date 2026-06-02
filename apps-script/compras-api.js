/**
 * LIFE — Compras: Apps Script API
 *
 * Qué hace: expone los datos de ListaCompras como JSON para el dashboard.
 * Por qué: mismo patrón que inventario-api.js — Apps Script Web App pública
 *   sin auth, 100% gratuito, dentro del ecosistema Google.
 *
 * Instrucciones de deploy:
 *   1. Abrí la Google Sheet de Compras → Extensions > Apps Script
 *   2. Creá un archivo nuevo llamado "api" y pegá este código
 *   3. Deploy > New deployment > Web App
 *      - Execute as: Me
 *      - Who has access: Anyone
 *   4. Copiá la URL y pegala en src/compras/index.html → constante API_URL
 *
 * IMPORTANTE: Si modificás este archivo, siempre creá un NEW deployment
 *   (no editues el existente). La URL del deployment cambia con cada versión.
 *
 * Endpoints:
 *   GET ?action=lista                              → todos los ítems no borrados
 *   GET ?action=add&nombre=X&cantidad=1&unidad=u
 *       &categoria=X&urgente=false&origen=manual&notas=
 *                                                  → agrega o suma cantidad (dedup)
 *   GET ?action=comprado&id=COMP-XXXXX             → marca estado=comprado
 *   GET ?action=delete&id=COMP-XXXXX               → soft delete (borrado=TRUE)
 *   GET ?action=limpiar                            → borra todos los comprados
 *   GET ?action=enviar                             → envía email con la lista
 */

// ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

// TODO: reemplazar con el ID del Spreadsheet de Compras + Recetario
const COMPRAS_SS_ID    = '1yW2qy_COYbiP3D-Mq_Z_N7aAcnepyWnRaA2Xkux4Ajk';
const COMPRAS_LISTA    = 'ListaCompras';

// Destinatarios del email de lista (DEC-B2)
const EMAIL_DESTINATARIOS = ['juandavidguzman96@gmail.com', 'regipinche@gmail.com'];

// Orden de categorías optimizado para recorrer el super de corrido
const ORDEN_CATEGORIAS =  ['Verduras', 'Carnes', 'Lácteos', 'Panadería',
                          'Almacén', 'Bebidas', 'Limpieza', 'Congelados', 
                          'Higiene personal', 'Perfumería/Cosmético', 'Fiambrería', 
                          'Mascotas', 'Frutas', 'Otro'];


// ─── ROUTER ──────────────────────────────────────────────────────────────────

function doGet(e) {
  const action = (e.parameter.action || '').toLowerCase();
  let result;

  try {
    switch (action) {
      case 'lista':
        result = getLista();
        break;
      case 'add':
        result = addItem(e.parameter);
        break;
      case 'comprado':
        result = marcarComprado(e.parameter.id);
        break;
      case 'delete':
        result = softDelete(e.parameter.id);
        break;
      case 'limpiar':
        result = limpiarComprados();
        break;
      case 'enviar':
        result = enviarLista();
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
 * Retorna todos los ítems con borrado=FALSE.
 * Orden: urgente DESC, luego por categoría (según ORDEN_CATEGORIAS), luego nombre ASC.
 */
function getLista() {
  const rows = getSheetData(COMPRAS_LISTA)
    .filter(r => r.borrado !== true && String(r.borrado).toUpperCase() !== 'TRUE');

  rows.sort((a, b) => {
    // 1. Urgente primero
    const urgA = a.urgente === true || String(a.urgente).toUpperCase() === 'TRUE';
    const urgB = b.urgente === true || String(b.urgente).toUpperCase() === 'TRUE';
    if (urgA !== urgB) return urgA ? -1 : 1;

    // 2. Por categoría según orden del super
    const catA = ORDEN_CATEGORIAS.indexOf(a.categoria);
    const catB = ORDEN_CATEGORIAS.indexOf(b.categoria);
    const iA   = catA === -1 ? 99 : catA;
    const iB   = catB === -1 ? 99 : catB;
    if (iA !== iB) return iA - iB;

    // 3. Nombre alfabético dentro de la categoría
    return String(a.nombre || '').localeCompare(String(b.nombre || ''));
  });

  return { ok: true, count: rows.length, data: rows };
}

// ─── ADD ITEM (con deduplicación — DEC-B2) ───────────────────────────────────

/**
 * Agrega un ítem a la lista, o suma la cantidad si ya existe uno pendiente
 * con el mismo nombre + unidad (case-insensitive).
 *
 * Parámetros esperados: nombre, cantidad, unidad, categoria, urgente, origen, notas
 */
function addItem(params) {
  const nombre    = String(params.nombre    || '').trim();
  const unidad    = String(params.unidad    || 'u').trim();
  const cantidad  = parseFloat(params.cantidad) || 1;
  const categoria = String(params.categoria || 'Otro').trim();
  const urgente   = params.urgente === 'true' || params.urgente === true;
  const origen    = String(params.origen    || 'manual').trim();
  const notas     = String(params.notas     || '').trim();

  if (!nombre) return { ok: false, error: 'Falta el parametro nombre' };

  const ss    = SpreadsheetApp.openById(COMPRAS_SS_ID);
  const sheet = ss.getSheetByName(COMPRAS_LISTA);
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];

  const col = name => hdr.indexOf(name);

  // === Deduplicación: buscar ítem existente con mismo nombre+unidad+pendiente+no-borrado ===
  for (let i = 1; i < data.length; i++) {
    const row      = data[i];
    const rNombre  = String(row[col('nombre')]  || '').trim().toLowerCase();
    const rUnidad  = String(row[col('unidad')]  || '').trim().toLowerCase();
    const rEstado  = String(row[col('estado')]  || '').toLowerCase();
    const rBorrado = row[col('borrado')] === true || String(row[col('borrado')]).toUpperCase() === 'TRUE';

    if (
      rNombre  === nombre.toLowerCase() &&
      rUnidad  === unidad.toLowerCase() &&
      rEstado  === 'pendiente' &&
      !rBorrado
    ) {
      // Existe: sumar la cantidad
      const cantActual = parseFloat(row[col('cantidad')]) || 0;
      sheet.getRange(i + 1, col('cantidad') + 1).setValue(cantActual + cantidad);
      const id = String(row[col('id')]);
      return { ok: true, status: 'updated', id, cantidad_nueva: cantActual + cantidad };
    }
  }

  // No existe: insertar fila nueva
  // Generar ID correlativo
  let maxId = 0;
  for (let i = 1; i < data.length; i++) {
    const val = String(data[i][col('id')] || '');
    if (val.startsWith('COMP-')) {
      const num = parseInt(val.replace('COMP-', ''), 10);
      if (!isNaN(num) && num > maxId) maxId = num;
    }
  }
  const newId = 'COMP-' + String(maxId + 1).padStart(5, '0');

  // Construir fila en el orden del schema
  const newRow = new Array(hdr.length).fill('');
  newRow[col('id')]        = newId;
  newRow[col('nombre')]    = nombre;
  newRow[col('cantidad')]  = cantidad;
  newRow[col('unidad')]    = unidad;
  newRow[col('categoria')] = categoria;
  newRow[col('urgente')]   = urgente;
  newRow[col('estado')]    = 'pendiente';
  newRow[col('origen')]    = origen;
  newRow[col('notas')]     = notas;
  newRow[col('borrado')]   = false;

 //// Buscar la primera fila disponible real (ignorando filas que solo tengan checkboxes)
 let insertRowIndex = data.length + 1;
 for (let i = 1; i < data.length; i++) {
  if (!data[i][col('id')] && !data[i][col('nombre')]) {
    insertRowIndex = i + 1;
    break;
  }
  }
 sheet.getRange(insertRowIndex, 1, 1, newRow.length).setValues([newRow]);
  return { ok: true, status: 'created', id: newId };
}

// ─── MARCAR COMPRADO ─────────────────────────────────────────────────────────

/**
 * Cambia estado a 'comprado' en la fila con el id dado.
 */
function marcarComprado(id) {
  return setFieldById(id, 'estado', 'comprado');
}

// ─── SOFT DELETE ─────────────────────────────────────────────────────────────

/**
 * Marca borrado=TRUE en la fila con el id dado.
 */
function softDelete(id) {
  return setFieldById(id, 'borrado', true);
}

// ─── LIMPIAR COMPRADOS ───────────────────────────────────────────────────────

/**
 * Marca borrado=TRUE en todos los ítems con estado='comprado'.
 * Equivalente a "vaciar el carrito" después de hacer las compras.
 * Retorna cuántos ítems se limpiaron.
 */
function limpiarComprados() {
  const ss    = SpreadsheetApp.openById(COMPRAS_SS_ID);
  const sheet = ss.getSheetByName(COMPRAS_LISTA);
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];

  const estadoCol  = hdr.indexOf('estado');
  const borradoCol = hdr.indexOf('borrado');
  if (estadoCol === -1 || borradoCol === -1) {
    return { ok: false, error: 'Columnas estado o borrado no encontradas' };
  }

  let count = 0;
  for (let i = 1; i < data.length; i++) {
    const estado  = String(data[i][estadoCol]  || '').toLowerCase();
    const borrado = data[i][borradoCol] === true || String(data[i][borradoCol]).toUpperCase() === 'TRUE';
    if (estado === 'comprado' && !borrado) {
      sheet.getRange(i + 1, borradoCol + 1).setValue(true);
      count++;
    }
  }

  return { ok: true, status: 'ok', count };
}

// ─── ENVIAR LISTA ─────────────────────────────────────────────────────────────

/**
 * Envía la lista de pendientes por email a los destinatarios configurados.
 * Formato: agrupado por categoría (orden del super), urgentes en negrita.
 * Asunto: "🛒 Lista del super — DD/MM/YYYY"
 */
function enviarLista() {
  const rows = getSheetData(COMPRAS_LISTA)
    .filter(r => {
      const borrado = r.borrado === true || String(r.borrado).toUpperCase() === 'TRUE';
      const estado  = String(r.estado || '').toLowerCase();
      return !borrado && estado === 'pendiente';
    });

  if (rows.length === 0) {
    return { ok: false, error: 'No hay ítems pendientes para enviar' };
  }

  // Agrupar por categoría en el orden del super
  const grupos = {};
  ORDEN_CATEGORIAS.forEach(c => { grupos[c] = []; });

  rows.forEach(r => {
    const cat = ORDEN_CATEGORIAS.includes(r.categoria) ? r.categoria : 'Otro';
    grupos[cat].push(r);
  });

  // Ordenar dentro de cada grupo: urgentes primero, luego alfabético
  Object.keys(grupos).forEach(cat => {
    grupos[cat].sort((a, b) => {
      const urgA = a.urgente === true || String(a.urgente).toUpperCase() === 'TRUE';
      const urgB = b.urgente === true || String(b.urgente).toUpperCase() === 'TRUE';
      if (urgA !== urgB) return urgA ? -1 : 1;
      return String(a.nombre || '').localeCompare(String(b.nombre || ''));
    });
  });

  // Formatear fecha
  const hoy    = new Date();
  const fecha  = Utilities.formatDate(hoy, Session.getScriptTimeZone(), 'dd/MM/yyyy');
  const asunto = '🛒 Lista del super — ' + fecha;

  // Construir cuerpo texto plano y HTML
  let textoPlano = asunto + '\n\n';
  let html       = '<h2 style="font-family:sans-serif;color:#333">🛒 Lista del super — ' + fecha + '</h2>';

  ORDEN_CATEGORIAS.forEach(cat => {
    const items = grupos[cat];
    if (!items.length) return;

    textoPlano += cat.toUpperCase() + '\n';
    html += '<h3 style="font-family:sans-serif;color:#555;margin-top:1.5em">' + cat + '</h3>';
    html += '<ul style="font-family:monospace;line-height:1.8">';

    items.forEach(item => {
      const urgente = item.urgente === true || String(item.urgente).toUpperCase() === 'TRUE';
      const cant    = parseFloat(item.cantidad) || 1;
      const linea   = '• ' + cant + ' ' + (item.unidad || 'u') + '  ' + (item.nombre || '');
      const origen  = (item.origen && item.origen !== 'manual') ? '  [' + item.origen + ']' : '';
      const notas   = item.notas ? '  (' + item.notas + ')' : '';

      textoPlano += (urgente ? '⚡ ' : '  ') + linea + origen + notas + '\n';

      const estilo = urgente
        ? 'font-weight:bold;color:#c0392b'
        : 'color:#333';
      html += '<li style="' + estilo + '">' + cant + ' ' + (item.unidad || 'u') + '  <strong>' + (item.nombre || '') + '</strong>';
      if (origen) html += ' <span style="color:#888;font-size:0.85em">' + origen + '</span>';
      if (notas)  html += '<br><span style="color:#aaa;font-size:0.8em">' + notas + '</span>';
      html += '</li>';
    });

    html       += '</ul>';
    textoPlano += '\n';
  });

  textoPlano += '\n— Enviado desde LIFE';
  html       += '<p style="font-family:sans-serif;color:#aaa;font-size:0.8em;margin-top:2em">— Enviado desde LIFE</p>';

  // Enviar a todos los destinatarios
  EMAIL_DESTINATARIOS.forEach(email => {
    MailApp.sendEmail({
      to:       email,
      subject:  asunto,
      body:     textoPlano,
      htmlBody: html,
    });
  });

  return { ok: true, status: 'ok', count: rows.length, destinatarios: EMAIL_DESTINATARIOS };
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Busca una fila por id y actualiza un campo.
 * Helper compartido por marcarComprado y softDelete.
 */
function setFieldById(id, field, value) {
  if (!id) return { ok: false, error: 'Falta el parametro id' };

  const ss    = SpreadsheetApp.openById(COMPRAS_SS_ID);
  const sheet = ss.getSheetByName(COMPRAS_LISTA);
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];

  const idCol    = hdr.indexOf('id');
  const fieldCol = hdr.indexOf(field);

  if (idCol === -1)    return { ok: false, error: 'Columna id no encontrada' };
  if (fieldCol === -1) return { ok: false, error: 'Columna ' + field + ' no encontrada' };

  for (let i = 1; i < data.length; i++) {
    if (data[i][idCol] === id) {
      sheet.getRange(i + 1, fieldCol + 1).setValue(value);
      return { ok: true, status: 'ok', id };
    }
  }

  return { ok: false, error: 'No se encontro ningun item con id: ' + id };
}

/**
 * Lee una hoja y devuelve array de objetos.
 * Primera fila = keys. Omite filas completamente vacías.
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
function testAddItem()    { Logger.log(JSON.stringify(addItem({ nombre: 'Leche', cantidad: '2', unidad: 'l', categoria: 'Lácteos', urgente: 'false', origen: 'manual', notas: '' }))); }
function testLimpiar()    { Logger.log(JSON.stringify(limpiarComprados())); }
