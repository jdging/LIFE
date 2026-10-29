# Contexto Actual - LIFE

## F4 QA2 — tres P2 finales corregidos en candidato aislado (2026-10-29)

En `f4-qa2-frontend`, la UI de Supermercado actualiza los borradores limpios al recibir valor y versión más nuevos del servidor; elimina los limpios de productos dados de baja y conserva los sucios como conflicto. El gate exige consistencia semántica de faltante, porcentaje, estado y resúmenes, incluyendo `0/0` como Vacío y categorías sin productos, con tolerancia numérica pequeña. La reconciliación por ID retira los `TextNode` transitorios de carga/error cuando un GET válido pinta productos, sin reemplazar inputs ni acciones ni disparar PATCH. Hay regresiones candidatas para los tres hallazgos. El implementador no ejecutó tests ni producto en este wrapper: el coordinador debe repetir Node/Chromium y nueva revisión. La validación API/PDF remota por Viktor y la aceptación visual/funcional de Juan y R.P. siguen pendientes. Sin cambios en producción, main, backend, DB real, infraestructura, recetas ni PDF; sin commit, push, merge o publicación.

## Estado candidato F2 punto 8 — 2026-10-27

En `lab/reinvencion` candidato `f2-tarjeta`, el dashboard de laboratorio, la API local y `telegram_ingesta.py` dejan de solicitar o mostrar identificación de tarjeta/banco en los gastos. Se mantienen `medio_pago` Crédito/Débito y `cuotas_total`; Telegram conserva la pregunta consolidada de faltantes y la confirmación explícita. La tabla y columna históricas permanecen en SQLite, sin migración destructiva. Las respuestas de gastos de la API y los futuros exports omiten `tarjeta_id`; el catálogo `/api/tarjetas` se retira del contrato. El procedimiento candidato está en `lab/PROCEDIMIENTO-TELEGRAM-F2.md`, con pasos para actualizar el procedimiento externo. `src/lab-dashboard/data/gastos.json` se regeneró sin `tarjeta_id` (189 filas, sin otros cambios; la base SQLite no se tocó). Pruebas sintéticas verdes (pytest 642, node 21). Procedimiento externo actualizado. No hubo despliegue ni modificación de producción.

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

## Integración CRUD LIFE (candidato aislado `lab/reinvencion`, t_ce790609) — cierre de suite (2026-10-17)

> Este bloque describe trabajo hecho en `candidates/integration-crud-v1`
> (copia aislada), **NO** en `lab/reinvencion` real ni en `main`. No
> representa el estado del repo real de Área Viva/Brain hasta que Juan lo
> acepte y el coordinador lo integre.

- **Alcance del hito:** API HTTP local (`api.py`) + dominio de fijos con
  reparto explícito/dinámico (`db.py::resolve_fixed_split`, historial de
  versiones del mismo día) + formularios (`src/lab-dashboard/app.js`,
  `index.html`, `style.css`) + proxy Vercel (`middleware.js`).
- **Estado de revisión:** Revisor de código APTO (run `a9042de1`). QA
  Codex APTO (run `e7916108`). Suite de integración verde con los ajustes
  de esta sesión (ver `INTEGRACION.md` para el detalle de archivos,
  comandos y pendientes).
- **Ajuste de esta sesión — reparto de fijos personal vs. explícito:**
  `db.py` exige que `tipo_proporcion`/`proporcion_jd` explícitos solo
  correspondan a responsable `Común` (un fijo de `JD`/`Pinki` ya tiene
  100/0 implícito; pasarlo explícito es redundante y ahora se rechaza con
  `FixedSplitError`). `migrar_datos_reales.py` y los tests afectados
  (`test_finanzas.py`, `test_migracion.py::TestGastosFijosResponsable`) se
  alinearon a esa semántica — `db.py` no se tocó, la validación es
  intencional.
- **Dataset real excluido a propósito:** este candidato no trae
  `finanzas_raw.json` (dato real). El test que depende de él
  (`TestSanityCheckDatasetReal`) queda `@unittest.skip` documentado; solo
  debe correr en el repo real, con backup, antes de integrar.
- **`api-contract.md`** realineado al contrato ya implementado en
  `api.py`/`README-api.md` + proxy/`README-proxy.md`: dos capas de auth
  (cookie `dashboard_session` del navegador, `X-Internal-Proxy-Secret`
  interno proxy→API), sin URLs/secretos/servicios inventados.
