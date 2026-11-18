import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';

const script = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const slice = (a, b) => script.slice(script.indexOf(a), script.indexOf(b, script.indexOf(a) + 1));
const source = [slice('const escapeHtml =', '\n\n'), slice('async function fetchJSON', 'function compareIds'),
  slice('function switchView', '// ── PERÍODO'),
  slice('// ── VISTA RECETAS', '// ── VISTA INVENTARIO')].join('\n');
const recipe = { id: 7, version: 3, titulo: 'Sopa <casera>', porciones: 2, tiempo_preparacion_min: null,
  ingredientes: [{ nombre: 'Sal a gusto', cantidad: null, unidad: null }], pasos: ['Mezclá <bien>'], notas: 'Servir caliente' };
const json = (data, status = 200) => new Response(JSON.stringify(data), { status });

function harness(fetch, confirm = () => true) {
  const elements = new Map();
  for (const section of ['ingredientes', 'pasos']) {
    elements.set(`receta-${section}`, { children: [], append(row) { this.children.push(row); }, replaceChildren() { this.children = []; } });
    elements.set(`receta-${section}-template`, { content: { firstElementChild: { cloneNode() {
      const fields = new Map();
      return { querySelector(selector) {
        if (!fields.has(selector)) fields.set(selector, { value: '', focus() {} });
        return fields.get(selector);
      } };
    } } } });
  }
  elements.set('receta-dialog', { open: false, showModal() { this.open = true; }, close() { this.open = false; } });
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, { value: '', textContent: '', innerHTML: '', hidden: false, focus() {},
      classList: { toggle() {} }, setAttribute() {}, contains() { return false; } });
    return elements.get(id);
  };
  const sandbox = vm.createContext({ DATA: { recetas: null, recetasError: null },
    currentView: 'inventario', VISIBLE_VIEWS: ['inventario', 'recetas'], ALL_VIEWS: ['inventario', 'recetas'],
    renderInventarioView() {}, document: { getElementById: get }, window: { confirm }, console, fetch, crypto: webcrypto });
  vm.runInContext(source, sandbox);
  return { ...sandbox, get };
}

test('renders the live recipe, escaping title and numbered steps, and searches by title', async () => {
  const paths = [];
  const app = harness(async (path) => { paths.push(path); return json({ recetas: [recipe] }); });
  await app.ensureRecetasLoaded();
  assert.deepEqual(paths, ['/api/recetas']);
  const content = app.get('recetas-content');
  assert.match(content.innerHTML, /Sopa &lt;casera&gt;/);
  assert.match(content.innerHTML, /<details[^>]*data-key="7"[^>]*>\s*<summary[^>]*>[\s\S]*?Sopa &lt;casera&gt;[\s\S]*?2 porciones[\s\S]*?<\/summary>\s*<h4>Ingredientes/);
  assert.doesNotMatch(content.innerHTML, /<details[^>]*\bopen\b/);
  assert.match(content.innerHTML, /<ol[^>]*>\s*<li>Mezclá &lt;bien&gt;<\/li>/);
  assert.match(content.innerHTML, /Sal a gusto/);
  assert.match(content.innerHTML, /Servir caliente/);
  assert.match(content.innerHTML, /data-id="7"[^>]*>Editar/);
  assert.equal(app.get('recetas-new').hidden, false);
  app.get('recetas-search').value = 'pan';
  app.renderRecetasList();
  assert.match(content.innerHTML, /Sin recetas que coincidan/);
  app.setRecetaExpanded({ dataset: { key: '7' }, open: true });
  app.get('recetas-search').value = '';
  await app.ensureRecetasLoaded(true);
  assert.match(content.innerHTML, /<details[^>]*\bopen\b/);
});

