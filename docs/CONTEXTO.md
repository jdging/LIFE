# Contexto Actual - LIFE

> Ultima actualizacion: 2026-06-02 (Sesion 30)

## Que es LIFE
Sistema de gestion personal multi-modulo alojado en GitHub Pages. Cada modulo es un subdirectorio con su propio index.html, conectado desde un hub central.

## Estado general
- **Hub (src/index.html):** Funcional, dark theme, sidebar 72px. Sidebar tiene: Home, Jardin, Finanzas, Inventario, Compras, Recetario.
- **Jardin (src/jardin/):** Completo -- 26 plantas catalogadas con filtros y compatibilidad de productos.
- **Finanzas (src/finanzas/):** 100% funcional en produccion -- 4 vistas, modulo Presupuestos live con datos reales. Deploy completo, GastosFijos cargado, test end-to-end aprobado.
- **Inventario (src/inventario/):** 100% funcional en produccion -- deploy completo, API activa, AppSheet configurado.
- **Compras (src/compras/):** 100% funcional en produccion -- deploy completo, API activa, AppSheet configurado.
- **Recetario (src/recetario/):** 100% funcional en produccion -- deploy completo, API activa, AppSheet configurado.

## Modulo Finanzas -- Estado actual
### Completado (codigo)
- Google Sheet creada con 4 hojas: Log, Tarjetas, Categorias, Config
  - ID: 1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg
- Apps Script API deployada con 6 endpoints (se agrego `fixed`)
- Dashboard HTML con 4 vistas (Gastos, Inversiones, Ingresos, Presupuesto)
  - Chart.js para visualizaciones
  - Logica de deuda proporcional dinamica con campo corresponde_a (H4)
  - Selector de periodo multi-opcion: Mes / 3M / 6M / Ano / Todo / Rango (H1)
  - Soft delete con confirmacion
  - Alerta de vencimientos de tarjetas
  - Vista Presupuesto: 6 cards, barra 5 segmentos, tabla distribucion individual JD/Pinki, simulador client-side
- Panel AppSheet: boton flotante (+) + drawer lateral con iframe (APPSHEET_URL configurada)
- Apps Script trigger (finanzas-triggers.js): auto-ID + expansion de cuotas (setupTriggers() ejecutado)
- finanzas-seed.js v2: Oct2025-Abr2026, 7 meses, 18 cols, GastosFijos history
- Tabla de detalle de Gastos interactiva: ordenamiento por columnas, filtros locales por Categoría/Pagó en encabezados, y sincronización con el filtro global de persona.

### Completado (setup post-deploy)
- Setup completo: GastosFijos, NEW deployment, test end-to-end, AppSheet configurado

### Completado (Sesion 13)
- H4 -- `getDeudaPct()` con logica `corresponde_a`: gasto propio excluye deuda, gasto ajeno genera 100% deuda. `finanzas-setup.js` con columna S
- H1 -- Selector de periodo: Mes / 3M / 6M / Ano / Todo / Rango. `computePeriod()`, `selectPeriodType()`, `onRangeChange()`. `filterLog()` y `filterCuotasComprometidas()` actualizados a from/to

### Completado (Sesion 16 — Audit fixes)
- C1 (CRITICO — Sesion 16): `getProportions()` en `finanzas-api.js` filtraba por `row.categoria === 'Salario'`. Corregido a `row.subcategoria === 'Salario'` (el schema del Log tiene `categoria='Ingreso'` y `subcategoria='Salario'`). La proporcion dinamica nunca habia funcionado (caia en fallback 50/50). ⚠ Requiere NEW deployment de finanzas-api.js para tomar efecto.
- C2: Renombrado `addMonths` → `addMonthsStr` en `finanzas-seed.js` (colision con `addMonths(Date, n)` de triggers.js)
- C3: Verificado `finanzas-triggers.js` — sin cambios necesarios
- M1: `isEmptyRow()` en triggers.js ya no trata `false` ni `0` como celdas vacias
- M2: Mapa `cols` en triggers.js incluye Q/R/S (tipo_proporcion, proporcion_jd, corresponde_a)
- M3: Array `widths` en setup.js extendido a 19 entradas (columnas Q/R/S)
- M6: CSS `var(--fg)` → `var(--text)` en `.dist-row-disponible` de finanzas/index.html
- M7: Comparacion exacta (`===`) en `showFixedHistory()` para highlight de fila activa
- M8: `renderCards()` en inventario usa `S.items` (global) en lugar de `items` (parametro filtrado) para count de activos
- P1: Dead code `closeHistoryChart()` eliminado de finanzas/index.html (sin callers)
- P3: `softDelete()` en finanzas-api.js protegido con `LockService.getScriptLock()`
- Skipped (por decision del usuario): M4, M5 (seed), P2 (setup)