- **Pendientes explícitos (no prometidos como resueltos):** activación de
  infraestructura real (VPS + Vercel), QA manual de Juan sobre el
  conjunto completo, y correr `TestSanityCheckDatasetReal` en el repo real
  una vez exista `finanzas_raw.json` + backup.
- **Nota de proceso:** esta sesión no tuvo acceso a una herramienta de
  ejecución de shell; la resolución de los puntos de test se verificó por
  lectura/trazado manual del código, no por una corrida real de
  `pytest`/`node`. El coordinador debe correr los comandos listados en
  `INTEGRACION.md` y confirmar el resultado antes de dar la suite por
  cerrada.

## F1 fix4: hallazgos del revisor independiente (NO APTO) + QA (candidato aislado `f1-correcciones`, t_38a7253f) (2026-10-27)

> Trabajo en `candidates/f1-correcciones` (copia aislada de F1, que ya
> incluía fix1-3), **NO** en `lab/reinvencion` real ni en `main`. No toca
> tarjeta/banco (F2) ni gráficos/filtros (F3).

- **Alcance del hito:** 6 correcciones puntuales sobre F1 (puntos
  1,2,6,7,10,12 del plan por fases de Juan) a partir de un dictamen
  **NO APTO** de un revisor independiente + QA, todas dentro de
  `lab/db.py`, `lab/api.py` y `src/lab-dashboard/app.js`.
- **Hallazgo 1 (ALTA) — `saldar_todas_las_deudas` saldaba de más:** el
  endpoint `POST /api/expenses/saldar-todas` saldaba TODO gasto
  `pagado_por` JD/Pinki sin saldar, incluidos los pagados 100% por quien
  los pagó (sin deuda real) — el modal (`getDebtRows()` en `app.js`) ya
  excluía esos casos desde antes. Nuevo helper `db._pct_contraparte`
  replica el criterio del frontend; `saldar_todas_las_deudas` ahora salda
  EXACTAMENTE el mismo universo que la deuda neta.
- **Hallazgo 2 (ALTA) — validación después del commit:** el handler de
  `api.py` validaba los montos (y podía fallar con 422/500) DESPUÉS de que
  `db.py` ya había hecho el `UPDATE`/`commit`. Ahora `db._validar_monto_saldable`
  valida cada monto y el total se calcula ANTES del `UPDATE`, dentro de la
  misma transacción — el handler solo serializa.
- **Hallazgo 3 (ALTA) — snapshot de auditoría sin reservar la transacción:**
  `saldar_todas_las_deudas` ahora hace `BEGIN IMMEDIATE` antes del `SELECT`
  (mismo patrón que `delete_expense`), para que el snapshot de auditoría no
  quede desalineado con lo que el `UPDATE` termina tocando. Todo el flujo
  (SELECT + validar + UPDATE + auditar) corre en una sola transacción con
  rollback completo ante cualquier falla.
- **Hallazgo 4 (MEDIA) — `renderDeudaDetail` colspan roto:** tras quitar la
  columna "Mes" la tabla quedó en 8 columnas; el `tfoot` usaba
  `colspan="6"` + 3 celdas (9 columnas). Corregido a `colspan="5"`.
- **Punto 5 — cobertura:** test de edición de gasto con el atajo `jd_100`
  (antes solo existía para `pinki_100`).
- **Punto 6 — bug "Mitad y mitad":** el selector de Reparto enviaba
  `tipo_proporcion:'50/50'` literal, que el backend rechaza
  (`validaciones.TIPO_PROPORCION_VALIDOS` solo admite `'dinamico'`/
  `'custom'`). `collectForm` ahora lo traduce a `'custom'` + `proporcion_jd:50`,
  igual criterio que los atajos 100% JD/Pinki.
- **Verificación:** sin acceso a shell/ejecución en esta sesión — todo se
  verificó por lectura y trazado manual del código contra tests nuevos y
  existentes (`lab/tests/test_finanzas.py`, `lab/tests/test_api.py`,
  `src/lab-dashboard/tests/forms.test.mjs`). Pendiente que el coordinador
  corra `pytest`/`node --test` y confirme el resultado antes de integrar.
- Detalle completo en `docs/BITACORA.md` (entrada `[2026-10-27]`) y en
  `report.md`.

