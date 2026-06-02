# Bitácora del Proyecto

> Registro cronológico de cada sesión de trabajo. Cada entrada documenta qué se hizo, qué se decidió y qué queda pendiente.

---
### [2026-04-11] - Sesión 26
**Objetivo:** 6 bug fixes / mejoras en vista Gastos de Finanzas: T1 fijos filtrados por persona en detalle, T2 fijos con crédito en card Crédito, T3 centralizar lógica de etiqueta tarjeta, T4 (diagnóstico barras), T5 subtotales jd_comun/pinki_comun en torta, T6 sub-labels card total 3 capas.
**Logros:**
- **T1 (renderFijosDetailTable con filtro persona):** La tabla de detalle de fijos mostraba todos los ítems sin importar el filtro de persona activo. Agregado bloque de filtro pre-map usando `getRowPct()` con las 5 ramas del filtro. Footer `tfoot` ahora suma solo los ítems filtrados (`fijosParaMostrar.reduce`).
- **T2 (Capa 3 en card Crédito):** `renderCreditoCard()` y `toggleCreditoDetail()` ahora incluyen gastos fijos con `medio_pago === 'Crédito'`. En `renderCreditoCard` se aplica filtro persona antes de agregar al total. En `toggleCreditoDetail` se muestran todos los fijos de crédito sin filtro de persona (panel de detalle completo).
- **T3 (getTarjetaLabel global helper):** Centralizada la lógica de resolución de ID → label de tarjeta en función global `getTarjetaLabel(id)`. Usa `t.label` (columna H de la Sheet Tarjetas) como primera opción; fallback a `banco + ' – ' + nombre`. Eliminadas dos closures locales `labelTarjeta` redundantes (una en `renderCuotasDetailTable`, otra en `renderCreditoDetailPanel`). Corregida referencia huérfana en template string.
- **T4 (diagnóstico barras):** El usuario confirmó que las etiquetas SÍ aparecen pero solo si la barra tiene cierto largo (MIN_PCT_LABEL = 8). Comportamiento by design, no bug. No requirió cambio.
- **T5 (subtotales jd_comun/pinki_comun en torta):** `renderGastosPie()` ahora muestra bloque "Común / Propio" cuando el filtro persona es `jd_comun` o `pinki_comun`. Cálculo: Común = monto * pct_persona / 100 donde ambos participan; Propio = monto donde pct === 100. Se muestra la proporción de cada uno sobre el total.
- **T6 (sub-labels card total, 3 capas):** Los sub-labels "JD: $X · Pinki: $Y" del card Total en modo `comun` ahora calculan correctamente las 3 capas: (1) gastos variables (cuota_nro === 1 únicamente para no doble-contar), (2) fijos (todos, via S.fixed.data), (3) cuotas comprometidas (filterCuotasComprometidas + applyPersonaFiltro). Antes solo usaba `filteredRows` con cuota_nro > 1 incluidos, causando doble-conteo y omitiendo fijos.
**Pendientes:**
- ⚠ MANUAL (pendiente de sesiones anteriores): NEW deployment `finanzas-api.js` para activar fix T2 falsy-zero + fix C1 subcategoria en getProportions + lastDay + remoción id_appsheet
- ⚠ MANUAL: Ejecutar `setupTriggers()` en Apps Script (instala `onGastosFijosChange`)
- ⚠ MANUAL: Eliminar col `id_appsheet_log` de Log + col `id_appsheet` de GastosFijos
**Notas:** El bug en T6 fue sutil: `filteredRows` ya tiene cuota_nro > 1 excluidos para el total `varTotal`, pero el sub-label usaba esas mismas filas — siendo inconsistente con el total real que incluye `fixTotal` y `cuotasTotal`. La solución fue replicar las 3 capas exactas del total en los sub-labels. Además, el scale de `getRowPct()` (0-100, no 0-1) fue crítico — todas las condiciones usan `=== 100`, `=== 0`, `> 0`.