### Completado (Sesion 17)
- F8 — `getDeudaPct()` eliminado; `renderDeuda()`, `toggleDeudaDetail()`, `renderDeudaDetailPanel()` usan `getRowPct()` directamente. Endpoint `fixed` ahora devuelve `tipo_proporcion` y `proporcion_jd` por cada gasto fijo.
- F4 — `renderFijosDetailTable()`: columna "Responsable" removida, agregadas "Proporcion", "JD $" y "Pinki $" calculadas con `getRowPct()` y `propLabel()`.
- F9 — Drawer redimensionable en desktop: handle CSS + `initDrawerResize()` implementado en finanzas y inventario. Variable de sesion `_drawerWidth`.
- F10 — Vista Inversiones: zoom 1M/3M/6M/1A/Todo, toggle torta/barras, labels de leyenda con monto + porcentaje.
- Correccion: descripcion de C1 en CONTEXTO Sesion 16 era incorrecta (decia `categoria`; el fix correcto es `subcategoria`).

### Completado (Sesion 18)
- CSS-01: compresion horizontal de vistas. Padding reducido en .content, .topbar, .chart-box, .table-header, thead th, tbody td, .deuda-detail. Sin cambios verticales.
- PPTO-01: grafico de fijos oculto por defecto; showFixedHistory() lo muestra al clickear boton por fila. renderPptoFijosTable() reescrita con columnas Proporcion/JD$/Pinki$/monto-mensual/boton arrow. Atributo data-desc en filas para highlight exacto sin falsos positivos del badge bimestral. event.stopPropagation() en boton para evitar doble-dispatch con onclick de fila.
- DIST-01 bug 1: filtro de salarios en renderDistribucion() cambiado de r.categoria a r.subcategoria. Salarios mostraban $0.
- DIST-01 bug 2: filtro r.pago=Comun en varRows/cuotasRows eliminado para alinear con computePresupuestoParts(). Fila Propios eliminada del display para evitar doble conteo (gastos propios ahora incluidos en var1/var2 via getRowPct()).
- SALDADO-01: feature completa de saldar deuda. Apps Script: saldarDeuda(id) con LockService + busca columna saldado por header + setValue(true). Case saldar en el router. Dashboard: renderDeuda() calcula balance solo sobre activeDebtRows (excluye saldado=true). renderDeudaDetailPanel() muestra todas las filas, saldadas con opacity:0.4 y label saldado, no saldadas con boton Saldar. Solo filas activas suman a debeP1/debeP2. saldarRow(id): confirm -> apiFetch(saldar) -> S.log.map(saldado:true) -> renderView(). CSS .btn-saldar con hover en accent verde.

### Completado (acciones manuales Sesion 18/19)
- Columna `saldado` agregada en hoja Log. NEW deployment de finanzas-api.js realizado. campo corresponde_a agregado en AppSheet.

## Modulo Inventario -- Estado actual

### Arquitectura
- **Sheet separada** (ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw) con hoja `Inventario`
- **Apps Script API** propia (inventario-api.js) con 2 endpoints: inventario y delete
- **AppSheet** para carga: https://www.appsheet.com/start/a80bcfb2-256e-48a8-8ed1-ae1f458b8025
- **Dashboard HTML** en src/inventario/index.html

