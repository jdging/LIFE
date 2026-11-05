import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Todos los registros de este archivo son SINTÉTICOS. No se llama a la API real
// de dolarapi.com en ningún test; fetch está mockeado siempre.
const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const slice = (from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `No se encontró el bloque ${from}`);
  return source.slice(start, end);
};

// Mismo rango que usa forms.test.mjs para collectForm: incluye validMoney,
// normalizeDecimalInput, el cache/fetch del dólar oficial y collectForm.
const moneyBlock = slice('function validMoney(', 'function routeForForm(');

function buildContext({ fetchImpl, elements = {} } = {}) {
  const elementStore = new Map(Object.entries(elements));
  const document = {
    getElementById: (id) => elementStore.get(id) || null,
  };
  const sandbox = {
    document,
    fetch: fetchImpl || (async () => { throw new Error('fetch no mockeado en este test'); }),
    Number, String, Math, Date,
    fmtARSExact: (n) => '$' + Number(n).toFixed(2),
    fmtUSD: (n) => 'U$D ' + Number(n).toFixed(2),
    console,
  };
  runInNewContext(moneyBlock, sandbox);
  return sandbox;
}

test('collectForm convierte USD a ARS con la cotización oficial cacheada y deja traza en la descripción', async () => {
  const ctx = buildContext({ fetchImpl: async () => ({ ok: true, json: async () => ({ venta: 1000 }) }) });
  await ctx.fetchDolarOficialVenta(); // deja DOLAR_OFICIAL_CACHE poblado, como lo hace updateExpenseMonedaHint en vivo
  const values = {
    fecha: '2026-11-05', monto: '10', moneda_ingreso: 'USD', categoria: 'Hogar', subcategoria: '',
    descripcion_original: 'Compra online', medio_pago: 'Débito', pagado_por: 'Común',
    tipo_proporcion: 'dinamico', cuotas_total: '1',
  };
  const { payload, errors } = ctx.collectForm('expense', null, values);
  assert.equal(Object.keys(errors).length, 0);
  assert.equal(payload.monto, 10000, 'USD 10 a cotización 1000 debe guardarse como ARS 10000');
  assert.match(payload.descripcion_original, /\[USD 10 @ \$1000 oficial\]/);
});

test('collectForm bloquea el envío en USD si no hay cotización oficial fresca', () => {
  const ctx = buildContext();
  const values = {
    fecha: '2026-11-05', monto: '10', moneda_ingreso: 'USD', categoria: 'Hogar', subcategoria: '',
    descripcion_original: '', medio_pago: 'Débito', pagado_por: 'Común',
    tipo_proporcion: 'dinamico', cuotas_total: '1',
  };
  const { payload, errors } = ctx.collectForm('expense', null, values);
  assert.ok(errors.monto, 'Sin cotización fresca debe marcar error en monto, no guardar a mitad de convertir');
  assert.equal(payload.monto, 10, 'Sin cotización válida el monto no debe convertirse a ciegas (se bloquea por error, no se guarda)');
});

test('collectForm en ARS (moneda por defecto) no toca el monto ni pide cotización', () => {
  const ctx = buildContext();
  const values = {
    fecha: '2026-11-05', monto: '5000', moneda_ingreso: 'ARS', categoria: 'Hogar', subcategoria: '',
    descripcion_original: 'Super', medio_pago: 'Efectivo', pagado_por: 'Común',
    tipo_proporcion: 'dinamico', cuotas_total: '1',
  };
  const { payload, errors } = ctx.collectForm('expense', null, values);
  assert.equal(Object.keys(errors).length, 0);
  assert.equal(payload.monto, 5000);
  assert.equal(payload.descripcion_original, 'Super');
});

test('fetchDolarOficialVenta cachea la venta oficial y no vuelve a pegarle a la API dentro del TTL', async () => {
  let calls = 0;
  const ctx = buildContext({
    fetchImpl: async () => { calls++; return { ok: true, json: async () => ({ venta: 1050.5 }) }; },
  });
  const first = await ctx.fetchDolarOficialVenta();
  const second = await ctx.fetchDolarOficialVenta();
  assert.equal(first, 1050.5);
  assert.equal(second, 1050.5);
  assert.equal(calls, 1, 'La segunda llamada debe servirse del cache, no repetir el fetch');
});