### [2026-04-12] - Sesión 27
**Objetivo:** 3 fixes independientes en Finanzas: T1 bug card deuda incluye gastos sin participación del otro, T2 trigger corrige proporcion_jd vacío cuando AppSheet no toca el campo, T3 sacar Compras y Recetario del sidebar de Finanzas.
**Logros:**
- **T1 (panel deuda incluye gastos que no involucran al otro):** `renderDeuda()` ya tenía el filtro correcto desde Sesión 24. El bug real estaba en `toggleDeudaDetail()`: cuando el usuario abre el panel haciendo clic en la card, se reconstruían los rows con `.filter(r => r.pago === p1 || r.pago === p2)` sin aplicar el check `getRowPct`. Corregido: `toggleDeudaDetail()` ahora aplica el mismo filtro de 3 condiciones que `renderDeuda()` — excluye pago=Común y excluye filas donde la contraparte tiene pct=0.
- **T2 (proporcion_jd vacío en trigger):** En `apps-script/finanzas-triggers.js`, nuevo paso "── 3. CORREGIR proporcion_jd VACÍO" en `onLogChange()`. Si `tipo_proporcion === 'custom'` y `proporcion_jd` está vacío/null/undefined, escribe 0 en esa celda. Guard `cols.tipo_proporcion >= 0 && cols.proporcion_jd >= 0` para backward compatibility. Raíz: AppSheet envía `proporcion_jd` vacío cuando el usuario no toca el campo en el formulario; el sistema interpretaba ese vacío como 50/50 por el fallback en `getRowPct`.
- **T3 (sidebar Finanzas):** Eliminados los bloques HTML de Compras y Recetario del sidebar de `src/finanzas/index.html` (links externos que no corresponden al módulo).
- **F13 (drill-down respeta filtro persona):** `renderSubcatChart(cat)` filtraba los rows por categoría pero ignoraba `_gastosPersonaFiltro`. Corregido: se envuelve con `applyPersonaFiltro(...)` antes de agrupar por subcategoría. Ahora el drilldown es consistente con la torta principal — en modo "JD" solo muestra subcategorías donde JD participa.
**Pendientes:**
- ⚠ MANUAL: Guardar `finanzas-triggers.js` en el editor de Apps Script (ya ejecutado por el usuario).
**Notas:** El diagnóstico de T1 reveló una asimetría entre el path "render automático" (que usa `debtRows` ya filtrado) y el path "abrir panel" (que reconstruía rows sin filtro). El primer path era correcto; el segundo no. La lección: cuando una función se puede invocar desde dos lugares distintos, verificar que ambos paths apliquen las mismas reglas de filtrado. F13 ya estaba implementado structuralmente — faltaba solo la consistencia con el filtro persona.

### [2026-04-16] - Sesión 28
**Objetivo:** Mejorar la UX de la tabla de detalle en la vista Gastos (Finanzas).
**Logros:**
- Se reemplazaron los `id` de los botones de filtro de persona por la clase `.persona-filter-btn` y el atributo `data-filter` para poder sincronizar múltiples botoneras (arriba de la vista y arriba de la tabla).
- La función `renderGastosTable()` fue reescrita por completo. Ahora recibe las filas ya filtradas por el filtro global de persona.
- Se implementaron variables de estado locales (`_tableSortCol`, `_tableSortDir`, `_tableFilterCat`, `_tableFilterPago`) para permitir ordenamiento por columnas (asc/desc) haciendo clic en los encabezados.
- Se agregaron `<select>` integrados en los encabezados de "Categoría" y "Pagó" para filtrar subconjuntos de datos dentro de la tabla sin afectar el resto del dashboard.
**Pendientes:** Sin pendientes críticos.
**Notas:** El uso de `querySelectorAll` en lugar de `getElementById` fue clave para mantener la sincronía visual de los botones de filtro al estar duplicados en la UI.