### Schema de la hoja Inventario
| Col | Campo | Tipo | Notas |
|-----|-------|------|-------|
| A | id | texto auto | INV-00001 |
| B | descripcion | texto | libre |
| C | categoria | lista | Electronica/Muebles/Electrodomesticos/Vehiculo/Ropa/Arte/Herramientas/Otro |
| D | fecha_compra | fecha | YYYY-MM-DD |
| E | precio_ars | numero | lo pagado en ARS |
| F | cotizacion_usd_compra | numero | ARS/USD el dia de compra |
| G | precio_usd_compra | numero | valor en USD (ingresable directo) |
| H | proporcion_jd | numero 0-100 | % de JD; Pinki = 100 - proporcion_jd |
| I | precio_venta_estimado_usd | numero | estimacion de reventa en USD |
| J | estado | lista | Activo/Vendido/Donado/Desechado |
| K | notas | texto | libre |
| L | borrado | checkbox | soft delete |

### Completado (codigo)
- `apps-script/inventario-setup.js`: crea hoja con headers, validaciones, formatos, trigger auto-ID
- `apps-script/inventario-api.js`: API con endpoints inventario y delete
- `src/inventario/index.html`: dashboard completo con cotizacion editable, 4 cards, tabla filtrable, drawer AppSheet

### Completado (setup post-deploy)
- setupInventarioSheet() ejecutado, setupInventarioTrigger() activado
- inventario-api.js deployado como Web App con acceso publico ("Anyone"), API_URL configurada en dashboard
- AppSheet conectado y operativo (seguridad publica configurada)

### Completado (Sesion 15)
- Bug fix: datos no cargaban por Apps Script con acceso restringido (usuario corrigio deployment)
- Bug fix: AppSheet no abria por CSP frame-ancestors (usuario configuro seguridad publica) + codigo cambiado a iframe lazy loading en openDrawer()
- Dashboard rediseado: tabla a 15 columnas, card "Reventa estimada" -> "Items activos"
- Funcion `usdCompra(item)` para calcular USD compra en frontend cuando precio_usd_compra esta vacio en la Sheet

## Archivos clave del modulo Finanzas
- `src/finanzas/index.html` -- dashboard 4 vistas + simulador + panel AppSheet
- `apps-script/finanzas-api.js` -- API REST: log, config, proportions, fixed, delete + tests
- `apps-script/finanzas-setup.js` -- inicializacion de la Sheet (ejecutar 1 vez, ya ejecutado)
- `apps-script/finanzas-triggers.js` -- trigger onChange: auto-ID + cuotas (setupTriggers() ya ejecutado)
- `apps-script/finanzas-seed.js` -- datos de prueba v2: Oct2025-Abr2026, 7 meses, 18 cols

## Archivos clave del modulo Inventario
- `src/inventario/index.html` -- dashboard con cotizacion editable, filtros, tabla viva, AppSheet drawer
- `apps-script/inventario-setup.js` -- setup de la hoja (ejecutar 1 vez antes del deploy)
- `apps-script/inventario-api.js` -- API: inventario + delete

## Arquitectura del modulo Presupuestos
- **Hoja GastosFijos** en Google Sheets: cada cambio de precio = nueva fila con `vigente_desde` nuevo
- **Endpoint `?action=fixed&month=YYYY-MM`**: retorna gastos vigentes + historial embedido en `history`
- **Vista Gastos**: total real (variables del Log + fijos del endpoint)
- **Vista Presupuesto**: proyeccion pura -- ingresos vs fijos vs simulados
- **Bimestral**: el API divide por 2 el monto para calculo mensual
- **Historial**: grafico de escalones por gasto fijo, data embedida en S.fixed.history

## Decisiones clave
- Proporcionalidad dinamica desde ingresos del Log (no fija en Config)
- Cuotas expandidas como filas individuales en el Log (trigger Apps Script)
- Soft delete (campo borrado) en lugar de borrado real
- GastosFijos como tabla separada con versionado por fecha
- History embedido en respuesta del endpoint fixed (evita round trips)
- Vista Gastos = panorama completo (fijos + variables). Vista Presupuesto = proyeccion/simulacion.
- corresponde_a separado de pago: permite 100% de deuda cuando se paga gasto ajeno
- S.period como objeto {type, from, to, refMonth}: soporta Mes/3M/6M/Ano/Todo/Rango
- Inventario en Sheet separada de Finanzas (dominios distintos)

