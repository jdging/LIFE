import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const script = source.slice(0, source.indexOf('function fijosDateLabel(')) + '\n'
  + source.slice(source.indexOf('function renderCuotasDetail('), source.indexOf('// Detalle de deuda:'));
const close = (cierre, id = 1, vencimiento_pago = null) => ({ id, mes: cierre.slice(0, 7), cierre, vencimiento_pago });
const expense = (fecha, descripcion_original, monto = 10) => ({ fecha, descripcion_original, monto,
  medio_pago: 'Crédito', tipo_proporcion: '50/50', categoria: 'Hogar', cuota_nro: 1 });
function harness(cierres = [], gastos = []) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '', textContent: '', hidden: false,
      style: {}, dataset: {}, classList: {toggle() {}}, setAttribute() {} });
    return elements.get(id);
  };
  const context = vm.createContext({ document: { getElementById: element,
    querySelector: (selector) => element(selector),
    querySelectorAll: (selector) => selector === '[data-write-action]' ? [element('global-write')] : [] },
    confirm: () => true, fetch: async () => { throw Error('unexpected fetch'); } });
  vm.runInContext(script, context);
  vm.runInContext(`Object.assign(DATA, {tarjetaVencimientos:${JSON.stringify(cierres)}, gastos:${JSON.stringify(gastos)}});
    liveMode = true; period = {from:'2026-11-01',to:'2026-11-30'}; personaFiltro = 'comun';`, context);
  context.loadLive = async () => {};
  return { context, element, run: (code) => vm.runInContext(code, context), html: () => element('credito-detail-inner').innerHTML };
}

test('onboarding empty state asks previous/next close and optional payment', () => {
  const h = harness(); h.run('renderCreditoDetail()');
  assert.match(h.html(), /vencimiento-cierre-anterior/);
  assert.match(h.html(), /vencimiento-cierre-proximo/);
  assert.match(h.html(), /opcional/);
  assert.match(h.html(), /Sin cargos/);
});

test('exclusive previous close, inclusive current close and year rollover', () => {
  const h = harness([close('2026-12-31'), close('2027-01-25', 2, '2027-02-05')]);
  assert.equal(h.run("creditCycleForDate('2026-12-31', creditCycles())"), null);
  assert.equal(h.run("creditCycleForDate('2027-01-01', creditCycles())"), '2027-01-25');
  assert.equal(h.run("creditCycleForDate('2027-01-25', creditCycles())"), '2027-01-25');
  assert.equal(h.run("creditCycleForDate('2027-01-26', creditCycles())"), null);
  const admin = h.run('renderVencimientosAdmin()');
  assert.match(admin, /01\/01\/2027 → 25\/01\/2027/);
  assert.doesNotMatch(admin, /Desde siempre/);
});

test('missing month remains unassigned until historical backfill', () => {
  const h = harness([close('2026-09-24'), close('2026-11-24', 3)]);
  assert.equal(h.run("creditCycleForDate('2026-10-25', creditCycles())"), null);
  assert.match(h.run('renderVencimientosAdmin()'), /faltan cierres/i);
  h.run("DATA.tarjetaVencimientos.push({id:2,mes:'2026-10',cierre:'2026-10-24'})");
  assert.equal(h.run("creditCycleForDate('2026-10-25', creditCycles())"), '2026-11-24');
  assert.equal(h.run("creditCycleForDate('2026-10-24', creditCycles())"), '2026-10-24');
});

test('cycle selector defaults current and keeps history independent of global calendar', () => {
  const h = harness([close('2026-09-24'), close('2026-10-24', 2), close('2026-11-24', 3)], [
    expense('2026-10-25', 'octubre-en-noviembre'), expense('2026-11-24', 'ultimo-dia'),
    expense('2026-11-25', 'abierto'), expense('2026-10-10', 'historico')]);
  h.context.todayLocalISO = () => '2026-11-05';
  h.run('renderCreditoDetail()');
  assert.match(h.html(), /credito-cycle-select/);
  assert.match(h.html(), /octubre-en-noviembre/);
  assert.match(h.html(), /ultimo-dia/);
  assert.doesNotMatch(h.html(), />abierto</);
  assert.match(h.html(), /independiente del calendario global/);
  h.run("setCreditoCycle('2026-10-24')");
  assert.match(h.html(), /historico/);
  assert.doesNotMatch(h.html(), /octubre-en-noviembre<\/td>/);
  h.run("period = {from:'2030-01-01',to:'2030-01-31'}; renderCreditoDetail()");
  assert.match(h.html(), /historico/);
  h.run("setCreditoCycle('abierto')"); assert.match(h.html(), />abierto</);
});