### [2026-06-02] - Sesión 30
**Objetivo:** Auditoría completa del módulo Finanzas usando el loop Claude(spec)→Codex(impl)→Claude(review). Punto de entrada: bug reportado por JD — "en Gastos Fijos no aparece ninguno este mes; el mes pasado aparecen pero la suma no da el total".
**Logros:**
- **Fase 0 (diagnóstico estático):** Causa raíz del síntoma = la visibilidad y el total de los fijos estaban acoplados a la proporción dinámica del mes vía `getRowPct()`. En un mes con proporción 100/0 (un solo salario cargado), el filtro `pct1>0 && pct2>0` descartaba TODOS los fijos compartidos. Además, card vs detalle usaban sets distintos.
- **F-A:** Nuevo helper `getFixedKind(item)` → 'shared' | 'personal_p1' | 'personal_p2', clasificando por `tipo_proporcion`/`proporcion_jd` (propiedad del gasto), NO por la proporción del mes. `renderFijosDetailTable()` y `computeFixedForPersona('comun')` ahora incluyen solo fijos `shared`. Card común === footer del detalle.
- **F-A.1:** Sub-línea "JD · Pinki" del card Total ahora suma solo fijos `shared` × meses del período (para que sub1+sub2 === total, incluso con un fijo personal presente). `computeFixedForPersona('comun')` = suma shared × `getMonthsInPeriod().length || 1`. Limpieza de comentario huérfano.
- **F-B:** Bimestrales `/2` en ramas multi-mes de `computeFixedTotalForPeriod()` y `computePresupuestoParts()`. El `history` del API guarda monto crudo sin `es_bimestral`; el front mapea el flag desde `S.fixed.data`. Sin tocar Apps Script (decisión: fix en front).
- **F-C:** Propagado `getFixedKind` + `× meses` a `renderCreditoCard()` y `toggleCreditoDetail()` (el fix F-A no se había propagado a la card de Crédito — Bug A reaparecía ahí).
- **F-D:** Sorts de fecha null-safe en `renderInversiones()` y `renderIngresos()`. Eliminado el `console.log('[CUOTAS DEBUG]…')` de `renderGastos()`.
- **Resto del módulo auditado y confirmado sano:** Deuda (card↔panel↔saldar coherentes), carga inicial con manejo de errores, Inversiones (patrimonial, sin proporción).
- Todos los cambios SOLO en `src/finanzas/index.html`. Cada fix verificado con `node --check` sobre el JS inline extraído.
**Decisiones:**
- **D1 (DEC-029) — ingreso con pago='Común':** No se usa en la práctica. Si llegara a pasar, JD y Pinki dividen por fuera y cargan lo de cada uno por separado. Sin cambios de código.
- **D2 (DEC-030) — gasto variable en mes con proporción 100/0:** Se deja como está. Que un gasto compartido lo banque 100% quien ganó ese mes es el comportamiento esperado de la proporción dinámica. Sin cambios de código.
**Pendientes:**
- Estas correcciones son SOLO frontend — NO requieren re-deploy de Apps Script.
- ⚠ MANUAL (heredados de sesiones previas, siguen abiertos): NEW deployment de `finanzas-api.js`; ejecutar `setupTriggers()`; eliminar cols `id_appsheet_log` (Log) e `id_appsheet` (GastosFijos).
- Aceptados sin urgencia: H1 (API pública — uso solo de la pareja), H8 (lógica de fijos triplicada/cuadruplicada — candidata a unificar en helper).
**Notas:** El loop por fases atrapó dos regresiones que un QA de un solo paso se hubiera comido: la sub-línea del card Total en F-A.1 (quedó sumando todos los fijos mientras el total ya contaba solo shared) y la card de Crédito en F-C (no propagaba el nuevo criterio). El patrón recurrente del módulo: lógica duplicada en varios lugares; arreglar una copia y olvidar las otras.