### Completado (Sesion 19)
- Verificacion de backlog features-2026-04-06b.md: BUG-01, PROP-01, TWEAK-01, TWEAK-02, C1 (CUOTAS-01+CREDITO-01), PIE-01 ya estaban implementados en el codigo. Todo correctamente funcional. Docs actualizados.
- Acciones manuales de Sesion 18 confirmadas por el usuario: columna saldado agregada en hoja Log + NEW deployment de finanzas-api.js.

### Completado (Sesion 23)
- BUG-A: Inspeccion de finanzas-triggers.js — sin causa en el codigo. Fila fantasma Ingreso=$1 es input accidental.
- BUG-B (`finanzas-triggers.js`): `id_appsheet_log` agregado al mapa `cols`. En `expandCuotas()`, cuotas generadas por trigger limpian `id_appsheet_log=''` para no heredar el ID AppSheet de la fila madre.
- BUG-B (`finanzas-api.js`): Endpoint `?action=fixed` incluye `id_appsheet: current.id_appsheet || ''` en cada objeto (preparado para cuando el usuario agregue esa columna en GastosFijos).
- TAREA 3A (`src/finanzas/index.html`): Card total = varTotal (cuota_nro=1 solamente) + fixTotal + cuotasComprometidas. Se elimina doble conteo de cuotas diferidas. Sub-lineas "JD: $X · Pinki: $Y" en modo Comun.
- TAREA 3B (`src/finanzas/index.html`): Helper `applyPersonaFiltro(rows)` centraliza filtro persona. Botones movidos al section-header de Gastos con nueva clase `.persona-btn` (evita colision con querySelectorAll del selector de periodo). `setGastosPersonaFiltro()` ahora llama `renderGastos()` completo. `renderComposicion()` tambien filtrada.

### Pendiente (manual -- usuario)
- BUG-B: Agregar columna `id_appsheet` en hoja GastosFijos. Configurar AppSheet para usar esa columna como clave primaria interna.
- La columna `id_appsheet_log` (col U) ya existe en hoja Log — AppSheet ya puede usarla.
- NEW deployment de `finanzas-api.js` para activar campo `id_appsheet` en endpoint `fixed`.
- NEW deployment de `finanzas-triggers.js` para activar fix de cuotas expandidas.

## Modulo Compras -- Estado actual (Sesion 20)

### Arquitectura
- **Sheet separada** (DEC-B1) para Compras + Recetario (misma Sheet, hojas distintas)
- **apps-script/compras-setup.js**: crea hoja `ListaCompras` con 10 columnas, validaciones, formato condicional, trigger auto-ID COMP-XXXXX
- **apps-script/compras-api.js**: 6 endpoints: lista, add (con deduplicacion DEC-B2), comprado, delete, limpiar, enviar
- **src/compras/index.html**: dashboard con lista agrupada por categoria, checkboxes, drawer AppSheet, envio por email
- **DEC-B3**: Una sola app AppSheet para Compras + Recetario

### Schema hoja ListaCompras
| Col | Campo | Tipo |
|-----|-------|------|
| A | id | texto auto COMP-XXXXX |
| B | nombre | texto libre |
| C | cantidad | numero |
| D | unidad | dropdown: u/kg/g/l/ml |
| E | categoria | dropdown 8 opciones |
| F | urgente | checkbox |
| G | estado | dropdown: pendiente/comprado |
| H | origen | texto: "manual" o nombre receta |
| I | notas | texto libre |
| J | borrado | checkbox soft delete |

### Completado (Sesion 20 -- codigo)
- `apps-script/compras-setup.js`: creado con setupComprasSheet(), setupComprasTrigger(), onComprasEdit()
- `apps-script/compras-api.js`: creado con 6 endpoints + logica de deduplicacion + envio de email
- `src/compras/index.html`: dashboard completo (lista agrupada, checkboxes, limpiar, enviar, drawer AppSheet)
- Hub `src/index.html`: tarjeta Compras (04) agregada + icono carrito en sidebar
- Sidebars actualizados: jardin, finanzas, inventario — todos tienen icono Compras
- FIX-01 y FEAT-01 de Finanzas implementados (saldado en renderGastosPersonales + filtro por persona en torta)