## F1b: correcciones del QA manual de Juan sobre F1 (candidato aislado `f1b-qa-juan`, t_38a7253f) (2026-10-27)

> Trabajo en `candidates/f1b-qa-juan` (copia aislada de F1 ya integrada,
> en `f98e2d0`), **NO** en `lab/reinvencion` real ni en `main`. No toca
> tarjeta/banco (F2) ni gráficos/filtros (F3).

- **Alcance del hito:** 2 hallazgos del QA manual de Juan por Telegram
  sobre F1 (categorías sugeridas en fijos, y tabla de detalle de gastos
  confusa con filtro de persona activo), dentro de `lab/db.py`,
  `lab/validaciones.py`, `lab/api.py`, `src/lab-dashboard/app.js` y
  `src/lab-dashboard/style.css`.
- **Hallazgo A — fijos sin categorías sugeridas:** el formulario de alta/
  edición de fijo usaba un `<input>` de texto con un `datalist` armado
  desde los fijos YA cargados (categoría vacía en todos), así que nunca
  sugería nada, sin ningún aviso. Ahora usa el mismo catálogo de
  `/api/categories?tipo=Gasto` que el formulario de gasto, con `<select>`
  Categoría + `<select>` Subcategoría dependiente (`formFixedCategorySelects`,
  reutiliza `onExpenseCategoriaChange()`). A diferencia del form de gasto:
  ambos selects son OPCIONALES (igual que valida el dominio), y un valor
  guardado que ya no está en el catálogo se conserva como opción extra en
  vez de perderse. Si el catálogo falla, se muestra el mismo aviso que
  gasto y se cae a texto libre + datalist armado desde los fijos cargados
  (`formFixedCategoryText`) — nunca un input libre silencioso.
  - Backend: `gastos_fijos.subcategoria` (columna ya existente) ahora se
    valida, se acepta en alta/edición y se versiona con herencia igual que
    `categoria` (`db.crear_version_fijo` ya no la hardcodea a la versión
    anterior).
- **Hallazgo B — tabla de detalle de gastos confusa:** con un filtro de
  persona activo, la columna "Monto" mostraba solo la porción de esa
  persona (igual que "$ JD"/"$ Pinki", que SÍ parten del total), haciendo
  parecer un error donde cada número ya era correcto por separado. Ahora
  "Monto" siempre muestra el TOTAL del gasto (`monto_propio`); con un
  filtro de persona activo, se resalta con una clase CSS la columna de esa
  persona (`.td-persona-jd` / `.td-persona-pinki`). El ordenamiento por
  "Monto" pasó a ordenar por ese total, no por la porción filtrada. Los
  cards/totales y el resumen imprimible no se tocaron (no dependen de la
  tabla de detalle).
- **Verificación:** sin acceso a shell/ejecución en esta sesión — todo se
  verificó por lectura y trazado manual del código contra tests nuevos y
  existentes (`lab/tests/test_fijos.py`, `lab/tests/test_api.py`,
  `src/lab-dashboard/tests/forms.test.mjs`), incluido el riesgo de romper
  harnesses `vm.runInNewContext` con slices parciales de `app.js` al
  extender la carga de catálogo a los formularios de fijo. Pendiente que
  el coordinador corra `pytest`/`node --test` y confirme antes de integrar.
- No se encontró `captura-qa.jpg` en la raíz del workdir — se trabajó con
  la descripción textual del hallazgo B, suficiente para identificar la
  causa exacta.
- Detalle completo en `docs/BITACORA.md` (entrada `[2026-10-27] F1b`) y en
  `report.md`.

## F1b-fix2: hallazgos del revisor (NO APTO) sobre F1b + QA (candidato aislado `f1b-qa-juan`, t_38a7253f) (2026-10-27)

> Mismo candidato aislado `candidates/f1b-qa-juan`, **NO** en
> `lab/reinvencion` real ni en `main`.

- **Alcance del hito:** 2 hallazgos del revisor independiente sobre la
  sesión F1b anterior (dictamen NO APTO) + 2 ítems de cobertura pedidos por
  QA, dentro de `lab/db.py`, `lab/validaciones.py`, `lab/api.py`,
  `src/lab-dashboard/app.js` y sus tests.