test('falling back to the legacy snapshot is read-only and can retry live without retaining stale data', async () => {
  const paths = [];
  const app = harness(async (path) => {
    paths.push(path);
    if (path === 'data/recetas.json') return json([{ nombre: 'Tarta', ingredientes: [{ ingrediente_nombre: 'Harina' }] }]);
    return paths.length === 1 ? json({ error: 'unavailable' }, 503) : json({ recetas: [] });
  });
  await app.ensureRecetasLoaded();
  assert.deepEqual(paths, ['/api/recetas', 'data/recetas.json']);
  assert.match(app.get('recetas-content').innerHTML, /Tarta.*Harina/s);
  assert.match(app.get('recetas-content').innerHTML, /Preparación.*Sin pasos cargados/s);
  assert.doesNotMatch(app.get('recetas-content').innerHTML, />Editar/);
  assert.doesNotMatch(app.get('recetas-content').innerHTML, />Borrar/);
  assert.equal(app.get('recetas-new').hidden, true);
  assert.match(app.get('recetas-notice').textContent, /solo lectura/i);
  assert.equal(app.get('recetas-retry').textContent, 'Reintentar conexión');
  await app.ensureRecetasLoaded(true);
  assert.equal(paths.at(-1), '/api/recetas');
  assert.match(app.get('recetas-content').innerHTML, /Todavía no hay recetas/);
  assert.equal(app.get('recetas-new').hidden, false);
});

test('returning to Recetas refreshes the live list to show bot additions', async () => {
  let reads = 0;
  const app = harness(async () => json({ recetas: ++reads === 1 ? [recipe] : [recipe, { ...recipe, id: 8, titulo: 'Pan del bot' }] }));
  app.switchView('recetas');
  await new Promise(setImmediate);
  assert.doesNotMatch(app.get('recetas-content').innerHTML, /Pan del bot/);
  app.switchView('inventario');
  app.switchView('recetas');
  await new Promise(setImmediate);
  assert.equal(reads, 2);
  assert.match(app.get('recetas-content').innerHTML, /Pan del bot/);
});

test('live mode offers Actualizar to fetch bot additions without leaving the tab', async () => {
  let reads = 0;
  const app = harness(async () => json({ recetas: ++reads === 1 ? [] : [recipe] }));
  await app.ensureRecetasLoaded();
  const refresh = app.get('recetas-retry');
  assert.equal(refresh.hidden, false);
  assert.equal(refresh.textContent, 'Actualizar');
  const handler = html.match(/id="recetas-retry"[^>]*onclick="([^"]+)"/)[1];
  await new Function('ensureRecetasLoaded', `return ${handler}`)(app.ensureRecetasLoaded);
  assert.equal(reads, 2);
  assert.match(app.get('recetas-content').innerHTML, /Sopa/);
});