### Completado (B-MANUAL)
- Google Sheet creada para Compras+Recetario
- setupComprasSheet() + setupComprasTrigger() ejecutados
- compras-api.js deployado como Web App (acceso publico), API_URL configurada en dashboard
- AppSheet conectado con ListaCompras (seguridad publica), APPSHEET_URL configurada

## Modulo Recetario -- Estado actual (Sesion 21)

### Arquitectura
- **Sheet compartida** con Compras (DEC-B1): hojas Recetas + Ingredientes en la misma Sheet
- **apps-script/recetario-setup.js**: crea hojas Recetas e Ingredientes con triggers auto-ID (RECETA-XXXXX / ING-XXXXX)
- **apps-script/recetario-api.js**: Web App read-only, 2 endpoints: lista y detalle
- **src/recetario/index.html**: dashboard completo con grid, filtros, porciones ajustables, "Agregar al super"
- **AppSheet**: misma app que Compras (DEC-B3)

### Schema hoja Recetas
| Col | Campo | Tipo |
|-----|-------|------|
| A | id | texto auto RECETA-XXXXX |
| B | nombre | texto libre |
| C | porciones_base | numero |
| D | categoria | dropdown: Desayuno/Almuerzo/Cena/Merienda/Postre/Otro |
| E | instrucciones | texto libre (opcional) |
| F | borrado | checkbox soft delete |

### Schema hoja Ingredientes
| Col | Campo | Tipo |
|-----|-------|------|
| A | id | texto auto ING-XXXXX |
| B | receta_id | texto (ref a Recetas.id) |
| C | nombre | texto libre |
| D | cantidad | numero |
| E | unidad | dropdown: u/kg/g/l/ml/cdita/cda/taza |
| F | borrado | checkbox soft delete |

### Completado (Sesion 21 -- codigo)
- `apps-script/recetario-setup.js`: creado con setupRecetarioSheets(), setupRecetarioTriggers(), onRecetasEdit(), onIngredientesEdit(), _generateId()
- `apps-script/recetario-api.js`: creado con 2 endpoints (lista, detalle), helpers getSheetData() y getSheetRow()
- `src/recetario/index.html`: dashboard completo — grid de tarjetas, filtro por categoria, detalle expandible con selector de porciones, ajuste proporcional de cantidades con cache data-cant-base, boton "Agregar al super" (fetch secuencial a compras-api.js), drawer AppSheet lazy
- Hub `src/index.html`: tarjeta Recetario (05) + icono recetario en sidebar
- Sidebars actualizados: jardin, finanzas, inventario, compras — todos tienen icono Recetario
- TWEAK Finanzas: S.disponible1 y S.disponible2 expuestos en renderDistribucion() para uso de F-16/F-17

### Completado (C-MANUAL -- Sesion 22)
- C-MANUAL-1: `setupRecetarioSheets()` + `setupRecetarioTriggers()` ejecutados en Apps Script
- C-MANUAL-2: `recetario-api.js` deployado como Web App. URL configurada en `RECETARIO_API_URL` de `src/recetario/index.html`
- C-MANUAL-3: AppSheet configurado con vistas Recetas + Ingredientes en la app de Compras (DEC-B3)

## Siguiente paso inmediato
- Todos los modulos en produccion. Pendientes de Sesion 23: NEW deployments de finanzas-api.js y finanzas-triggers.js + columna id_appsheet en GastosFijos.
- Proximas mejoras opcionales: drill-down categorias en torta de Gastos (F-13), mejoras Vista Presupuesto (F-14/F-15).
- Ultima actualizacion: 2026-04-08 (Sesion 23)

## Sesión 24 — Fixes y Feature Filtro Persona Extendido (2026-04-09)