- **Hallazgo 1 — fail-closed real sin catálogo en el form de fijo:** F1b
  dejaba que `openForm()` cayera a `formFixedCategoryText` (texto libre) si
  el catálogo de categorías fallaba o venía vacío, con "Revisar" habilitado
  igual. Ahora el form queda bloqueado por completo (ni nombre ni monto
  editables), con un aviso y un botón "Reintentar" (`retryFixedCatalog`,
  vuelve a pedir el catálogo); `#form-submit` queda oculto/deshabilitado
  mientras no haya catálogo válido, con el mismo chequeo repetido en
  `handleFormSubmit` como defensa en profundidad. Gasto no cambió (no fue
  objeto de este hallazgo).
- **Hallazgo 2 — "Sin categoría/subcategoría" en edición no vaciaba el
  valor:** el campo vacío se omitía y `crear_version_fijo` heredaba de la
  versión vigente, así que no había forma de vaciar una categoría/
  subcategoría ya asignada. Ahora hay semántica explícita: campo AUSENTE =
  heredar; `null` EXPLÍCITO = vaciar. `db.resolve_fixed_categoria` (mismo
  patrón de centinela `_FIXED_UNSET` que ya usaba `resolve_fixed_split`
  para el reparto) resuelve categoría/subcategoría de la nueva versión;
  vaciar `categoria` sin tocar `subcategoria` vacía ambas en cascada. Regla
  de dominio nueva (validada en `validaciones.validar_gasto_fijo`, en
  `api.py` antes de escribir, y en el propio `collectForm` del dashboard):
  no puede quedar `subcategoria` sin `categoria` — se rechaza con `400`.
  `app.js` manda `null` explícito cuando el usuario elige "Sin…" sobre un
  valor existente, y omite el campo si no cambió; cambiar la categoría
  resetea el `<select>` de subcategoría (comportamiento ya existente de
  `onExpenseCategoriaChange`), así que la vieja nunca viaja heredada junto
  a una categoría nueva.
- **Cobertura QA:** orden DESCENDENTE por "Monto" con filtro de persona
  activo (ya existía el ascendente); combinación categoría-en-catálogo +
  subcategoría-fuera-de-catálogo en el form de edición de fijo.
- **Decisión documentada:** la regla cruzada "subcategoria sin categoria"
  devuelve `400`, no `422` — en este contrato las validaciones de payload
  nuevo de escritura devuelven `400`; `422` se usa para datos
  almacenados/acumulados inválidos (ver `lab/README-api.md`), con la
  excepción documentada de `GET /api/categories` (`tipo` ausente/inválido).
  Si Juan prefiere `422` literal para esta regla puntual, es un cambio acotado.
- **Verificación:** sin acceso a shell/ejecución en esta sesión — todo se
  verificó por lectura y trazado manual contra tests nuevos y existentes,
  incluido confirmar que las funciones nuevas de `app.js`
  (`renderFixedCatalogBlocked`/`retryFixedCatalog`) caen dentro del slice
  que usa `makeExpenseFormHarness` en `forms.test.mjs`. Pendiente que el
  coordinador corra `pytest`/`node --test` y confirme antes de integrar.
- Detalle completo en `docs/BITACORA.md` (entrada `[2026-10-27] F1b-fix2`)
  y en `report.md`.

## Estado del candidato F1b-fix6 (2026-10-27)

- Candidato aislado `f1b-qa-juan` en `lab/reinvencion`, sin cambios en `main`, datos productivos, tarjeta ni despliegue.
- El historial de gastos fijos muestra categoría y subcategoría por versión. Compara ambos campos y etiqueta las altas, modificaciones y limpiezas; las versiones legacy sin valores muestran «Sin categoría» y «Sin subcategoría».
- El resumen «Revisar» de una edición de fijo combina el payload con la fila actual: omitido hereda, `null` vacía y un string reemplaza. Vaciar categoría sin enviar subcategoría también se refleja como subcategoría vacía, igual que en el backend.
- `loadCategoriasGasto()` valida la estructura completa antes de cachear: `categories` debe ser un array no vacío; cada entrada debe tener nombre de categoría string no vacío y `subcategorias` array de strings no vacíos. Una respuesta malformada mantiene el formulario de fijo bloqueado con «Reintentar». El formulario de gasto conserva su fallback de texto libre.
- Regresiones agregadas en `src/lab-dashboard/tests/fijos.test.mjs` y `src/lab-dashboard/tests/forms.test.mjs`. **Sin ejecución de tests en esta corrida por instrucción del wrapper**; cualquier conteo anterior no corresponde a fix6. Ver `report.md` y la entrada F1b-fix6 de `docs/BITACORA.md`.

