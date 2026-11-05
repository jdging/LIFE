/**
 * Tests del rediseño de "vencimientos de tarjeta" (mejora #6 de Juan,
 * rediseño 2026-11-05 por pedido explícito -- "no está muy didáctica" --
 * con revisión CPO/UX/CTO/front-end, ver docs/BITACORA.md).
 *
 * Cubre: el form ya no pide "mes" (se deriva de la fecha), el panel pinta
 * el RANGO de cada ciclo vía creditCycles() (no solo la fecha de cierre),
 * bloqueo de mes duplicado con mensaje específico, y confirm() antes de
 * borrar un vencimiento que no es el más reciente.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');

function cortar(desde, hasta) {
  const inicio = source.indexOf(desde);
  if (inicio === -1) throw new Error(`no encontré el marcador de inicio: ${desde}`);
  const fin = source.indexOf(hasta, inicio);
  if (fin === -1) throw new Error(`no encontré el marcador de fin: ${hasta}`);
  return source.slice(inicio, fin);
}

const VENCIMIENTOS_SCRIPT = [
  cortar('function creditCycles() {', 'function creditCycleForDate('),
  cortar('function renderVencimientosAdmin() {', '\nasync function saveTarjetaVencimiento'),
  cortar('async function saveTarjetaVencimiento(mes, vencimiento) {', '\nfunction renderCreditoDetail('),
].join('\n');

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function harness({ tarjetaVencimientos = [], confirmResult = true, fetchImpl } = {}) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', value: '', hidden: false, dataset: {},
      classList: { toggle() {} }, addEventListener() {}, focus() {} });
    return elements.get(id);
  };
  const confirmCalls = [];
  const context = vm.createContext({
    document: { getElementById: element, querySelectorAll: () => [] },
    escapeHtml, Number, String, Math,
    confirm: (msg) => { confirmCalls.push(msg); return confirmResult; },
    fetch: fetchImpl || (async () => { throw new Error('unexpected fetch'); }),
  });
  vm.runInContext(VENCIMIENTOS_SCRIPT, context);
  vm.runInContext(
    `DATA = { tarjetaVencimientos: ${JSON.stringify(tarjetaVencimientos)} }; liveMode = true; writePending = false;`,
    context,
  );
  return { context, element, confirmCalls };
}

test('el form de vencimientos ya no pide "mes" -- un solo input de fecha', () => {
  const { context } = harness({ tarjetaVencimientos: [] });
  const html = vm.runInContext('renderVencimientosAdmin()', context);
  assert.doesNotMatch(html, /id="vencimiento-mes"/, 'el campo Mes ya no debe existir en el DOM');
  assert.match(html, /id="vencimiento-fecha"/);
  assert.match(html, /¿Cuándo vence el próximo resumen\?/);
});

test('sin vencimientos cargados muestra el bloque de ejemplo, no solo una oración', () => {
  const { context } = harness({ tarjetaVencimientos: [] });
  const html = vm.runInContext('renderVencimientosAdmin()', context);
  assert.match(html, /credito-vencimientos-empty/);
  assert.match(html, /24\/10/);
  assert.match(html, /24\/11/);
});

test('con vencimientos cargados, la lista pinta el RANGO de cada ciclo (no solo la fecha de cierre)', () => {
  const { context } = harness({ tarjetaVencimientos: [
    { id: 1, mes: '2026-10', vencimiento: '2026-10-24' },
    { id: 2, mes: '2026-11', vencimiento: '2026-11-24' },
  ] });
  const html = vm.runInContext('renderVencimientosAdmin()', context);
  assert.match(html, /Desde siempre → 24 oct 2026/, 'primer ciclo sin piso: "Desde siempre"');
  assert.match(html, /24 oct → 24 nov 2026/, 'segundo ciclo muestra el rango completo');
  assert.match(html, /Vence el.*24\/10\/2026/s);
  assert.match(html, /Vence el.*24\/11\/2026/s);
});

test('cargar un vencimiento en un mes ya cargado se bloquea con mensaje específico (no un string genérico)', () => {
  const { context, element } = harness({ tarjetaVencimientos: [
    { id: 1, mes: '2026-11', vencimiento: '2026-11-24' },
  ] });
  element('vencimiento-fecha').value = '2026-11-30'; // mismo mes derivado, otro día
  const writes = [];
  context.saveTarjetaVencimiento = async (...args) => { writes.push(args); };
  context.loadLive = async () => {};
  context.renderCreditoDetail = () => {};
  vm.runInContext('handleVencimientoFormSubmit({ preventDefault(){} })', context);
  assert.equal(writes.length, 0, 'no debe llamar a la API si el mes ya está cargado');
  assert.match(element('vencimiento-form-error').textContent, /Ya hay un vencimiento cargado para ese mes \(24\/11\/2026\)/);
});

test('borrar el vencimiento más reciente no pide confirmación', async () => {
  const { context, confirmCalls } = harness({ tarjetaVencimientos: [
    { id: 1, mes: '2026-10', vencimiento: '2026-10-24' },
    { id: 2, mes: '2026-11', vencimiento: '2026-11-24' },
  ] });
  let borrado = null;
  context.deleteTarjetaVencimientoRequest = async (id) => { borrado = id; };
  context.loadLive = async () => {};
  context.renderCreditoDetail = () => {};
  await vm.runInContext('handleVencimientoDelete(2)', context); // el más reciente
  assert.equal(confirmCalls.length, 0);
  assert.equal(borrado, 2);
});

test('borrar un vencimiento que NO es el más reciente pide confirmación (recalcula ciclos posteriores)', async () => {
  const { context, confirmCalls } = harness({
    tarjetaVencimientos: [
      { id: 1, mes: '2026-10', vencimiento: '2026-10-24' },
      { id: 2, mes: '2026-11', vencimiento: '2026-11-24' },
    ],
    confirmResult: false,
  });
  let borrado = false;
  context.deleteTarjetaVencimientoRequest = async () => { borrado = true; };
  await vm.runInContext('handleVencimientoDelete(1)', context); // no es el más reciente
  assert.equal(confirmCalls.length, 1);
  assert.match(confirmCalls[0], /cambiar el ciclo de los vencimientos posteriores/);
  assert.equal(borrado, false, 'si el usuario cancela la confirmación, no borra nada');
});