### Cambios en `apps-script/finanzas-triggers.js`
- **T1-limpieza:** Removido `id_appsheet_log` del objeto `cols` en `onLogChange()`. Removido bloque de limpieza `id_appsheet_log = ''` en `expandCuotas()`.
- **T2-isEmptyRow:** `isEmptyRow()` incluye `|| cell === false` para checkboxes no inicializados de Google Sheets. Guard adicional: `if (!row[cols.tipo] || !row[cols.fecha]) continue` en `onLogChange()`.
- **T3-trigger GastosFijos:** Nueva función `onGastosFijosChange()` — busca filas en hoja GastosFijos sin ID válido `GF-` y pisa cualquier ID (incluye los propios de AppSheet). `generateNextGfId(data, idCol)` — helper análogo a `generateNextId` pero con formato `GF-XXX` (3 dígitos). `setupTriggers()` actualizado: instala ambos triggers `onLogChange` y `onGastosFijosChange`.
- **⚠ MANUAL:** Ejecutar `setupTriggers()` en Apps Script para instalar el nuevo trigger.

### Cambios en `apps-script/finanzas-api.js`
- **T1-limpieza:** Removido campo `id_appsheet` del push en `vigentes` dentro de `getFixed()`.
- **T2-getFixed lastDay:** `firstDay = targetMonth + '-01'` → `lastDay = targetMonth + '-31'`. Gastos con `vigente_desde` a mitad del mes (ej: 2026-04-08) ahora aparecen en la consulta de ese mes.
- **⚠ MANUAL:** NEW deployment requerido para activar ambos fixes.

### Cambios en `src/finanzas/index.html`
- **T1-deuda:** `renderDeuda()` — `debtRows` ahora filtra filas donde la contraparte tiene `pct===0`. Condición: `if (r.pago === p1 && pct2 === 0) return false` / viceversa. Excluye gastos 100% personales del cálculo de deuda.
- **T4-applyPersonaMonto:** Helper `applyPersonaMonto(rows, persona, pJD, pPinki)` — devuelve copia de rows con `monto_total` proporcional. `'comun'` = sin cambios; `'jd_comun'|'jd'` = multiplica por pct1; `'pinki_comun'|'pinki'` = multiplica por pct2. Aplicado en `renderGastosBar()` y `renderGastosTable()`.
- **T4-5 botones:** Reemplazados 3 botones (Comunes/p1/p2) por 5: `gastos-filter-comun`, `gastos-filter-jd-comun`, `gastos-filter-jd`, `gastos-filter-pinki-comun`, `gastos-filter-pinki`. `_gastosPersonaFiltro = 'comun'` (era null).
- **T4-applyPersonaFiltro:** Reescrita con 5 ramas usando `getRowPct()`:
  - `'comun'`: pct1>0 && pct2>0
  - `'jd_comun'`: pct1>0
  - `'jd'`: pct1===100
  - `'pinki_comun'`: pct2>0
  - `'pinki'`: pct2===100
- **T4-computeFixedForPersona:** Nueva función junto a `computeFixedTotalForPeriod()`. Para `'comun'` delega al existente; para otros modos, itera `S.fixed.data` y aplica proporción usando `monto_mensual`. Usada en `renderGastos()` y `renderComposicion()`.
- **T4-cuotas+crédito:** Cuotas comprometidas: `applyPersonaMonto(applyPersonaFiltro(...))` en renderGastos y renderComposicion. Crédito card: recibe `applyPersonaFiltro(rows)` + `cuotasCredito` filtrada internamente con `applyPersonaFiltro`.
- **T4-cascade:** Sub-labels: `=== null` → `=== 'comun'`. Rename 4 botones: `{p1}+Común`, `{p1}`, `{p2}+Común`, `{p2}` en `renderGastosPie`. `setGastosPersonaFiltro` usa loop por los 5 IDs.

### Diagnóstico T3 (fijos no visibles en dashboard)
API confirmada correcta — devuelve 6 ítems correctos para abril 2026. Código frontend analizado y correcto. Causa probable: GitHub Pages con versión antigua del HTML o error silencioso en fetch que deja `S.fixed = null`. **Diagnóstico pendiente:** el usuario debe verificar `S.fixed` en browser console.

### Siguiente paso inmediato
1. NEW deployment `finanzas-api.js` (crítico — activa lastDay + remoción id_appsheet)
2. `setupTriggers()` en Apps Script (crítico — instala trigger GastosFijos)
3. Eliminar columnas manuales en Sheets (id_appsheet_log en Log, id_appsheet en GastosFijos)
4. Verificar `S.fixed` en console para cerrar diagnóstico T3
- Última actualización: 2026-04-09 (Sesión 24)