## Candidato F4 Supermercado — 2026-10-28

En la copia filtrada de `lab/reinvencion`, F4 suma tablas `supermercado_*` vacías al init idempotente, API autenticada, proxy con descarga PDF binaria y pestaña Lab para categorías, productos, stock e historial. Cálculos y orden canónicos en servidor; PDF A4 con ReportLab. Las decisiones y el procedimiento de QA están en `docs/F4-SUPERMERCADO-QA.md`. Los originales de planilla/macro no están presentes; no se atribuyen catálogos ni ponderación a ellos. Por la prohibición de ejecutar tests y producto en esta corrida, código y pruebas quedaron sin verificar por ejecución; los dos PDF sintéticos se generan con `lab/generar_demo_supermercado.py` cuando QA habilite ejecución. No se tocó main, producción, recetas, DB cotidiana ni servicios.

## Candidato F4 v2 — corrección acotada y QA local (2026-10-28)

- El coordinador ejecutó QA sobre v1: Python **645 passed / 1 failed / 1 skipped**, Node **24/24**, y generó PDF A4 sintéticos de **1 y 10 páginas**. El fallo Python provenía de `test_validation_auth_and_category_order`: usaba barra + `n` literal donde se quería un salto de línea real. En v2 el test del control usa el salto real y otro test verifica que barra + `n` sigue siendo un nombre válido. No se cambió el validador de producto.
- `docs/F4-SUPERMERCADO-QA.md` dirige `TMPDIR` y `--basetemp` a un temporal externo al repo, necesario para la suite completa de retención Telegram. El venv del ejemplo también queda allí.

- QA web manual bloqueado: no se entregó harness WSGI porque no se puede tratar la API directa como proxy autenticado del dashboard. La guía enumera las barreras necesarias para un harness futuro; no se arrancó servidor ni se alteraron gateway, middleware o servicios.
- El implementador **no ejecutó pruebas ni producto en v2**. Los resultados de v1 son evidencia anterior, no verificación del cambio actual. El coordinador debe correr los comandos de la guía; Juan no aprobó QA. Sin cambios en main, producción, recetas, planilla real, DB cotidiana, commit, push, merge o deploy.

## Candidato F4 v3 — revisión y QA reproducible (2026-10-28)

La versión optimista persistida de cada producto obliga a enviar `expected_version` en PATCH/DELETE, incluido stock. Un dato obsoleto da 409 y se recarga la UI sin reintentar escritura; operaciones rechazadas no auditan. Migración v1 idempotente; bajar categoría incrementa versiones y audita snapshots. Lectura de categorías/productos/resumen en snapshot SQLite. Historial paginado de 50 eventos, cursor validado y estados `next_cursor`/`has_more`; 1000 productos y 100 categorías activos como límites técnicos del lab. Proxy y tests se ampliaron para F4. `lab/qa_supermercado.py` crea DB sintética nueva en directorio explícito y sirve dashboard/API in-process solo en loopback con Basic de prueba, Host/Origin estrictos y assets allowlist. El implementador no corrió tests, producto ni servidor. El coordinador debe ejecutar QA offline; Juan debe hacer QA de navegador y decidir ponderación agregada. Originales XLSX/BAS ausentes; PDF mantiene limitación CP1252. Sin aprobación de Juan, commit, push, merge ni deploy.

## Candidato F4 v4 — carrera UI y trazabilidad (2026-10-28)

La recarga de Supermercado ahora conserva el refresh forzado cuando hay un GET anterior pendiente: invalida la respuesta vieja, serializa la lectura posterior al PATCH y devuelve su promesa a `superMutate`. Así, la confirmación y el cache usan el stock y la versión posteriores; reabrir la pestaña reutiliza ese snapshot. Se agregaron pruebas de carrera con promesas diferidas y de PATCH general exitoso (nombre, unidad, categoría, deseado, actual, versión y auditoría) más validación rechazada sin mutación. `api-contract.md` refleja las capabilities reales de health (`inventory` y `supermercado`). El implementador no ejecutó tests ni producto en v4; el coordinador debe repetir QA.