test('edits fresh detail with its version and shows persisted readback', async () => {
  const calls = [];
  const saved = { ...recipe, version: 5, titulo: 'Sopa editada', porciones: 4, pasos: ['Mezclá <bien>', 'Serví'] };
  const app = harness(async (path, options) => {
    calls.push([path, options.method || 'GET', options.body && JSON.parse(options.body)]);
    if (options.method === 'PATCH') return json(saved);
    if (path === '/api/recetas/7') return json(calls.length === 2 ? { ...recipe, version: 4 } : saved);
    return json({ recetas: [calls.length === 1 ? recipe : saved] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor('7');
  assert.equal(app.get('receta-titulo').value, recipe.titulo);
  assert.equal(Number(app.get('receta-porciones').value), 2);
  app.get('receta-porciones').value = '4';
  assert.equal(app.get('receta-ingredientes').children[0].querySelector('[name="nombre"]').value, 'Sal a gusto');
  app.get('receta-titulo').value = '  Sopa editada  ';
  app.addRecetaRow('pasos', 'Serví');
  await app.saveReceta(new Event('submit'));
  assert.deepEqual(calls, [
    ['/api/recetas', 'GET', undefined], ['/api/recetas/7', 'GET', undefined],
    ['/api/recetas/7', 'PATCH', { titulo: saved.titulo, porciones: 4, ingredientes: recipe.ingredientes, pasos: saved.pasos, version: 4 }],
    ['/api/recetas/7', 'GET', undefined],
    ['/api/recetas', 'GET', undefined],
  ]);
  assert.equal(app.get('receta-dialog').open, false);
  assert.match(app.get('recetas-content').innerHTML, /Sopa editada/);
});

test('validates creation and keeps the draft and intake key for retry without double submit', async () => {
  const writes = [];
  let release;
  const persisted = { ...recipe, titulo: 'Caldo', porciones: 1, ingredientes: [{ nombre: 'Cebolla', cantidad: 1.5, unidad: 'u' }], pasos: ['Herví'] };
  const app = harness(async (path, options) => {
    if (path === '/api/recetas/7') return json(persisted);
    if (options.method !== 'POST') return json({ recetas: [] });
    writes.push(JSON.parse(options.body));
    if (writes.length === 1) return new Promise((resolve) => { release = resolve; });
    return json(persisted, 200);
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor();
  app.get('receta-titulo').value = 'Caldo';
  await app.saveReceta(new Event('submit'));
  assert.equal(writes.length, 0);
  assert.match(app.get('receta-error').textContent, /ingrediente/i);
  const ingredient = app.get('receta-ingredientes').children[0];
  ingredient.querySelector('[name="nombre"]').value = 'Cebolla';
  ingredient.querySelector('[name="cantidad"]').value = '1.5';
  ingredient.querySelector('[name="unidad"]').value = 'u';
  app.get('receta-pasos').children[0].querySelector('[name="paso"]').value = 'Herví';
  assert.equal(Number(app.get('receta-porciones').value), 1);
  app.get('receta-porciones').value = '1.5';
  await app.saveReceta(new Event('submit'));
  assert.equal(writes.length, 0);
  assert.match(app.get('receta-error').textContent, /porciones/i);
  app.get('receta-porciones').value = '1';
  const saving = app.saveReceta(new Event('submit'));
  await app.saveReceta(new Event('submit'));
  assert.equal(writes.length, 1);
  assert.equal(app.get('receta-fields').disabled, true);
  release(json({ error: 'upstream_timeout' }, 504));
  await saving;
  assert.equal(app.get('receta-dialog').open, true);
  assert.equal(ingredient.querySelector('[name="nombre"]').value, 'Cebolla');
  assert.equal(app.get('receta-fields').disabled, true);
  // Even a submit with changed DOM values must retry the original request.
  app.get('receta-titulo').value = 'Otro borrador';
  await app.saveReceta(new Event('submit'));
  assert.ok(writes[0].clave_ingesta);
  assert.deepEqual(writes[0], { titulo: 'Caldo', porciones: 1, ingredientes: [{ nombre: 'Cebolla', cantidad: 1.5, unidad: 'u' }],
    pasos: ['Herví'], clave_ingesta: writes[1].clave_ingesta, allow_duplicado: false });
  assert.deepEqual(writes[1], writes[0]);
  assert.equal(app.get('receta-dialog').open, false);
});

test('a size rejection after timeout unlocks the draft without changing its intake key', async () => {
  const writes = [];
  const shortened = { ...recipe, porciones: 1, pasos: ['Mezclar.'] };
  const app = harness(async (path, options) => {
    if (options.method === 'POST') {
      writes.push(JSON.parse(options.body));
      if (writes.length === 1) return json({ error: 'upstream_timeout' }, 504);
      if (writes.length === 2) return json({ error: 'payload_too_large' }, 413);
      return json(shortened, 201);
    }
    return path === '/api/recetas/7' ? json(shortened) : json({ recetas: [shortened] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor();
  app.get('receta-titulo').value = recipe.titulo;
  app.get('receta-ingredientes').children[0].querySelector('[name="nombre"]').value = 'Sal a gusto';
  const step = app.get('receta-pasos').children[0].querySelector('[name="paso"]');
  step.value = recipe.pasos[0];
  await app.saveReceta(new Event('submit'));
  assert.equal(app.get('receta-fields').disabled, true);
  await app.saveReceta(new Event('submit'));
  assert.equal(app.get('receta-fields').disabled, false);
  assert.equal(step.value, recipe.pasos[0]);
  assert.match(app.get('receta-error').textContent, /Acortá/);
  step.value = shortened.pasos[0];
  await app.saveReceta(new Event('submit'));
  assert.deepEqual(writes[0], writes[1]);
  assert.equal(writes[2].clave_ingesta, writes[0].clave_ingesta);
  assert.deepEqual(writes[2].pasos, shortened.pasos);
  assert.equal(app.get('receta-feedback').textContent, 'Receta guardada.');
});

test('does not announce a replayed creation with different content', async () => {
  const paths = [];
  const app = harness(async (path, options) => {
    paths.push(path);
    if (options.method === 'POST') return json(recipe);
    return json({ recetas: [recipe] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor();
  app.get('receta-titulo').value = 'Otra sopa';
  app.get('receta-ingredientes').children[0].querySelector('[name="nombre"]').value = 'Sal a gusto';
  app.get('receta-pasos').children[0].querySelector('[name="paso"]').value = recipe.pasos[0];
  await app.saveReceta(new Event('submit'));
  assert.deepEqual(paths, ['/api/recetas', '/api/recetas']);
  assert.equal(app.get('receta-dialog').open, true);
  assert.equal(app.get('receta-titulo').value, 'Otra sopa');
  assert.equal(app.get('receta-fields').disabled, false);
  assert.equal(app.get('receta-save').disabled, true);
  assert.match(app.get('receta-error').textContent, /ficha #7.*no se guardaron/i);
  assert.equal(app.get('receta-feedback').textContent, '');
});

test('wrong ID or portions on readback preserve the draft and retry only the detail read', async () => {
  const created = { ...recipe, porciones: 1 };
  let writes = 0;
  let details = 0;
  const app = harness(async (path, options) => {
    if (options.method === 'POST') { writes++; return json(created, 201); }
    if (path === '/api/recetas/7') return json([{ ...created, id: 8 }, { ...created, porciones: 3 }, created][details++]);
    return json({ recetas: [created] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor();
  app.get('receta-titulo').value = recipe.titulo;
  app.get('receta-ingredientes').children[0].querySelector('[name="nombre"]').value = 'Sal a gusto';
  app.get('receta-pasos').children[0].querySelector('[name="paso"]').value = recipe.pasos[0];
  await app.saveReceta(new Event('submit'));
  assert.equal(app.get('receta-dialog').open, true);
  assert.equal(app.get('receta-fields').disabled, true);
  assert.equal(app.get('receta-feedback').textContent, '');
  await app.saveReceta(new Event('submit'));
  assert.equal(app.get('receta-dialog').open, true);
  await app.saveReceta(new Event('submit'));
  assert.equal(details, 3);
  assert.equal(writes, 1);
  assert.equal(app.get('receta-dialog').open, false);
  assert.equal(app.get('receta-feedback').textContent, 'Receta guardada.');
});

test('a stale edit stays open with its draft and cannot retry against a newer version automatically', async () => {
  let writes = 0;
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') { writes++; return json({ code: 'version_desactualizada' }, 409); }
    return path === '/api/recetas/7' ? json(recipe) : json({ recetas: [recipe] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor('7');
  app.get('receta-titulo').value = 'Mi borrador';
  await app.saveReceta(new Event('submit'));
  assert.match(app.get('receta-error').textContent, /otra versión/i);
  assert.equal(app.get('receta-dialog').open, true);
  assert.equal(app.get('receta-titulo').value, 'Mi borrador');
  await app.saveReceta(new Event('submit'));
  assert.equal(writes, 1);
});

test('a database-busy PATCH keeps the same draft and version available for retry', async () => {
  const writes = [];
  const saved = { ...recipe, titulo: 'Mi borrador', version: 4 };
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') {
      writes.push(JSON.parse(options.body));
      return writes.length === 1 ? json({ error: 'base de datos ocupada; reintentar.' }, 409) : json(saved);
    }
    return path === '/api/recetas/7' ? json(writes.length === 2 ? saved : recipe) : json({ recetas: [saved] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor('7');
  app.get('receta-titulo').value = saved.titulo;
  await app.saveReceta(new Event('submit'));
  assert.match(app.get('receta-error').textContent, /ocupad.*reintent/i);
  assert.equal(app.get('receta-save').disabled, false);
  assert.equal(app.get('receta-titulo').value, saved.titulo);
  await app.saveReceta(new Event('submit'));
  assert.deepEqual(writes.map(({ titulo, version }) => ({ titulo, version })), [
    { titulo: saved.titulo, version: 3 }, { titulo: saved.titulo, version: 3 },
  ]);
  assert.equal(app.get('receta-dialog').open, false);
});

test('only the duplicate code shows a duplicate message on creation', async () => {
  const writes = [];
  const app = harness(async (_path, options) => {
    if (options.method !== 'POST') return json({ recetas: [] });
    writes.push(JSON.parse(options.body));
    return json(writes.length === 1 ? { error: 'base de datos ocupada; reintentar.' } : { code: 'receta_duplicada' }, 409);
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor();
  app.get('receta-titulo').value = recipe.titulo;
  app.get('receta-ingredientes').children[0].querySelector('[name="nombre"]').value = 'Sal a gusto';
  app.get('receta-pasos').children[0].querySelector('[name="paso"]').value = recipe.pasos[0];
  await app.saveReceta(new Event('submit'));
  assert.match(app.get('receta-error').textContent, /ocupad.*reintent/i);
  assert.doesNotMatch(app.get('receta-error').textContent, /ya existe/i);
  await app.saveReceta(new Event('submit'));
  assert.match(app.get('receta-error').textContent, /ya existe una receta con ese título/i);
  assert.equal(app.get('receta-fields').disabled, false);
  assert.equal(app.get('receta-titulo').value, recipe.titulo);
  assert.deepEqual(writes[0], writes[1]);
});

test('confirmed writes never replay after a failed readback; reconnect clears the stale warning', async () => {
  let writes = 0;
  let reads = 0;
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') { writes++; return json({ ...recipe, version: 4 }); }
    if (path === '/api/recetas/7') return json({ ...recipe, version: writes ? 4 : 3 });
    if (path === 'data/recetas.json') return json([]);
    if (++reads === 2) return json({}, 503);
    return json({ recetas: [recipe] });
  });
  await app.ensureRecetasLoaded();
  await app.openRecetaEditor('7');
  await app.saveReceta(new Event('submit'));
  assert.equal(app.get('receta-dialog').open, false);
  assert.match(app.get('receta-feedback').textContent, /guardada.*no se pudo actualizar/i);
  await app.saveReceta(new Event('submit'));
  await app.ensureRecetasLoaded(true);
  assert.equal(writes, 1);
  assert.doesNotMatch(app.get('receta-feedback').textContent, /no se pudo actualizar/i);
  assert.match(app.get('recetas-content').innerHTML, /Sopa/);
});

test('canceling deletion names the recipe and makes no writes', async () => {
  const prompts = [];
  const app = harness(async (_path, options) => {
    assert.equal(options.method, undefined);
    return json({ recetas: [recipe] });
  }, (prompt) => { prompts.push(prompt); return false; });
  await app.ensureRecetasLoaded();
  assert.match(app.get('recetas-content').innerHTML, /data-id="7"[^>]*>Borrar/);
  await app.deleteReceta('7');
  assert.match(prompts[0], /Sopa <casera>/);
  assert.match(app.get('recetas-content').innerHTML, /Sopa &lt;casera&gt;/);
});

test('deletion and undo verify the live list, restoring the same ID with the returned version', async () => {
  const calls = [];
  let version = 3;
  let activa = true;
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') {
      const sent = JSON.parse(options.body);
      calls.push([path, sent]);
      activa = sent.activa;
      return json({ id: recipe.id, version: ++version, activa });
    }
    assert.equal(path, '/api/recetas');
    return json({ recetas: activa ? [{ ...recipe, version }] : [] });
  });
  await app.ensureRecetasLoaded();
  await app.deleteReceta('7');
  assert.doesNotMatch(app.get('recetas-content').innerHTML, /Sopa/);
  assert.match(app.get('receta-action-status').textContent, /borrada/i);
  assert.equal(app.get('receta-action').textContent, 'Deshacer');
  await app.ensureRecetasLoaded(true);
  await app.retryRecetaAction();
  assert.match(app.get('recetas-content').innerHTML, /Sopa/);
  assert.match(app.get('receta-action-status').textContent, /restaurada/i);
  assert.equal(app.get('receta-action').hidden, true);
  assert.deepEqual(calls, [['/api/recetas/7', { version: 3, activa: false }], ['/api/recetas/7', { version: 4, activa: true }]]);
});

test('an offline snapshot does not reintroduce a confirmed deletion', async () => {
  let active = true;
  let offline = false;
  const app = harness(async (path, options) => {
    if (path === 'data/recetas.json') return json([{ id: 7, nombre: 'Sopa' }, { id: 8, nombre: 'Tarta' }]);
    if (options.method === 'PATCH') {
      active = false;
      return json({ id: 7, version: 4, activa: false });
    }
    return offline ? json({}, 503) : json({ recetas: active ? [recipe] : [] });
  });
  await app.ensureRecetasLoaded();
  await app.deleteReceta('7');
  offline = true;
  await app.ensureRecetasLoaded(true);
  assert.match(app.get('recetas-content').innerHTML, /Tarta/);
  assert.doesNotMatch(app.get('recetas-content').innerHTML, /Sopa/);
  assert.equal(app.get('receta-action').hidden, true);
  offline = false;
  await app.ensureRecetasLoaded(true);
  assert.equal(app.get('receta-action').textContent, 'Deshacer');
  assert.equal(app.get('receta-action').hidden, false);
});

test('a timeout retries the original PATCH once; failed live readback retries only GET', async () => {
  const writes = [];
  let reads = 0;
  let finish;
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') {
      writes.push(JSON.parse(options.body));
      if (writes.length === 1) return new Promise((resolve) => { finish = resolve; });
      return json({ id: 7, version: 4, activa: false });
    }
    assert.equal(path, '/api/recetas');
    if (++reads === 2) return json({}, 503);
    return json({ recetas: reads === 1 ? [recipe] : [] });
  });
  await app.ensureRecetasLoaded();
  const pending = app.deleteReceta('7');
  await app.deleteReceta('7');
  await app.ensureRecetasLoaded(true);
  assert.equal(writes.length, 1);
  assert.equal(reads, 1);
  finish(json({}, 504));
  await pending;
  assert.equal(app.get('receta-action').textContent, 'Reintentar');
  await app.retryRecetaAction();
  assert.deepEqual(writes, [{ version: 3, activa: false }, { version: 3, activa: false }]);
  assert.equal(app.get('receta-action').textContent, 'Verificar');
  assert.doesNotMatch(app.get('receta-action-status').textContent, /receta borrada/i);
  await app.retryRecetaAction();
  assert.equal(writes.length, 2);
  assert.equal(app.get('receta-action').textContent, 'Deshacer');
});

test('stale deletion refreshes the list without automatically overwriting the latest version', async () => {
  let writes = 0;
  const app = harness(async (_path, options) => {
    if (options.method === 'PATCH') { writes++; return json({ code: 'version_desactualizada' }, 409); }
    return json({ recetas: [writes ? { ...recipe, version: 4, titulo: 'Título actualizado' } : recipe] });
  });
  await app.ensureRecetasLoaded();
  await app.deleteReceta('7');
  assert.match(app.get('receta-action-status').textContent, /cambió/i);
  assert.equal(app.get('receta-action').hidden, true);
  assert.match(app.get('recetas-content').innerHTML, /Título actualizado/);
  await app.retryRecetaAction();
  assert.equal(writes, 1);
});

test('definitive archive rejections release the action and allow deleting another recipe', async (t) => {
  for (const status of [400, 401, 403, 413, 422]) await t.test(String(status), async () => {
    const writes = [];
    const second = { ...recipe, id: 8, titulo: 'Tarta' };
    const app = harness(async (path, options) => {
      if (options.method === 'PATCH') {
        writes.push(path);
        return path.endsWith('/7') ? json({}, status) : json({ id: 8, version: 4, activa: false });
      }
      return json({ recetas: writes.length < 2 ? [recipe, second] : [recipe] });
    });
    await app.ensureRecetasLoaded();
    await app.deleteReceta('7');
    assert.equal(app.get('receta-action').hidden, true);
    assert.match(app.get('receta-action-status').textContent, /rechazó|sesión/i);
    await app.retryRecetaAction();
    await app.deleteReceta('8');
    assert.deepEqual(writes, ['/api/recetas/7', '/api/recetas/8']);
  });
});

test('Archivadas loads only on demand after reload and restores any archived recipe', async () => {
  const archived = [{ id: 7, version: 4, titulo: recipe.titulo, porciones: 2 },
    { id: 8, version: 6, titulo: 'Tarta', porciones: 1 }];
  const active = [];
  const calls = [];
  const fetch = async (path, options) => {
    calls.push([path, options.body && JSON.parse(options.body)]);
    if (options.method === 'PATCH') {
      const [row] = archived.splice(0, 1);
      const restored = { ...row, version: row.version + 1, activa: true };
      active.push(restored);
      return json(restored);
    }
    return json({ recetas: path.endsWith('/archivadas') ? archived : active });
  };
  await harness(fetch).ensureRecetasLoaded();
  const app = harness(fetch);
  await app.ensureRecetasLoaded();
  assert.deepEqual(calls.map(([path]) => path), ['/api/recetas', '/api/recetas']);
  assert.match(html, /id="recetas-archived-toggle"[^>]*onclick="toggleRecetasArchive\(\)"/);
  await app.toggleRecetasArchive();
  const content = app.get('recetas-archived-content');
  assert.equal(app.get('recetas-archived-panel').hidden, false);
  assert.match(content.innerHTML, /Sopa &lt;casera&gt;/);
  assert.match(content.innerHTML, /Tarta/);
  assert.doesNotMatch(app.get('recetas-content').innerHTML, /Sopa|Tarta/);
  await app.restoreArchivedReceta('7');
  assert.deepEqual(calls.slice(2), [['/api/recetas/archivadas', undefined],
    ['/api/recetas/7', { version: 4, activa: true }], ['/api/recetas', undefined], ['/api/recetas/archivadas', undefined]]);
  assert.match(app.get('recetas-content').innerHTML, /Sopa/);
  assert.match(app.get('receta-action-status').textContent, /restaurada/i);
  assert.doesNotMatch(content.innerHTML, /Sopa/);
  assert.match(content.innerHTML, /Tarta/);
});

test('a rejected restore leaves a fresh version available in Archivadas', async () => {
  let version = 4;
  const writes = [];
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') {
      writes.push(JSON.parse(options.body));
      if (writes.length === 1) { version = 5; return json({}, 400); }
      return json({ id: 7, version: 6, activa: true });
    }
    const active = writes.length === 2;
    const rows = path.endsWith('/archivadas') ? (active ? [] : [{ ...recipe, version }])
      : (active ? [{ ...recipe, version: 6 }] : []);
    return json({ recetas: rows });
  });
  await app.ensureRecetasLoaded();
  await app.toggleRecetasArchive();
  await app.restoreArchivedReceta('7');
  assert.equal(app.get('receta-action').hidden, true);
  assert.match(app.get('recetas-archived-content').innerHTML, /Restaurar/);
  await app.retryRecetaAction();
  await app.restoreArchivedReceta('7');
  assert.deepEqual(writes, [{ version: 4, activa: true }, { version: 5, activa: true }]);
  assert.match(app.get('recetas-archived-status').textContent, /No hay recetas archivadas/);
});

test('a restore followed by a concurrent archive releases the action without replaying the PATCH', async () => {
  let version = 4;
  const writes = [];
  const app = harness(async (path, options) => {
    if (options.method === 'PATCH') {
      writes.push(JSON.parse(options.body));
      version = 6;
      return json({ id: 7, version: 5, activa: true });
    }
    return json({ recetas: path.endsWith('/archivadas') ? [{ ...recipe, version }] : [] });
  });
  await app.ensureRecetasLoaded();
  await app.toggleRecetasArchive();
  await app.restoreArchivedReceta('7');
  assert.match(app.get('receta-action-status').textContent, /volvió a cambiar/);
  assert.equal(app.get('receta-action').hidden, true);
  assert.match(app.get('recetas-archived-content').innerHTML, /Restaurar/);
  assert.doesNotMatch(app.get('recetas-archived-content').innerHTML, /disabled/);
  await app.retryRecetaAction();
  assert.deepEqual(writes, [{ version: 4, activa: true }]);
});

test('a busy database retains the original archive action for retry', async () => {
  const writes = [];
  const app = harness(async (_path, options) => {
    if (options.method === 'PATCH') {
      writes.push(JSON.parse(options.body));
      return writes.length === 1 ? json({ error: 'base de datos ocupada; reintentar.' }, 409)
        : json({ id: 7, version: 4, activa: false });
    }
    return json({ recetas: writes.length < 2 ? [recipe] : [] });
  });
  await app.ensureRecetasLoaded();
  await app.deleteReceta('7');
  assert.equal(app.get('receta-action').textContent, 'Reintentar');
  await app.retryRecetaAction();
  assert.deepEqual(writes, [{ version: 3, activa: false }, { version: 3, activa: false }]);
  assert.equal(app.get('receta-action').textContent, 'Deshacer');
});