## Sesión 25 — Bug fixes Finanzas: falsy-zero, subcategoría crédito, cuotas filtro persona (2026-04-09)

### Cambios en `apps-script/finanzas-api.js`
- **T2-falsy-zero (línea 308):** `proporcion_jd: parseFloat(current.proporcion_jd) || 50` → `proporcion_jd: (current.proporcion_jd != null && current.proporcion_jd !== '') ? parseFloat(current.proporcion_jd) : 50`. El bug: cuando `proporcion_jd = 0` en la Sheet, `parseFloat(0) = 0` y `0 || 50 = 50` porque 0 es falsy en JS. Resultado: gastos 100% Pinki mostraban 50/50 en la card de Fijos.
- **⚠ MANUAL:** NEW deployment requerido para activar este fix (más los fixes de Sesión 24 aún sin deployar).

### Cambios en `src/finanzas/index.html`
- **T1-deuda:** Verificado ya correcto desde Sesión 24. Sin cambio.
- **T3-subcategoría en Crédito:** `renderCreditoDetailPanel()` — columna Categoría ahora muestra "Cat / SubCat". Template: `${r.categoria || '—'}${r.subcategoria ? ' / ' + r.subcategoria : ''}`.
- **T4-cuotas con filtro persona:** Card "En Cuotas" en `renderGastos()` ahora aplica `applyPersonaFiltro(cuotasAll)` + `applyPersonaMonto(cuotasFiltered, _gastosPersonaFiltro, p1, p2)`. Count usa `cuotasFiltered.length` (no `cuotasAdjusted` — cantidad de ítems, no monto).

### Acciones manuales completadas (post Sesión 25)
- NEW deployment `finanzas-api.js` ejecutado — todos los fixes activos en producción
- `setupTriggers()` ejecutado — trigger `onGastosFijosChange` activo
- Cols `id_appsheet_log` (Log) e `id_appsheet` (GastosFijos) eliminadas de Sheets
- `API_URL` actualizada en `src/finanzas/index.html`
- `S.fixed` verificado — fijos visibles, todo ok

### Siguiente paso inmediato
- Sin pendientes críticos. Todos los módulos en producción y operativos.
- Próximas mejoras opcionales: F13 (drill-down torta Gastos), SETUP-FINANZAS.md.
- Última actualización: 2026-04-09 (Sesión 25)

## Sesión 26 — Vista Gastos: fixes y mejoras (2026-04-11)

### Cambios en `src/finanzas/index.html`
- **T1 (renderFijosDetailTable filtro persona):** Tabla de detalle de fijos filtrada por persona activa antes del map. Footer `tfoot` suma solo ítems filtrados.
- **T2 (Capa 3 en card Crédito):** `renderCreditoCard()` incluye fijos con `medio_pago=Crédito` con filtro persona para el total económico. `toggleCreditoDetail()` los incluye sin filtro (panel informativo).
- **T3 (getTarjetaLabel helper global):** Función global centralizada para resolver ID tarjeta → label legible. Prioridad: `t.label` (col H) > `banco + ' – ' + nombre` > raw ID. Eliminadas closures locales duplicadas.
- **T5 (subtotales en torta jd_comun/pinki_comun):** Bloque "Común / Propio" en `renderGastosPie()` para modos `jd_comun` y `pinki_comun`.
- **T6 (sub-labels card Total, 3 capas):** Sub-labels "JD: $X · Pinki: $Y" replican las 3 capas del total: (1) vars cuota_nro===1, (2) S.fixed.data, (3) cuotas comprometidas.

### Siguiente paso inmediato
- Todos los módulos en producción y operativos.
- Próximas mejoras opcionales: F13 (drill-down torta Gastos), SETUP-FINANZAS.md.
- Última actualización: 2026-04-11 (Sesión 26)

## Sesión 27 — Bug fixes: deuda panel, trigger proporcion_jd, sidebar (2026-04-12)