Evidencia **previa a v4**, ejecutada por el coordinador sobre v3: `evidencia/pytest-v3-final.log` 655 passed/1 skipped (`test_migracion.py:344` requiere `finanzas_raw.json` real ausente a propósito), `evidencia/node-v3.log` 27/27, navegador Chromium 390×844 para alta decimal/historial/stock/descarga/«No falta nada» y 1280×900 para submit real de edición/XSS como texto/historial/PDF/conflicto entre dos contextos, ambos sin errores de consola. PDF demo v3 regenerados y descargas A4 leídas. Esto no verifica v4 ni equivale a aceptación de Juan; siguen pendientes QA web de Juan, revisión visual/UX de R.P., originales XLSX/BAS, límite CP1252 y decisión de ponderación por conteo.

El snapshot de revisión v3 omitió `marca/jdg/` por el filtro del coordinador; no hubo eliminación en el candidato. `.lasso-runs` es evidencia operativa del wrapper, fuera del diff integrable. `evidencia/f4-v3.patch` y `evidencia/f4-v3-manifest.json` enumeran 20 archivos, y `git apply --check` pasó sobre repo limpio sin aplicar el parche. El coordinador generará el diff v4. Sin cambios en main, recetas, producción, planilla real, servicios, commit, push, merge ni deploy.

## Candidato F4 v5 — ámbito del banner y escritura de Supermercado (2026-10-28)

QA v4 del coordinador (`f5d720a0-59de-4e96-9729-a5d2977b9a66`) fue apto con observación P2: cuando `/api/health` falla en el harness aislado, el banner global afirmaba que todo estaba en solo lectura aunque la API propia de Supermercado permitía guardar. En v5 el banner identifica Finanzas y otros módulos, y la pestaña Supermercado expone su estado propio. Un GET protegido de `/api/supermercado` con estructura válida habilita sus controles y `superMutate`; antes del GET, tras lectura fallida o mutación 401/403, se niegan escrituras. Un GET invalidado no puede restablecer el permiso tras un fallo nuevo. Se mantienen `expected_version`, la recarga serializada v4, autenticación de cada operación y el harness sin endpoints financieros. Pruebas VM dinámicas cubren esas transiciones y el texto del banner. El implementador no ejecutó tests ni producto en v5; resultados v4 (Python 656/1 skipped, Node 28/28, Chromium móvil y desktop sin errores) son evidencia anterior. Siguen pendientes QA manual de Juan, Safari/iPhone físico, autenticación Vercel real, originales XLSX/BAS, ponderación por conteo, CP1252 y revisión visual de R.P. Sin recetas, main, planilla/DB real, commit, push, merge ni deploy.

## Integración F4 sobre F3 para preview (2026-10-29)

Base del workdir: `origin/lab/reinvencion` `d636a6cc763c3751f2b02585a7014fbf66e1c228`, con F3 aprobado por Juan. La rama de prueba prevista es `lab/supermercado-f4`; commit y push corresponden al coordinador tras revisar y ejecutar QA. El hash publicado y la URL/status de Vercel siguen pendientes. F4 se fusionó semánticamente en los tres archivos de UI compartidos; F3 conserva gráficos, filtros, historia mensual, meses e ingresos y sus tests no se editaron. El resto de F4 v5 se integró como delta sobre archivos idénticos a la base anterior.

El lock frontend de Supermercado serializa mutaciones de la misma pestaña, incluido un doble submit de alta, y mantiene controles bloqueados hasta completar el refresh. Se libera en `finally`, pero 401/403 o fallo de lectura mantienen el módulo sin permiso de escritura. Las pruebas dinámicas nuevas quedaron sin ejecutar en esta corrida, junto con el resto de suites; ver `docs/F4-SUPERMERCADO-QA.md`. El lock no aporta idempotencia de backend ni deduplicación entre clientes. `docs/F4-PREVIEW-API.md` contiene el mensaje para Viktor y el procedimiento de preview/backend aislado. Lasso no actualizó API, infraestructura ni DB; sigue pendiente QA manual de Juan y decisión de aceptación. Originales XLSX/BAS ausentes, porcentaje agregado por conteo y límite WinAnsi/CP1252 del PDF siguen abiertos.

## Candidato F4 QA2 web — revisión de Juan (2026-10-29)

