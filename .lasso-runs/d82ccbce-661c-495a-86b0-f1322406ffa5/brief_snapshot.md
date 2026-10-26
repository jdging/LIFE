# Brief — Tabla de Gastos: editar por fila + PATCH backend + fix descripción en confirmación Telegram

Repo: este workdir (clon aislado de LIFE, rama `lab/reinvencion`, ya tiene
integrados los cambios de la tarea previa de Deuda/acordeón -- no los toques
ni los repitas, son base).
Kanban: tarjeta t_b5c6e680 (board lasso), hija de t_02402679.

## Pedido de Juan (confirmado, 2026-10-26), 4 puntos:

### 1. Botón editar por fila en la tabla de Gastos
En `src/lab-dashboard/` (vista Gastos, tabla principal al fondo), agregar un
botón "editar" por fila junto al de borrar. Al tocarlo debe abrir el mismo
sistema de formularios genérico que ya existe (`openForm`/`collectForm`/
`formMarkup`/`describeForm`/`routeForForm`) para un gasto existente, con los
campos precargados, y guardar con el endpoint nuevo del punto 3. Seguí el
mismo patrón que ya usa el formulario de alta de gasto y el de edición de
Inventario (PATCH) como referencia de cómo este dashboard ya maneja edición.

### 2. Columna "Monto" — NO TOCAR
Juan confirmó que ya muestra el total correcto; era un filtro de persona que
él tenía activo. Descartado, no es un bug.

### 3. Backend: falta PATCH /api/expenses/:id
`lab/api.py` tiene `DELETE /api/expenses/:id` pero ningún `PATCH` (a
diferencia de income, que sí tiene `PATCH /api/income/:id` -- usalo como
referencia directa de patrón: mismo estilo de validación, mismo whitelist de
campos editables, mismo manejo de errores). Agregar:
- `db.py`: función de actualización de gasto (nombre a tu criterio, mismo
  patrón de atomicidad que las funciones de edición existentes).
- `api.py`: handler + ruta `PATCH /api/expenses/:id`, agregado a
  `ALLOWED_EXPENSE_FIELDS` o un subset editable si corresponde restringir
  algo (ej. no permitir editar cuotas_total de un gasto ya generado en
  cuotas, usar tu criterio y documentarlo).
- `middleware.js` del dashboard: whitelist de la ruta nueva en `PROXY_ROUTES`.
- Documentar en `lab/README-api.md` y `src/lab-dashboard/api-contract.md`.
- Tests nuevos en `lab/tests/test_api.py` (y `proxy.test.mjs` si aplica).

### 4. Fix en el resumen de confirmación de Telegram (bug real, ya causó datos sin descripción en producción)
`lab/telegram_ingesta.py`, función `_resumen_borrador()`: el resumen que se le
muestra a Juan ANTES de guardar un gasto por Telegram NO incluye la
descripción/comercio en ningún lado. Esto permitió que un gasto real
(id=856, "Panadería Distinción") se guardara sin descripción sin que nadie lo
notara en la confirmación. Agregar la descripción al resumen
(`borrador.get("descripcion_original")`) cuando esté presente, con el mismo
criterio de formato que el resto de las partes (ej. como una parte más del
`" · ".join(partes)`, ubicación razonable cerca de la categoría). Ajustar
tests existentes de `telegram_ingesta` si verifican el formato exacto del
resumen (buscá en `lab/tests/` los tests de `_resumen_borrador`/`armar_pregunta`).

NO corrijas el dato real id=856 desde este workdir -- eso lo hace el
coordinador contra la base real después de que el PATCH nuevo esté probado.
Documentalo en `report.md` como pendiente explícito.

## Reglas
- Rama `lab/reinvencion`, sin tocar `main` ni `src/finanzas/index.html`.
- No inventar persistencia ni simular escrituras que no persisten de verdad.
- Correr los tests existentes antes de reportar si tenés shell disponible
  (`cd lab && python -m pytest -q tests`, `cd src/lab-dashboard && node --test
  tests/*.mjs`). Si no tenés herramienta de shell, decilo explícitamente en
  el report y el coordinador los corre.
- `report.md` en la raíz del workdir: archivos tocados, decisiones de diseño
  (qué campos quedaron editables en el PATCH y por qué), resultado de tests,
  y qué falta (push/deploy/QA manual de Juan, corrección del dato real
  id=856, todo pendiente -- no lo hagas).
