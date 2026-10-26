# Brief — Card de Deuda (detalle+saldar) + acordeón exclusivo

Repo: este workdir (clon aislado de LIFE, rama `lab/reinvencion` ya checked out).
Kanban: tarjeta t_3fce89aa (board lasso), hija de t_02402679.

## Contexto
`src/lab-dashboard/` es el dashboard nuevo (en construcción, lab/reinvencion).
`src/finanzas/index.html` es el LEGACY real en producción (rama `main` del repo
original) — NO LO TOQUES, está fuera de este workdir solo como referencia de
comportamiento. Pedí leerlo si necesitás comparar (existe en este mismo clon
porque es la misma rama lab/reinvencion, que también tiene ese archivo).

## Pedido de Juan (dueño del producto), dos puntos:

### 1. Card de Deuda: detalle de origen + poder saldarla
En el legacy (`src/finanzas/index.html`), buscá `toggleDeudaDetail`, `.deuda-card`,
`.btn-saldar` y la lógica de deuda en general (quién le debe a quién, por qué mes,
composición). El panel desplegable de Deuda ahí muestra el detalle de origen de la
deuda y permite saldarla.

En `src/lab-dashboard/` (buscá `deudaPendiente`, `adaptCurrentDebt`, cualquier
función que renderice el card/panel de Deuda en `app.js`), el card de Deuda hoy
sólo muestra el monto pendiente, SIN detalle de origen ni botón de saldar.

Implementá:
- En el panel de detalle del card Deuda: mostrar de dónde viene la deuda (mes(es)
  de origen, quién pagó de más, composición si hay varios ítems) — mismo nivel de
  detalle que el legacy.
- Agregar la posibilidad de saldar la deuda desde ahí (botón/flujo equivalente al
  `.btn-saldar` del legacy), respetando el modelo de datos actual del lab-dashboard
  (SQLite vía `lab/api.py`/`lab/db.py` si hace falta tocar backend — revisá si ya
  existe un endpoint de saldar deuda en `lab/api.py`; si no existe, proponé el
  mínimo necesario y documentalo, pero priorizá no romper nada existente).
- Si el dashboard actual es snapshot estático (JSON versionados, sin escritura
  real — confirmá mirando `src/lab-dashboard/app.js` y comentarios previos sobre
  "Escrituras disponibles" / `liveMode`), el botón de saldar debe comportarse
  acorde al modo real (si no hay backend de escritura para esto todavía, dejalo
  documentado como pendiente en vez de simular un guardado falso). NO inventes
  persistencia que no existe.

### 2. Acordeón exclusivo: un solo panel de detalle abierto a la vez
Hoy, al tocar un card (ej. "Carga en crédito", Fijos, Cuotas, Deuda) se abre su
panel de detalle debajo. Si después se toca OTRO card, el panel nuevo se abre
ADEMÁS del anterior (se apilan). Se pide que al abrir un nuevo panel, el anterior
se cierre automáticamente — solo un panel de detalle abierto por vez en toda la
vista. Buscá `toggleCreditoDetail`, `toggleDeudaDetail`, y las funciones toggle
equivalentes de Fijos/Cuotas en `src/lab-dashboard/app.js` — hay una nota previa
(`AGENTS.md` watch-outs) sobre asimetría render/toggle entre esas funciones:
tené cuidado de no romper los filtros de persona que ya existen al centralizar
el cierre de paneles.

## Reglas
- Rama `lab/reinvencion`, sin tocar `main` ni `src/finanzas/index.html`.
- No inventar datos ni simular escrituras que no persisten de verdad.
- Corré los tests existentes del repo antes de reportar (`lab/tests/`, y los de
  `src/lab-dashboard/tests/` si aplican — mirá README de cada carpeta para el
  comando exacto).
- Dejá un `report.md` en la raíz de este workdir con: qué tocaste (archivos),
  qué decidiste sobre backend de "saldar" (si hiciste falta endpoint nuevo o no),
  resultado de tests, y qué falta para que esto sea mergeable (push/deploy/QA
  manual de Juan siguen pendientes, no los hagas).