test('fetchDolarOficialVenta devuelve null sin lanzar si la API falla o responde algo inválido', async () => {
  const ctxDown = buildContext({ fetchImpl: async () => { throw new Error('network down'); } });
  assert.equal(await ctxDown.fetchDolarOficialVenta(), null);

  const ctxBadStatus = buildContext({ fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({}) }) });
  assert.equal(await ctxBadStatus.fetchDolarOficialVenta(), null);

  const ctxBadBody = buildContext({ fetchImpl: async () => ({ ok: true, json: async () => ({ venta: 'no-numero' }) }) });
  assert.equal(await ctxBadBody.fetchDolarOficialVenta(), null);
});

test('updateExpenseMonedaHint muestra el equivalente USD chico cuando se tipeó en ARS', async () => {
  const hint = { textContent: '' };
  const moneda = { value: 'ARS' };
  const monto = { value: '1000' };
  const ctx = buildContext({
    fetchImpl: async () => ({ ok: true, json: async () => ({ venta: 1000 }) }),
    elements: { 'expense-moneda-hint': hint, 'field-moneda_ingreso': moneda, 'field-monto': monto },
  });
  await ctx.updateExpenseMonedaHint();
  assert.match(hint.textContent, /U\$D 1\.00/, 'ARS 1000 a cotización 1000 debe mostrar ≈ USD 1 de referencia');
});

test('updateExpenseMonedaHint avisa sin bloquear si la cotización no está disponible', async () => {
  const hint = { textContent: '' };
  const moneda = { value: 'USD' };
  const monto = { value: '10' };
  const ctx = buildContext({
    fetchImpl: async () => { throw new Error('network down'); },
    elements: { 'expense-moneda-hint': hint, 'field-moneda_ingreso': moneda, 'field-monto': monto },
  });
  await ctx.updateExpenseMonedaHint();
  assert.match(hint.textContent, /No se pudo obtener la cotización oficial/);
});

// Ampliación 2026-11-05: Juan pidió explícitamente que la carga en USD
// también estuviera disponible para gastos FIJOS, no sólo variables.
test('collectForm convierte USD a ARS también en gastos fijos (monto_estimado)', async () => {
  const ctx = buildContext({ fetchImpl: async () => ({ ok: true, json: async () => ({ venta: 1000 }) }) });
  await ctx.fetchDolarOficialVenta();
  const values = {
    nombre: 'Netflix', monto_estimado: '10', moneda_ingreso: 'USD',
    periodicidad: 'mensual', responsable: 'Común', medio_pago: 'Crédito',
    fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-11-05',
  };
  const { payload, errors } = ctx.collectForm('fixed', null, values);
  assert.equal(Object.keys(errors).length, 0);
  assert.equal(payload.monto_estimado, 10000, 'USD 10 a cotización 1000 debe guardarse como ARS 10000');
});

test('collectForm bloquea un fijo en USD sin cotización oficial fresca', () => {
  const ctx = buildContext();
  const values = {
    nombre: 'Netflix', monto_estimado: '10', moneda_ingreso: 'USD',
    periodicidad: 'mensual', responsable: 'Común', medio_pago: 'Crédito',
    fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-11-05',
  };
  const { payload, errors } = ctx.collectForm('fixed', null, values);
  assert.ok(errors.monto_estimado, 'Sin cotización fresca debe marcar error en monto_estimado');
  assert.equal(payload.monto_estimado, 10, 'No debe convertirse a ciegas sin cotización válida');
});

test('collectForm en ARS (fijo, moneda por defecto) no toca monto_estimado ni pide cotización', () => {
  const ctx = buildContext();
  const values = {
    nombre: 'Netflix', monto_estimado: '5000', moneda_ingreso: 'ARS',
    periodicidad: 'mensual', responsable: 'Común', medio_pago: 'Efectivo',
    fixed_tipo_proporcion: 'dinamica', vigente_desde: '2026-11-05',
  };
  const { payload, errors } = ctx.collectForm('fixed', null, values);
  assert.equal(Object.keys(errors).length, 0);
  assert.equal(payload.monto_estimado, 5000);
});