### Cambios en `src/finanzas/index.html`
- **T1 (panel deuda):** `toggleDeudaDetail()` — el path "abrir panel haciendo clic" ahora aplica el mismo filtro de 3 condiciones que `renderDeuda()`: excluye pago=Común y excluye filas donde la contraparte tiene pct=0. Antes, el panel se construía con `.filter(r => r.pago === p1 || r.pago === p2)` sin verificar la proporción del otro.
- **T3 (sidebar):** Eliminados bloques HTML de Compras y Recetario del sidebar. Solo quedan los módulos propios de Finanzas.

### Cambios en `apps-script/finanzas-triggers.js`
- **T2 (proporcion_jd vacío):** Nuevo paso en `onLogChange()` — si `tipo_proporcion=custom` y `proporcion_jd` está vacío, escribe 0. Guard `cols.tipo_proporcion >= 0 && cols.proporcion_jd >= 0` para backward compatibility.

### Acción manual pendiente
- ⚠ Guardar `finanzas-triggers.js` en el editor de Apps Script (Ctrl+S). No requiere new deployment — los triggers `onChange` usan el código más reciente al guardar.

### Siguiente paso inmediato
- Acción manual: guardar finanzas-triggers.js en Apps Script para activar fix T2.
- Sin pendientes críticos de código.
- Última actualización: 2026-04-12 (Sesión 27)

## Resumen Histórico (Sesiones 1-25)
- **Infraestructura:** Stack definido con HTML/JS vanilla + Google Sheets + Apps Script (API Web App) + AppSheet para carga.
- **Módulo Jardín:** Catálogo de 26 plantas completo con filtros y base de datos de productos.
- **Módulo Finanzas:** Core del sistema. Implementado Log de transacciones, gestión de tarjetas, categorías dinámicas y configuración de nombres (p1/p2).
- **Lógica Proporcional:** Sistema de "proporción dinámica" basado en el Log. Soporta gastos Comunes, JD, Pinki y proporciones Custom (0-100%).
- **Triggers Críticos:** Expansión automática de cuotas en Apps Script (heredando IDs para trazabilidad) y corrección de valores null en `proporcion_jd`.
- **Dashboard:** 4 vistas principales (Dashboard, Gastos, Ingresos, Inversiones) con Chart.js.
- **Módulos Satélite:** Inventario, Compras y Recetario operativos con sus propias APIs y formularios de carga.
- **UX/UI:** Sidebar de 72px, modo dark persistente, drawer para AppSheet y cards con sub-labels de distribución de gastos.
### Completado (Sesion 30 — Auditoria completa modulo Finanzas)
Loop de auditoria por fases (Claude spec -> Codex impl -> Claude review). Todos los cambios SOLO en `src/finanzas/index.html`, verificados con `node --check`. NO requieren re-deploy de Apps Script.
- **Bug raiz resuelto:** la visibilidad y el total de los gastos fijos estaban acoplados a la proporcion dinamica del mes; en meses con proporcion 100/0 desaparecian todos los fijos compartidos.
- **F-A:** helper `getFixedKind()` clasifica fijos shared/personal por `tipo_proporcion` (no por la proporcion del mes). Card comun === detalle.
- **F-A.1:** sub-linea del card Total = fijos shared x meses; `computeFixedForPersona('comun')` multi-mes con `getMonthsInPeriod().length`.
- **F-B:** bimestrales /2 en multi-mes (`computeFixedTotalForPeriod`, `computePresupuestoParts`); flag `es_bimestral` mapeado desde `S.fixed.data`.
- **F-C:** mismo criterio propagado a la card/panel de Credito.
- **F-D:** sorts de fecha null-safe (Inversiones/Ingresos); eliminado `console.log('[CUOTAS DEBUG]')`.
- **Auditado sano sin tocar:** Deuda (card/panel/saldar coherentes), carga inicial con manejo de errores, Inversiones.
- **Decisiones (sin cambios de codigo):** DEC-029 (ingreso pago='Comun' no se modela, se divide por fuera), DEC-030 (gasto variable en mes 100/0 se mantiene dinamico).
- **Deuda tecnica aceptada:** H1 (API publica, uso de la pareja), H8 (logica shared/personal duplicada en 4+ lugares — candidata a unificar en helper).