test('fixed recurring estimates are separate, undated, excluded from dated cycle total', () => {
  const h = harness([close('2026-10-24'), close('2026-11-24', 2)], [expense('2026-10-25', 'compra', 10)]);
  h.context.todayLocalISO = () => '2026-11-05';
  h.run(`DATA.fijos = [{id:'1',fijo_grupo_id:'1',nombre:'Netflix',medio_pago:'Crédito',
    responsable:'Común',tipo_proporcion:'50/50',vigente_desde:'2026-01-01',activo:1,monto_mensual:100}];
    period = {from:'2030-01-01',to:'2030-01-31'}; renderCreditoDetail()`);
  assert.match(h.html(), /Netflix/);
  assert.match(h.html(), /estimad[oa]s?.*sin fecha real de cargo/is);
  assert.match(h.html(), /Total fechado del ciclo/);
  assert.doesNotMatch(h.html(), /2026-11-01<\/td>/);
});

test('legacy unconfirmed due date never defines a close', () => {
  const h = harness([{id:1,mes:'2026-10',cierre:null,vencimiento_pago:'2026-11-04'}]);
  assert.equal(h.run('creditCycles().length'), 0);
  assert.match(h.run('renderVencimientosAdmin()'), /confirmar.*cierre/i);
});

test('POST stores close and optional due date separately', async () => {
  const h = harness(); const payloads = [];
  h.context.fetch = async (url, options) => { payloads.push(JSON.parse(options.body)); return {ok:true,json:async()=>({})}; };
  await h.run("saveTarjetaVencimiento('2026-11','2026-11-24',null)");
  await h.run("saveTarjetaVencimiento('2026-12','2026-12-24','2027-01-04')");
  assert.deepEqual(payloads, [{mes:'2026-11',cierre:'2026-11-24'},
    {mes:'2026-12',cierre:'2026-12-24',vencimiento_pago:'2027-01-04'}]);
});

test('single save prevents double submit and rerenders unlocked after completion', async () => {
  const h = harness([close('2026-10-24')]);
  h.element('vencimiento-fecha').value = '2026-11-24';
  let resolve; let writes = 0;
  h.context.saveTarjetaVencimiento = async () => { writes++; await new Promise((r) => { resolve = r; }); };
  const first = h.run('handleVencimientoFormSubmit({preventDefault(){}})');
  await h.run('handleVencimientoFormSubmit({preventDefault(){}})');
  assert.equal(writes, 1);
  assert.equal(h.element('global-write').disabled, true);
  resolve(); await first;
  assert.equal(h.run('writePending'), false);
  assert.equal(h.element('global-write').disabled, false);
  assert.doesNotMatch(h.html(), /disabled/);
});

test('initial second POST failure reads back partial success and exposes recoverable missing close', async () => {
  const h = harness();
  h.element('vencimiento-cierre-anterior').value = '2026-10-24';
  h.element('vencimiento-cierre-proximo').value = '2026-11-24';
  let writes = 0; let reads = 0;
  h.context.saveTarjetaVencimiento = async () => { if (++writes === 2) throw Error('network'); };
  h.context.fetch = async () => { reads++; return {ok:true,json:async()=>({vencimientos:[close('2026-10-24')]})}; };
  const submitting = h.run('handleVencimientoFormInicialSubmit({preventDefault(){}})');
  await h.run('handleVencimientoFormInicialSubmit({preventDefault(){}})');
  await submitting;
  assert.equal(writes, 2, 'double submit must not start another onboarding pair');
  assert.equal(reads, 1);
  assert.equal(h.run('DATA.tarjetaVencimientos.length'), 1);
  assert.match(h.element('vencimiento-form-error').textContent, /Revisá.*faltante/s);
  assert.match(h.html(), /id="vencimiento-fecha"/);
  assert.doesNotMatch(h.html(), /disabled/);
});

test('delete rerenders unlocked; older close requires confirmation', async () => {
  const h = harness([close('2026-10-24'), close('2026-11-24',2)]);
  let writes=0; h.context.deleteTarjetaVencimientoRequest = async () => {writes++;};
  h.context.confirm = () => false;
  await h.run('handleVencimientoDelete(1)'); assert.equal(writes,0);
  await h.run('handleVencimientoDelete(2)'); assert.equal(writes,1);
  assert.doesNotMatch(h.html(), /disabled/);
});