El candidato filtrado de `lab/reinvencion@5e6f519` implementa puntos 1–6 y 8 del segundo QA web de Supermercado; PDF corresponde a otro task. El frontend sigue en HTML/CSS/JS vanilla y reutiliza tokens visuales. Administración de categorías/productos se pliega; stock diario se agrupa por orden de servidor y muestra unidad, estado, faltante/excedente y cobertura por producto. Gráficos DOM general/categoría cuentan productos y calculan cobertura normalizada por producto elegible; no suman unidades incompatibles. Historial modal usa auditoría real paginada y SVG local, cierra con X/Escape/Cerrar y restaura foco. Stock se lee automáticamente sin escritura y solo se guarda tras edición válida humana con debounce/blur/Enter, PATCH versionado, GET verificador, cola por producto y conflicto 409 explícito. El gate propio de Supermercado permanece cerrado sin GET válido o tras 401/403. Formularios de alta/edición conservan confirmación y lock de doble clic. Tests de Supermercado se actualizaron/agregaron; F3 no se tocó. La sintaxis pasó `node --check`; el coordinador ejecutará suites/producto, y Juan/R.P. revisarán UX/visual. Sin publicación ni aceptación de esta versión.

Ajuste final: el gráfico histórico filtra puntos a la unidad actual para no unir magnitudes incompatibles; la lista muestra la unidad y categoría anterior/posterior. Si un producto desaparece mientras hay borrador, éste se conserva visible para descarte explícito. El panel de stock precede a gráficos y administración.

## F4 QA2 web — corrección del informe WEB P1/P2 (2026-10-29)

El informe WEB `a16d4e0e-dff4-4a97-b72e-4568f96f78dc` calificó el candidato anterior **NO APTO**: PATCH paralelos de productos invalidaban mutuamente sus GET verificadores, el gate aceptaba snapshots sin IDs de categoría requeridos y el historial podía confundir el nombre actual con el histórico. En este workdir autorizado, el autosave usa cola única de módulo para PATCH + GET, guarda el último borrador por producto sin bloquear edición, difiere foco/poll durante verificación y pausa la cola ante error para reintento explícito. Las acciones administrativas no interrumpen el verificador. El gate comprueba categorías y resumen canónicos, referencias, duplicados, conteos y cantidades; un snapshot corrupto cierra escrituras. El historial muestra `#id` y aclara si un nombre es actual o si la categoría ya no existe; no inventa nombres históricos.

Se añadieron pruebas deterministas para esas carreras, gate, pausa y auditoría de categorías, y se adaptaron pruebas existentes a las lecturas coalescidas. **El implementador no ejecutó producto ni tests en este wrapper.** Node 46/46, Python 663 aprobadas/1 omitida/1 warning fitz y Chromium básico son evidencia anterior al cambio actual; el navegador avanzado tuvo timeout. El coordinador debe repetir pruebas, verificar en navegador y presentar esta versión a Juan; la revisión visual de R.P. sigue pendiente. No hay aprobación de Juan ni publicación. Alcance y límites detallados en `docs/F4-QA2-FRONTEND.md`.

## F4 QA2 web — corrección de identidad DOM y foco (2026-10-29)

Después de que `782fb0f3` superara Node 55/55, el coordinador reprodujo en Chromium una segunda pérdida de edición: `handleSuperStockBlur()` reconstruía `supermercado-content` al salir de un campo limpio, eliminaba el siguiente input o botón antes del click/focus y la edición no llegaba a PATCH. El `finally` de un guardado podía reconstruir otra fila. En este candidato, `renderSupermercadoList()` reconcilia secciones y artículos por ID; las lecturas y verificaciones actualizan metadatos, estado, barras y resúmenes sin reemplazar inputs ni acciones. El valor de un input sin borrador se sincroniza cuando deja de estar enfocado. Cambios de agrupación mueven el mismo artículo y recuperan foco/caret; el filtro explícito y los borradores se conservan. Pruebas nuevas de funciones reales cubren la transición hacia otro stock e Historial, metadatos y GET tardío con reagrupación.

**Pendiente:** esta corrección no tiene pruebas ejecutadas en el wrapper. El 55/55 era previo; el coordinador debe repetir Node y Chromium en 320/390/768/1280 más el escenario avanzado. No hay aceptación de Juan ni publicación. Solo se editaron rutas F4 QA2 frontend/pruebas/documentación autorizadas; no se tocó backend, DB real, main, infraestructura, recetas ni PDF.
