# Reporte — Card de Deuda (detalle+saldar) + acordeón exclusivo

Tarjeta: t_3fce89aa (board lasso), hija de t_02402679. Rama `lab/reinvencion`,
workdir aislado. No se tocó `main` ni `src/finanzas/index.html` (legacy, solo
se leyó como referencia).

## 1. Card de Deuda: detalle de origen + saldar

### Qué encontré
- `src/lab-dashboard/app.js` ya tenía `tipo_proporcion`/`proporcion_jd`/
  `proporcion_pinki`/`pagado_por`/`saldado` disponibles por fila en
  `DATA.gastos` (mismo modelo que el Log legacy) — no hacía falta tocar el
  esquema para mostrar composición.
- Ya existía una función `getRowPct(row)` en `app.js` (usada por
  `applyPersonaFiltro`) que resuelve el % JD/Pinki por fila igual que el
  legacy (`custom` → reparto propio; `dinamico` → proporción del mes vía
  `getMonthProportion`, con fallback 50/50). La reutilicé en vez de
  duplicarla.
- `lab/db.py` ya tenía `calcular_deudas_pendientes()` (misma lógica que uso
  en el detalle, pero agregada en un solo neto) y la columna `gastos.saldado`
  — pero **no existía ningún endpoint para escribirla** (marcar un gasto como
  saldado). `lab/api.py` tenía `DELETE /api/expenses/:id` pero ningún
  `PATCH`/`POST` sobre un gasto existente.

### Qué implementé

**Frontend (`src/lab-dashboard/app.js`)**
- `getDebtRows()`: gastos sin saldar, pagados por JD o Pinki (nunca
  "Común"), atemporal — mismo universo que ya usa la card (no respeta el
  período activo, igual que `DATA.deudaPendiente`).
- `renderDeudaDetail()` reescrita: antes solo mostraba el agregado
  `{deudor, acreedor, monto}` de `DATA.deudaPendiente` (sin desglose). Ahora
  renderiza una tabla fila por fila con mes de origen, fecha, descripción,
  quién pagó, % y $ de reparto por persona, subtotales, y un botón
  **Saldar** por fila.
- La card (`g-deuda` / `g-deuda-quien`, función `renderDeudaCard`) **no se
  tocó**: sigue mostrando el agregado del backend (`DATA.deudaPendiente`),
  como pedía el brief.
- Nuevo `kind` `'expense-saldar'` integrado al sistema de formularios
  genérico existente (`openForm`/`collectForm`/`formMarkup`/`describeForm`/
  `routeForForm`/`verifiedWriteEnvelope`), igual patrón que
  `'expense-delete'`: dos pasos (revisar → confirmar), sin campos, `POST`
  sin cuerpo a `/api/expenses/:id/saldar`.
- El botón "Saldar" usa `data-write-action` y queda deshabilitado según las
  mismas condiciones que el resto de las escrituras (`!liveMode ||
  writePending || reloadPending || reloadFailed`). En modo snapshot (sin
  backend de escritura) el detalle se ve igual, pero saldar queda
  deshabilitado con una nota explícita — **no se simula ningún guardado**.

**Backend (`lab/db.py`, `lab/api.py`) — endpoint nuevo, mínimo**
No existía forma de marcar un gasto como saldado, así que agregué el mínimo
necesario siguiendo los patrones ya establecidos en el archivo:
- `db.saldar_gasto(conn, gasto_id, actor)`: mismo patrón de atomicidad que
  `eliminar_gasto_logico` (UPDATE condicionado + `rowcount` + auditoría +
  rollback explícito en caso de falla). Rechaza con `ValueError` si el gasto
  no existe, está borrado, ya está saldado, o `pagado_por='Común'` (un gasto
  común nunca generó deuda, no tiene sentido "saldarlo").
- `POST /api/expenses/:id/saldar` en `api.py` (ruta nueva, handler
  `saldar_expense`): `200 {"expense": {...}}`, `404` si no existe, `409`
  para cualquier otro rechazo de `saldar_gasto` (borrado/ya saldado/Común).
- `src/lab-dashboard/middleware.js`: agregada la ruta al whitelist del proxy
  (`PROXY_ROUTES`), mismo criterio que el resto (sin query params, solo
  `POST`).
- Documentado en `lab/README-api.md` y `src/lab-dashboard/api-contract.md`.

No se tocó ningún endpoint existente ni su contrato.

## 2. Acordeón exclusivo (un solo panel abierto)