test('legacy unconfirmed month can be confirmed without deleting preserved payment', async () => {
  const h = harness([{id:1,mes:'2026-10',cierre:null,vencimiento_pago:'2026-11-04'}]);
  h.element('vencimiento-fecha').value = '2026-10-24';
  let payload;
  h.context.fetch = async (url, options) => { payload = JSON.parse(options.body); return {ok:true,json:async()=>({})}; };
  await h.run('handleVencimientoFormSubmit({preventDefault(){}})');
  assert.equal(payload.cierre, '2026-10-24');
  assert.equal(payload.vencimiento_pago, '2026-11-04');
});

test('initial pair POST/readback/retry uses real handlers and idempotent monthly payloads', async () => {
  const h = harness(); const stored = new Map(); const requests = [];
  let failNext = true;
  h.context.fetch = async (url, options = {}) => {
    if (options.method === 'POST') {
      const p = JSON.parse(options.body); requests.push(p);
      if (p.mes === '2026-11' && failNext) { failNext = false; return {ok:false,json:async()=>({error:'reintentar'})}; }
      const row = {...p,id:stored.get(p.mes)?.id || stored.size+1}; stored.set(p.mes,row);
      return {ok:true,json:async()=>({vencimiento:row})};
    }
    return {ok:true,json:async()=>({vencimientos:[...stored.values()]})};
  };
  h.context.loadLive = async () => h.run("fetchJSON('/api/tarjeta-vencimientos').then(r => { DATA.tarjetaVencimientos = r.vencimientos; })");
  h.element('vencimiento-cierre-anterior').value = '2026-10-24';
  h.element('vencimiento-cierre-proximo').value = '2026-11-24';
  h.element('vencimiento-pago-inicial').value = '2026-12-04';
  await h.run('handleVencimientoFormInicialSubmit({preventDefault(){}})');
  assert.equal(stored.size,1);
  assert.match(h.element('vencimiento-form-error').textContent, /24\/11\/2026/);
  h.element('vencimiento-fecha').value = '2026-11-24';
  h.element('vencimiento-pago-fecha').value = '2026-12-04';
  await h.run('handleVencimientoFormSubmit({preventDefault(){}})');
  assert.equal(stored.size,2);
  assert.equal(stored.get('2026-11').vencimiento_pago,'2026-12-04');
  assert.equal(h.run("creditCycleForDate('2026-10-25',creditCycles())"),'2026-11-24');
  assert.equal(requests.length,3);
  assert.equal(h.element('vencimiento-form-error').textContent,'');
});

test('failed first POST and failed readback explain uncertainty and unlock retry', async () => {
  const h = harness();
  h.element('vencimiento-cierre-anterior').value = '2026-10-24';
  h.element('vencimiento-cierre-proximo').value = '2026-11-24';
  h.context.fetch = async () => {throw Error('offline');};
  await h.run('handleVencimientoFormInicialSubmit({preventDefault(){}})');
  assert.equal(h.run('writePending'),false);
  assert.match(h.element('vencimiento-form-error').textContent,/No se pudo verificar/);
  assert.doesNotMatch(h.html(), /disabled/);
});

test('empty historical cycle still keeps selector; unassigned and due dates never fabricate charges', () => {
  const h = harness([close('2026-09-24'),close('2026-11-24',2,'2027-03-20')], [expense('2026-10-25','gap-charge')]);
  h.run("setCreditoCycle('2026-11-24')");
  assert.match(h.html(),/Sin cargos/); assert.match(h.html(),/credito-cycle-select/);
  assert.doesNotMatch(h.html(),/>gap-charge</);
  h.run("setCreditoCycle('sin-asignar')"); assert.match(h.html(),/>gap-charge</);
});

test('duplicate month and invalid onboarding order perform no writes', async () => {
  const h = harness([close('2026-10-24')]); let writes=0;
  h.context.saveTarjetaVencimiento = async () => {writes++;};
  h.element('vencimiento-fecha').value = '2026-10-30';
  await h.run('handleVencimientoFormSubmit({preventDefault(){}})');
  assert.match(h.element('vencimiento-form-error').textContent,/Ya hay un cierre/);
  h.element('vencimiento-cierre-anterior').value = '2026-11-24';
  h.element('vencimiento-cierre-proximo').value = '2026-10-24';
  await h.run('handleVencimientoFormInicialSubmit({preventDefault(){}})');
  assert.match(h.element('vencimiento-form-error').textContent,/antes/);
  assert.equal(writes,0);
});