`toggleDetail(kind)` ya era una función única compartida por las 4 cards
(fijos/cuotas/credito/deuda) — mejor que lo que anticipaba el brief (el
legacy tiene 4 funciones `toggleXDetail` separadas y asimétricas; acá ya
estaba centralizado). Solo faltaba cerrar los demás paneles al abrir uno
nuevo:
- Agregué `DETAIL_KINDS` (lista de los 4 kinds) y `closeDetail(kind)`.
- `toggleDetail(kind)` ahora cierra los otros 3 paneles (`panel.hidden =
  true` + `aria-expanded="false"`) antes de abrir/cerrar el solicitado.
- Confirmé que cada `render*Detail()` sigue aplicando sus propios filtros de
  persona (`applyPersonaFiltro`, `computeFixedForPersona`, etc.) exactamente
  igual que antes — no cambié esa lógica, solo la visibilidad del panel.
- `renderGastosView()` ya tenía el patrón de re-renderizar el panel que
  esté abierto tras cada recarga de datos (`if (!... .hidden) render...()`)
  — como ahora solo puede haber un panel abierto a la vez, sigue funcionando
  sin cambios.

## Archivos tocados
- `src/lab-dashboard/app.js`
- `src/lab-dashboard/middleware.js`
- `src/lab-dashboard/api-contract.md`
- `src/lab-dashboard/tests/proxy.test.mjs` (casos nuevos para la ruta
  `/api/expenses/:id/saldar`)
- `lab/api.py`
- `lab/db.py`
- `lab/README-api.md`
- `lab/tests/test_api.py` (casos nuevos: saldar OK, saldar ya saldado,
  saldar inexistente, rechazo de `pagado_por='Común'`, rechazo de gasto
  borrado)

## Tests: NO pude ejecutarlos en esta sesión

Este wrapper no me dio una herramienta de shell/ejecución (solo Read/Edit/
Write/Glob/Grep) — no hay forma de correr `pytest` ni `node --test` desde
acá. (Nota: `README-proxy.md` de este mismo repo documenta la misma
limitación en una sesión anterior, así que no es nuevo en este proyecto.)

Hice una revisión estática cuidadosa en su lugar:
- Repasé línea por línea cada función que edité (`db.py`, `api.py`,
  `app.js`) buscando balance de llaves/backticks y coherencia de tipos.
- Para `app.js` en particular, `tests/forms.test.mjs` extrae fragmentos de
  código fuente por texto (`source.indexOf(...)`) y los corre en
  `vm.runInNewContext` con sandboxes mínimos. Verifiqué que:
  - Todo lo que agregué está dentro de ramas `if (kind === 'expense-saldar')`
    que ningún test existente ejercita (ningún test llama
    `collectForm`/`formMarkup`/`describeForm`/`routeForForm`/`openForm` con
    ese `kind`), así que no pueden disparar un `ReferenceError` aunque el
    sandbox de ese test no tenga `P1`/`P2`/`getRowPct` definidos.
  - No creé un `getRowPct` duplicado (ya existía uno en `app.js`; mi primer
    borrador lo duplicaba y lo corregí).
  - `DETAIL_KINDS`/`closeDetail`/`getDebtRows`/`renderDeudaDetail` no
    colisionan con nombres existentes (verificado con grep).
- Para `lab/tests/test_api.py`, seguí el mismo harness (`WsgiApiTestCase`)
  y los mismos helpers (`self.expense(...)`) que el resto del archivo.

**Pendiente para quien acepte este candidato:** correr
```
cd lab && python -m pytest -q tests
cd src/lab-dashboard && node --test tests/fijos.test.mjs tests/forms.test.mjs
cd src/lab-dashboard && node --test tests/proxy.test.mjs
```
antes de mergear, y confirmar visualmente en el navegador (QA manual de
Juan) que:
1. El panel de Deuda muestra el desglose y el botón "Saldar" funciona en
   modo live (requiere que `VPS_API_BASE_URL`/`VPS_INTERNAL_SECRET` estén
   configurados — hoy no lo están en ningún entorno real, según
   `api-contract.md`).
2. Abrir Fijos → Cuotas → Crédito → Deuda en secuencia reemplaza el panel
   en vez de apilarlo, y los filtros de persona siguen funcionando igual
   que antes en cada uno.

## Qué falta (fuera de esta sesión)
- Push/deploy/merge a `main`: no los hice, quedan para Juan.
- QA manual en navegador: no lo hice (sin entorno de browser disponible
  acá tampoco).
- `src/lab-dashboard/api-contract.md` tenía referencias ya desactualizadas
  antes de este cambio (dice "No existe `DELETE /api/income/:id`", que sí
  existe) — no las corregí, están fuera del alcance de este brief; solo
  agregué la fila del endpoint nuevo.
