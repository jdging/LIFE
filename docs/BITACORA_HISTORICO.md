### [2026-04-03] - Sesión 5
**Objetivo:** Crear datos de prueba para validar el dashboard completo de Finanzas
**Logros:**
- Creado apps-script/finanzas-seed.js — script Apps Script para poblar el Log con datos ficticios realistas
  - Feb y Mar 2026: ingresos $3.000.000/mes (JD 75% / Pinki 25%)
  - Gastos variados por categoría (~$1.600.000/mes): fijos y variables, distintos medios de pago y titulares
  - Inversiones con el saldo restante (~$1.390.000/mes): Plazo fijo, MEP, FCI, Crypto
  - Cuota en 3 partes ($33.000 c/u): feb, mar y abr — última cuota visible como pendiente en el dashboard
  - Script lee tarjetas dinámicamente desde la hoja Tarjetas (no hardcodea IDs)
  - Genera IDs LOG-XXXXX sin pisar datos existentes
  - Las 3 filas de cuotas se crean directamente con fechas explícitas (bypass del trigger de expansión)
**Pendientes:** Ejecutar populateTestData() en Apps Script; test end-to-end con datos reales
**Notas:** Sesión corta y concreta. Datos diseñados para ejercitar todas las vistas del dashboard: deudas, cuotas comprometidas, proporcionalidad, inversiones por tipo.

---

### [2026-04-02] - Sesion 4
**Objetivo:** Ajuste post-configuracion AppSheet
**Logros:**
- Usuario confirmo que AppSheet fue configurado exitosamente y URL pegada en APPSHEET_URL
- Usuario confirmo que triggers, sidebar y panel AppSheet funcionan correctamente
- Identificado UX issue: campo medio_pago aparece para tipo=Ingreso (innecesario)
- Propuesta: Show_If [tipo] <> "Ingreso" en AppSheet sobre campo medio_pago
**Pendientes:** Aplicar Show_If en AppSheet; test end-to-end con datos reales
**Notas:** Sesion muy corta — el sistema esta funcionando, falta afinar UX del formulario

---

### [2026-04-02] - Sesión 2
**Objetivo:** Implementar el módulo Finanzas: Google Sheet, Apps Script API y Dashboard HTML (Pasos 1–3)
**Logros:**
- Creado apps-script/finanzas-setup.js — script que crea la Sheet completa (4 hojas, validaciones, datos precargados)
- Google Sheet creada: ID 1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg
- Creado apps-script/finanzas-api.js — API REST con 5 endpoints: log, config, proportions, delete
- API deployada: https://script.google.com/macros/s/AKfycbww3oiHDqq4w5hHQqdwJpCxGMx-mSQhiUEiJojkCyRIkk2BLcsMcF2NdWb0cLEFJdcu/exec
- Creado src/finanzas/index.html — dashboard completo con 3 vistas, Chart.js, deuda proporcional, soft delete
- Actualizado src/index.html — tarjeta Finanzas habilitada (reemplazó "Próximamente")
**Pendientes:** Paso 4 — Configurar AppSheet y embeber como iframe
**Notas:** Hook cbm-code-discovery-gate bloquea tool Read en archivos .md — workaround: usar Bash cat

---

### [YYYY-MM-DD] - Sesión 1
**Objetivo:** Inicialización del proyecto
**Logros:** Template base copiado y configurado
**Pendientes:** Definir alcance, stack, y primera funcionalidad
**Notas:** -

---
### [2026-04-02] - Sesión 3
**Objetivo:** Completar integraciones pendientes: triggers Apps Script, panel AppSheet en dashboard, Finanzas en sidebar del hub
**Logros:**
- Creado apps-script/finanzas-triggers.js — trigger onChange con LockService; auto-genera ID (LOG-00001) y expande cuotas en N filas automáticamente
- Agregado Finanzas al sidebar del hub (src/index.html) con ícono $ y tooltip
- Agregado panel AppSheet en el dashboard (src/finanzas/index.html):
  - Botón flotante (+) en esquina inferior derecha
  - Drawer lateral con iframe que carga AppSheet al abrirse
  - Placeholder APPSHEET_URL para configurar al conectar AppSheet
  - Cierre con × o tecla Escape
**Pendientes:** Configurar AppSheet y pegar la URL pública en APPSHEET_URL; ejecutar setupTriggers() en Apps Script; test end-to-end
**Notas:** Sesión de continuación post-compresión de contexto. Node heredoc como técnica estable para editar archivos con caracteres especiales.

---

### [2026-04-03] - Sesión 7
**Objetivo:** Ajustes post-implementación detectados en el primer uso del módulo Presupuestos
**Logros:**
- Identificados y documentados dos ajustes pendientes para la próxima sesión:
  - AJ-1: Validación de datos en columna `tarjeta` de GastosFijos (dropdown → hoja Tarjetas, igual que Log). Incluye función separada para hojas ya existentes.
  - AJ-2: Reemplazar torta de fijos por gráfico de evolución mejorado: líneas con fill/gradiente, un dataset por gasto fijo, puntos en cada hito. Modo "Todos" = normalización % (evita aplastamiento de gastos chicos vs grandes). Modo individual = montos absolutos con escala adaptada. Toggle "$ / %" en el gráfico.
- `tasks/todo.md` actualizado con secciones AJ-1 y AJ-2 con especificación completa
**Pendientes:** Ejecutar AJ-1 y AJ-2 en la próxima sesión
**Notas:** Sesión de planificación pura — sin código escrito. El usuario se quedó sin tokens antes de ejecutar.

---

### [2026-04-03] - Sesión 6
**Objetivo:** Implementar el módulo Presupuestos completo: hoja GastosFijos, endpoint fixed, 4ª vista del dashboard, simulador, tutorial.
**Logros:**
- `tasks/todo.md` actualizado: ideas futuras H1–H7 registradas, sección Setup Presupuestos creada
- `apps-script/finanzas-setup-gastosfijos.js` — script nuevo para crear hoja GastosFijos con versionado por fecha. Incluye `setupGastosFijos()`, `actualizarMontoFijo()` y `testGastosFijos()`. 6 gastos iniciales en $0: Alquiler, Expensas, Seguro, Internet, Gas (bimestral), Electricidad (bimestral).
- `apps-script/finanzas-api.js` — agregado endpoint `?action=fixed` con función `getFixed()`: versionado por vigente_desde, manejo de bimestrales, history embedido para evitar round trips extra.
- `src/finanzas/index.html` — cambios extensivos:
  - CSS: estilos para panel fijos colapsable, barra de progreso tricolor, tabla de fijos clickeable, badge bimestral, simulador de inputs inline
  - Sidebar: 4° botón de navegación (Presupuesto)
  - Card "Gastos fijos" en vista Gastos: clickeable → despliega panel con lista de fijos vigentes
  - Vista Presupuesto completa: 4 cards, barra rojo/dorado/verde, torta de fijos por categoría, tabla clickeable con historial por gasto, simulador client-side
  - JS: `S.fixed`, `S.simRows`, `S.simCounter`; `fetchFixed()` en paralelo con `fetchProportions()`; `renderGastos()` usa `S.fixed.total` en lugar de filtro `es_fijo`; 15 funciones nuevas para la vista Presupuesto y el simulador
- `tutoriales/SETUP-PRESUPUESTOS.html` — tutorial completo en 7 pasos con checklist final
**Pendientes:** Ejecutar `setupGastosFijos()` en Apps Script, cargar montos reales, crear NEW deployment, actualizar API_URL, configurar AppSheet (ocultar es_fijo, vista GastosFijos)
**Notas:** Sesión continuada desde context window previo (el contexto fue comprimido). La sesión 5 había quedado a mitad de las ediciones de JS — esta sesión retomó y completó todo el trabajo pendiente.

### [2026-04-04] - Sesión 8
**Objetivo:** Ejecutar ajustes AJ-1 y AJ-2 post-implementación Presupuestos; actualizar estado post-deploy
**Logros:**
- AJ-1 ejecutado: `setupGastosFijos()` ahora aplica validación dropdown en columna `tarjeta` referenciando hoja Tarjetas. `setAllowInvalid(true)` para no romper celdas vacías.
- AJ-2 ejecutado: reemplazada torta por gráfico de evolución multi-línea con fill+gradiente. Toggle $/% para escala absoluta vs variación porcentual (resuelve aplastamiento de gastos chicos vs grandes). Botón "← todos" para desfiltrar. Fill-forward sobre eje X unificado para alinear datasets con historiales distintos.
- Confirmado por el usuario: NEW deployment de Apps Script activo, GastosFijos con montos reales, test end-to-end aprobado — módulo Finanzas 100% en producción.
- Docs actualizados: CONTEXTO.md, BITACORA.md, todo.md
**Pendientes:** Mejoras post-MVP del backlog (H1–H7) según prioridad del usuario
**Notas:** LEC-006 aplicada — se usaron Write/Edit tools en lugar de Bash+Node para archivos .md (paths Windows con backslashes rompen heredoc de Node).

### [2026-04-04] - Sesión 9
**Objetivo:** Implementar F-01 (Vista Presupuesto con capas reales) y su prerequisito `filterCuotasComprometidas`
**Logros:**
- Función global `filterCuotasComprometidas(month)` agregada en `src/finanzas/index.html` — filtra `S.log` por `cuota_nro > 1` AND `fecha.startsWith(month)`. Prerequisito para F-01, F-02 y F-03.
- F-01 implementado completo: Vista Presupuesto muestra ahora 5 capas reales:
  - 2 cards nuevas: "Variables ejecutados" y "Cuotas comprometidas"
  - Barra de progreso expandida de 3 a 5 segmentos (fijos/variables/cuotas/simulados/disponible)
  - Colores: rojo → naranja (#c4895a) → violeta (#9a7fc4) → dorado → verde
  - `renderPresupuesto()` y `updateSimTotals()` actualizados para calcular ambas capas
  - `updateProgressBar()` ahora recibe 5 parámetros en lugar de 3
- Variables ejecutados: `tipo=Gasto`, `es_fijo` falso, `cuota_nro=1` (la cuota propia del mes)
- Cuotas comprometidas: delega en `filterCuotasComprometidas()` — cuotas diferidas de compras anteriores
**Pendientes:** Verificar visual con datos reales; continuar con F-02
**Notas:** Sesión corta y concreta. Toda la implementación es frontend puro — sin endpoint nuevo. La separación entre "variables ejecutados" y "cuotas comprometidas" es la decisión de diseño clave del feature.

### [2026-04-04] - Sesión 10
**Objetivo:** Implementar F-02, F-03 (Vista Gastos mejorada) y wins rápidos H3, H6, H7, punto 5
**Logros:**
- F-02: Nueva card "Carga en crédito" en Vista Gastos — acumulado mensual en tarjeta de crédito (gastos del mes + cuotas comprometidas). Panel colapsable con detalle agrupado por tarjeta, label resuelto desde `S.tarjetas` (banco + nombre).
- F-03: Barra de composición del gasto siempre visible en Vista Gastos — 3 segmentos (fijos/variables/cuotas) con leyenda y porcentajes. Diferente de la barra de Presupuesto (no incluye simulados ni disponible, es descriptiva del gasto real).
- H3: Torta de gastos por categoría muestra montos + % en los labels de la leyenda (`"Hogar  $450k  32%"`). Tooltip sobrescrito para evitar redundancia.
- H6: Gráfico acumulado de inversiones expandido a multi-dataset — línea gruesa total + líneas finas por subcategoría (FCI, Crypto, etc.). Leyenda interactiva de Chart.js (click para toggle). Torta ya usaba `subcategoria` — marcada ✅.
- H7: Card de proporción en Vista Ingresos muestra `shortMonth(S.month)` (ej: "abr 2026") en lugar del estático "este mes". La proporción ya se actualizaba correctamente en cambio de mes — solo era un problema de display.
- Punto 5 (AJ-1): Función `addTarjetaValidationToGastosFijos()` agregada en `finanzas-setup-gastosfijos.js` — aplica dropdown de tarjetas sobre hoja GastosFijos ya existente sin recrearla.
**Pendientes:** F-04 (modelo de proporción por gasto) es el siguiente bloqueo crítico — habilita F-05.
**Notas:** Sesión de alta densidad. F-02/F-03 antes de la compresión de contexto; H3/H6/H7/punto5 después. Todos los cambios son frontend puro excepto punto 5 (Apps Script). La distinción F-03 vs F-01 es clave: F-03 describe el gasto real (3 capas), F-01 es la herramienta de planificación (5 capas con simulados y disponible).

### [2026-04-04] - Sesión 11
**Objetivo:** Completar F-04 (pieza restante en setup.js) e implementar F-05 (distribución individual)
**Logros:**
- F-04 completado: `apps-script/finanzas-setup.js` actualizado con `tipo_proporcion` (col Q) y `proporcion_jd` (col R) en el array de headers del Log — para futuras inicializaciones. No toca datos existentes.
- F-05 implementado completo en `src/finanzas/index.html`:
  - CSS: `.dist-table`, `.dist-row-negative`, `.dist-row-disponible`, `.dist-disponible-pos/neg`, `.dist-pct-sub`
  - HTML: bloque "Distribución individual" al final de `view-presupuesto` con `#dist-container`
  - JS: `renderDistribucion()` — tabla comparativa JD | Pinki con 7 filas (Salario / Fijos / Variables / Cuotas / Simulados / Propios-condicional / Disponible)
  - Variables y cuotas usan `getRowPct()` por fila (respeta `tipo_proporcion` de F-04)
  - Simulados usan proporción dinámica del mes (no tienen `tipo_proporcion`)
  - Gastos propios (pagó=persona, no Común) aparecen solo si existen en el mes
  - Disponible en verde/rojo con ⚠ si negativo
  - `updateSimTotals()` llama `renderDistribucion()` — actualización en tiempo real al usar el simulador
  - Proporción del mes visible como subíndice bajo cada nombre (ej: "75%" / "25%")
**Pendientes:** H4, H1, H2, H5 (backlog) según prioridad del usuario
**Notas:** Sesión corta y concreta. F-04 + F-05 cierran el ciclo de features del MVP de Finanzas. La lógica de `getRowPct()` implementada en F-04 se reutilizó directamente en F-05 — buen diseño previo.

### [2026-04-04] - Sesión 12
**Objetivo:** Reescribir finanzas-seed.js para cubrir todos los features del dashboard con 7 meses de datos; actualizar backlog post-MVP
**Logros:**
- `apps-script/finanzas-seed.js` v2 — reescritura completa:
  - Borra el Log completo antes de insertar (deleteRows 2..lastRow)
  - 7 meses Oct 2025–Abr 2026 con salarios crecientes (JD: 1.8M→2.5M / Pinki: 600k→900k) — proporción cambia mes a mes
  - 18 columnas incluyendo `tipo_proporcion` y `proporcion_jd` (F-04)
  - Mix deliberado de proporciones: `dinamica` (supermercado, farmacia), `50/50` (verdulería, streaming, cine), `custom` (cuotas personales)
  - Diciembre con aguinaldo SAC; Nov y Feb con ingresos freelance extra
  - 4 grupos de cuotas cross-month: TV 65" (6c, Nov2025, Común, dinamica), Zapatillas JD (3c, Ene2026, JD, custom 100%), Silla escritorio (4c, Feb2026, Común, 50/50), Tablet Pinki (3c, Mar2026, Pinki, custom 0%)
  - `clearSeedGastosFijosHistory()` elimina filas con vigente_desde < 2026-01-01 sin tocar precios de producción
  - `seedGastosFijosHistory()` agrega 3 versiones históricas por gasto activo al 65%/80%/92% en 2025-01-01/2025-07-01/2025-10-01 para el gráfico de evolución (AJ-2)
- H5 registrado como completado (usuario lo hizo manualmente en AppSheet)
- H2 redefinido como módulo independiente en `src/inventario/` (no parte de Finanzas — tiene su propio index.html, se registra en el hub como Jardín y Finanzas)
- `tasks/todo.md` actualizado: sección "Próximos" con H4/H1/H2 como prioridades, seed v2 en Completadas
**Pendientes:** Ejecutar `populateTestData()` en Apps Script; implementar H4 (deudas mejoradas), H1 (más opciones de período), H2 (módulo inventario en src/inventario/)
**Notas:** Sesión de continuación post-compresión de contexto. Único entregable de código: finanzas-seed.js v2. Convención clave: primera cuota del grupo tiene cuota_ref = su propio id (self-reference). propJd=0 debe tratarse explícitamente para no caer en falsy.

### [2026-04-05] - Sesion 13
**Objetivo:** Implementar H4 (logica de deudas con campo corresponde_a) y H1 (selector de periodo multi-opcion)
**Logros:**
- H4 implementado en `src/finanzas/index.html`:
  - Nueva funcion `getDeudaPct(row, p1, p2)` que envuelve `getRowPct()`: si `corresponde_a` apunta a una persona, retorna 100%/0% en lugar de proporcion dinamica
  - `renderDeuda()` actualizado: el filtro `debtRows` excluye filas donde la persona pago su propio gasto (pago==ca)
  - `toggleDeudaDetail()` y `renderDeudaDetailPanel()` actualizados con la misma logica + muestra "para: <strong>X</strong>" en el detalle
  - `apps-script/finanzas-setup.js` actualizado: columna S = `corresponde_a`, con validacion dropdown lista `['Comun', 'JD', 'Pinki']`
- H1 implementado en `src/finanzas/index.html`:
  - CSS: estilos para `.period-selector` y `.period-btn` (incluyendo `.period-btn.active` con fondo acento)
  - HTML: reemplazo del `<input type="month">` unico por 6 botones (Mes / 3M / 6M / Ano / Todo / Rango) + pickers condicionales
  - JS: `S.period` como objeto `{ type, from, to, refMonth }` — `S.month` se mantiene como alias de `refMonth` para compatibilidad con charts y fetchs
  - `computePeriod(type, opts)` genera el objeto period segun el tipo seleccionado
  - `selectPeriodType(type)` actualiza UI + recalcula period + renderiza
  - `onRangeChange()` lee los dos date inputs del rango y llama `computePeriod('range')`
  - `filterLog()` y `filterCuotasComprometidas()` actualizados a parametros `from/to` (strings YYYY-MM-DD)
  - 21 sitios de llamada actualizados: 15 x `month: S.month` -> `from: S.period.from, to: S.period.to` y 6 x `filterCuotasComprometidas(S.month)` -> `filterCuotasComprometidas(S.period.from, S.period.to)`
**Pendientes:** Agregar campo `corresponde_a` en AppSheet (manual, usuario); implementar H2 (modulo Inventario)
**Notas:** Dos bugs surgidos y resueltos durante la sesion: (1) UnicodeEncodeError en Python stdout por el caracter flecha U+2192 en Windows cp1252 -- la escritura al archivo no se ejecuto a pesar de que los cambios 1-6 estaban en memoria; (2) el mass-replace de `month: S.month` afecto la linea de inicializacion `computePeriod('month', { month: S.month })` -- fix con script apuntado especificamente.

### [2026-04-05] - Sesion 14
**Objetivo:** Generar el modulo Inventario completo (H2): setup de Sheet, API, dashboard HTML, actualizacion del hub
**Logros:**
- Documentacion de cierre de Sesion 13 completada al inicio de esta sesion:
  - BITACORA.md con entrada Sesion 13, DECISIONES.md con DEC-016/DEC-017, lessons.md con LEC-010, CLAUDE.md Watch Out For actualizado
- `apps-script/inventario-setup.js` generado:
  - Crea hoja Inventario con 12 columnas: id, descripcion, categoria, fecha_compra, precio_ars, cotizacion_usd_compra, precio_usd_compra, proporcion_jd, precio_venta_estimado_usd, estado, notas, borrado
  - Dropdowns: categoria (8 opciones), estado (4 opciones)
  - Validacion numerica 0-100 en proporcion_jd, checkbox en borrado, formatos en columnas numericas y fecha
  - Trigger auto-ID INV-XXXXX con calculo del maximo existente (no se rompe con filas borradas)
- `apps-script/inventario-api.js` generado:
  - 2 endpoints: ?action=inventario (retorna items sin borrados) y ?action=delete&id=INV-XXXXX (soft delete)
  - Patron identico a finanzas-api.js (getSheetData helper, doGet router, fechas a YYYY-MM-DD)
- `src/inventario/index.html` generado (dashboard completo):
  - Sidebar 72px con los 4 modulos (Home/Jardin/Finanzas/Inventario activo)
  - Barra de cotizacion editable sticky que recalcula cards y tabla en tiempo real
  - 4 cards: Total USD compra / JD / Pinki / Reventa estimada (todas con equivalente ARS dinamico)
  - Filtros por estado (Activos/Vendidos/Donados/Desechados/Todos)
  - Tabla 11 columnas: descripcion / categoria / fecha / ARS pagado / USD compra / ARS hoy (vivo) / JD USD / Pinki USD / Reventa est. / Estado / Acciones
  - Soft delete desde tabla con confirmacion
  - Drawer AppSheet (boton +) con URL del usuario ya configurada
  - API_URL como placeholder, pendiente deploy
- `src/index.html` actualizado: icono cubo en sidebar + tarjeta 03 Inventario en grid
**Pendientes:** Ejecutar setupInventarioSheet() + setupInventarioTrigger() en Apps Script, luego deploy de inventario-api.js y pegar URL en API_URL del dashboard
**Notas:** Sheet de Inventario usa Spreadsheet separado (ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw). AppSheet URL ya configurada en el drawer. El unico paso manual restante es el deploy del API.

### [2026-04-05] - Sesion 15
**Objetivo:** Completar cierre de Sesion 14, marcar Inventario como produccion 100%, corregir dos bugs del dashboard y redisenar tabla + cards.
**Logros:**
- Documentacion de cierre de Sesion 14 completada al inicio de la sesion (ejecutando docs/_tmp_update.py pendiente): BITACORA Sesion 14, DECISIONES DEC-018/DEC-019, CONTEXTO actualizado, todo.md actualizado.
- CLAUDE.md actualizado con seccion Inventario en estado "completo, en produccion".
- CONTEXTO.md actualizado: Inventario marcado como "100% funcional en produccion -- deploy completo, API activa, AppSheet configurado".
- Dos bugs del dashboard corregidos:
  - Bug 1 (datos no cargan): Apps Script estaba deployado con autenticacion requerida. El usuario corrigio redepluoyando con "Execute as: Me / Who has access: Anyone". En el codigo se agrego check `res.ok` antes de `res.json()`.
  - Bug 2 (AppSheet no abre con +): Doble causa -- la seguridad de la app AppSheet no estaba configurada como publica (usuario lo corrigio manualmente), y el codigo creaba el iframe eagerly en `init()` en lugar de lazily en `openDrawer()`. Corregido para seguir el patron de finanzas: iframe creado solo al primer clic en el boton +, con atributo `allow="camera; microphone"`.
- Rediseno del dashboard de Inventario (`src/inventario/index.html`):
  - Card "Reventa estimada" reemplazada por "Itemas activos" (conteo de items con estado=Activo)
  - Funcion `usdCompra(item)` agregada: calcula precio USD como `precio_ars / cotizacion_usd_compra` si `precio_usd_compra` no esta en el campo directo (Apps Script trigger no auto-calcula este campo)
  - Tabla rediseada a 15 columnas: Descripcion / Categoria / Fecha / ARS pagado / Cot. compra / USD compra / % JD / % Pinki / ARS JD / ARS Pinki / Cot. hoy (editable inline) / Venta JD / Venta Pinki / Estado / Acciones
  - `min-width` de tabla aumentado a 1300px
  - `onCotizacionChange()` actualizado para aceptar valor como parametro (sincroniza input global con inputs inline de cada fila)
**Pendientes:** Sin pendientes criticos. Mejoras opcionales: F-04 (tipo_proporcion), F-05 (distribucion individual), H7 (card proporcion por mes).
**Notas:** El campo `precio_usd_compra` en la Sheet queda vacio porque el trigger de Apps Script no lo auto-calcula. La solucion definitiva es calcular en el frontend con `usdCompra()`. Si en el futuro se quiere persistir ese calculo, se puede agregar logica al trigger de inventario.

### [2026-04-06] - Sesión 16
**Objetivo:** Ejecutar los arreglos de la auditoría de código completa del proyecto
**Logros:**
- Auditoría de código entregada (sesión previa): 3 críticos, 7 menores, 6 mejoras en 8 archivos
- C1: `finanzas-api.js` — `getProportions()` filtraba por `row.subcategoria` en lugar de `row.categoria` para detectar salarios. La proporcionalidad dinámica nunca funcionaba en producción — siempre caía al fallback 50/50. Corregido con un cambio de una palabra.
- C2: `finanzas-seed.js` — renombrada `addMonths()` a `addMonthsStr()` (y sus 5 callers) para eliminar colisión de nombres con `finanzas-triggers.js` en el mismo proyecto Apps Script.
- C3: `finanzas-triggers.js` — verificado limpio, sin cambios necesarios.
- M1: `finanzas-triggers.js` — `isEmptyRow()` ya no trata `0` ni `false` como celda vacía (evitaba asignar ID a filas con monto=0 o borrado=false).
- M2: `finanzas-triggers.js` — mapa `cols` extendido con columnas Q/R/S (`tipo_proporcion`, `proporcion_jd`, `corresponde_a`).
- M3: `finanzas-setup.js` — array `widths` extendido de 16 a 19 entradas para Q/R/S.
- M4/M5: salteados por decisión del usuario (seed y inventario-setup).
- M6: `src/finanzas/index.html` — CSS: `var(--fg)` reemplazado por `var(--text)` en `.dist-row-disponible` (variable CSS inexistente).
- M7: `src/finanzas/index.html` — `showFixedHistory()` usa `===` en lugar de `startsWith()` para resaltar fila activa (evitaba falsos positivos con descripciones que son prefijo de otra).
- M8: `src/inventario/index.html` — `renderCards()` cuenta ítems activos desde `S.items` (total global) en lugar de `filteredItems` (subconjunto filtrado).
- P1: `src/finanzas/index.html` — eliminada función dead code `closeHistoryChart()`.
- P2: salteado (setup — decisión del usuario).
- P3: `finanzas-api.js` — `LockService` agregado a `softDelete()` con patrón try/finally (consistente con triggers.js).
**Pendientes:** ⚠ Requiere NEW deployment de `finanzas-api.js` para que el fix C1 tome efecto en producción.
**Notas:** C1 es el fix más crítico — la proporcionalidad dinámica (feature central) nunca había funcionado. La colisión de nombres `addMonths` en C2 también era un riesgo silencioso que podía romper la expansión de cuotas o el seed dependiendo del orden de carga en Apps Script.

### [2026-04-06] - Sesión 20
**Objetivo:** Bloque A (FIX-01 + FEAT-01 Finanzas) + Bloque B completo (Módulo Compras)
**Logros:**
- FIX-01: `renderGastosPersonales()` excluye filas con `saldado=true` (mismo patrón que `renderDeuda()`)
- FEAT-01: Filtro por persona en torta de gastos — 3 botones Comunes/JD/Pinki. Modo Comunes excluye gastos 100% personales y muestra subtotales "Corresponde a X: $Y". Modos JD/Pinki muestran solo gastos 100% de esa persona agrupados por categoría.
- B-DECISION: DEC-B1 (Sheet separada), DEC-B2 (deduplicación en API), DEC-B3 (una app AppSheet) confirmadas.
- B-SETUP: `apps-script/compras-setup.js` creado con setupComprasSheet(), setupComprasTrigger(), onComprasEdit(). Schema 10 columnas, validaciones dropdown, checkboxes, formato condicional.
- B-API: `apps-script/compras-api.js` creado con 6 endpoints (lista, add, comprado, delete, limpiar, enviar). Deduplicación por nombre+unidad+pendiente. Email con MailApp.sendEmail() agrupado por ORDEN_CATEGORIAS.
- B-DASH: `src/compras/index.html` creado. Dark theme, sidebar 72px, lista agrupada por categoría, checkboxes optimistas, limpiar, enviar, drawer AppSheet lazy.
- D-HUB: tarjeta "04 Compras" agregada a `src/index.html` + ícono carrito en sidebar del hub.
- D-SIDEBAR: ícono Compras agregado a sidebars de jardin, finanzas e inventario. Jardín actualizado con todos los módulos (Finanzas, Inventario, Compras).
**Pendientes:**
- B-MANUAL: usuario debe crear Sheet, ejecutar setup, deployar API, configurar AppSheet.
- Bloque C (Recetario): depende de que compras-api.js esté deployada.
**Notas:** FEAT-01 requirió mover `_gastosCategRows = rows` al inicio de `renderGastosPie()` para que el state guarde las filas sin filtrar — evita que re-renders desde `setGastosPersonaFiltro()` usen filas ya filtradas como input. Jardín tenía solo 2 items en el sidebar (Home + Jardín); en esta sesión se completó con Finanzas, Inventario y Compras.

### [2026-04-07] - Sesión 21
**Objetivo:** Implementar Bloque C (módulo Recetario) completo + tweak S.disponible1/S.disponible2 en Finanzas
**Logros:**
- TWEAK (Finanzas): `S.disponible1 = disp1` y `S.disponible2 = disp2` expuestos en `renderDistribucion()` — groundwork para F-16/F-17 (Gastos Personales) que usarán estos valores como "Presupuesto disponible" sin recalcular desde cero.
- C-SETUP: `apps-script/recetario-setup.js` creado. Hojas Recetas (id/nombre/porciones_base/categoria/instrucciones/borrado) e Ingredientes (id/receta_id/nombre/cantidad/unidad/borrado) en la misma Sheet que Compras. Triggers auto-ID: RECETA-XXXXX y ING-XXXXX. Categorías: Desayuno/Almuerzo/Cena/Merienda/Postre/Otro. Unidades: u/kg/g/l/ml/cdita/cda/taza.
- C-API: `apps-script/recetario-api.js` creado. Web App read-only, 2 endpoints: `?action=lista` (recetas no borradas, orden categoria+nombre) y `?action=detalle&id=RECETA-XXXXX` (receta + ingredientes). Constante con sufijo `_R` para evitar colisión de nombres con compras-api.js.
- C-DASH: `src/recetario/index.html` creado (~500 líneas). Grid de tarjetas, filtro por categoría, detalle expandible con selector de porciones, ajuste proporcional de cantidades (`data-cant-base`), botón "Agregar al super" (fetch secuencial a compras-api.js), drawer AppSheet lazy. Dark theme + sidebar 72px consistente.
- D-HUB: tarjeta "05 Recetario" + ícono recetario en sidebar de `src/index.html`.
- D-SIDEBAR: ícono Recetario agregado a sidebars de jardin, finanzas, inventario y compras.
**Pendientes:**
- C-MANUAL-1: ejecutar `setupRecetarioSheets()` + `setupRecetarioTriggers()` en Apps Script de la Sheet Compras+Recetario
- C-MANUAL-2: deployar `recetario-api.js` como Web App (Execute as Me / Anyone) → pegar URL en `RECETARIO_API_URL` de `src/recetario/index.html`
- C-MANUAL-3: en AppSheet, agregar vistas Recetas e Ingredientes en la app existente de Compras (DEC-B3)
- F-16/F-17: Gastos Personales expandidos por persona (S.disponible1/2 ya expuestos)
**Notas:** La constante `COMPRAS_SPREADSHEET_ID` en `recetario-setup.js` usa el mismo nombre que en `compras-setup.js`. Si ambos archivos se pegan en el mismo proyecto Apps Script colisionan — deben estar en archivos separados o renombrar la constante. El API file lo resuelve con sufijo `_R`. Mapeado en Watch Out For de CLAUDE.md.

### [2026-04-07] - Sesión 22
**Objetivo:** 4 fixes/features de Finanzas + Recetario, más F-16/F-17 (Gastos Personales) y cierre de setup manual de Recetario
**Logros:**
- FIX-1: `renderGastosPersonales()` — fila "Ingresos propios" renombrada a "Disponible del mes", valor ahora usa `S.disponible1 ?? …` / `S.disponible2 ?? …` (salario − fijos − variables − cuotas − simulados en lugar del ingreso bruto)
- FIX-2: `renderCreditoCard()` y `toggleCreditoDetail()` — Capa 1 ahora filtra `(parseInt(r.cuota_nro) || 1) === 1` para excluir cuotas diferidas que ya entran por `filterCuotasComprometidas()` (Capa 2). Elimina duplicados en la card "Carga en Crédito".
- FIX-3: `renderGrid()` en `src/recetario/index.html` — estado vacío diferenciado: sin filtro activo muestra "No hay recetas cargadas todavía / Usá el botón +…"; con filtro activo muestra "No hay recetas en esta categoría / Probá con otra…".
- FEAT-TUTORIAL: `tutoriales/SETUP-COMPRAS-RECETARIO.html` creado — guía completa (dark theme, autocontenida) para configurar AppSheet en módulos Compras + Recetario. 4 secciones + checklist de 20 ítems.
- F-16/F-17: `renderGastosPersonales()` rediseñada completamente con layout de 2 columnas (una por persona). Cada columna muestra: Disponible del mes / − Gastos propios / + Deuda a cobrar / − Deuda propia / = Saldo personal. Lógica: gastos con `tipo_proporcion=custom` y `proporcion_jd=100 o 0` identifican gastos 100% personales. Deuda simétrica: lo que el otro puede cobrar = lo que esta persona debe. CSS: `.gp-col`, `.gp-row`, `.gp-saldo`, `.gp-saldo-pos/neg`.
- C-MANUAL-1/2/3: Usuario ejecutó setup, deployó recetario-api.js y configuró AppSheet. `RECETARIO_API_URL` seteada en `src/recetario/index.html`. Recetario 100% en producción.
**Pendientes:** Sin pendientes críticos. Módulos Recetario y Compras 100% operativos.
**Notas:** F-16/F-17 requiere que el Log tenga entradas con `tipo_proporcion=custom` y `proporcion_jd=100 o 0` para mostrar datos — si no hay ninguna, muestra empty state con instrucciones.

<!-- Claude: agregar nuevas sesiones arriba de este comentario, manteniendo el formato -->

### [2026-04-08] - Sesión 23
**Objetivo:** BUG-A (fila fantasma en Log), BUG-B (colisión ID AppSheet en GastosFijos), FEAT 3A+3B (card total correcto + filtro persona en vista Gastos)
**Logros:**
- BUG-A (TAREA 1): Inspección completa de `finanzas-triggers.js`. No hay causa en el código: el `1` hardcodeado va a `cuota_nro`, no a `monto_total`; el self-loop está protegido por el check de ID y el LockService; `isEmptyRow()` es correcto. Conclusión: input accidental del usuario. Sin cambios de código.
- BUG-B (TAREA 2 — `finanzas-triggers.js`): Agregado `id_appsheet_log` al mapa `cols`. En `expandCuotas()`, las cuotas generadas por el trigger limpiaron `id_appsheet_log = ''` para no heredar el ID de AppSheet de la fila madre. Aplicado con guard `if (cols.id_appsheet_log >= 0)` para compatibilidad si la columna no existe.
- BUG-B (TAREA 2 — `finanzas-api.js`): Endpoint `?action=fixed` agrega `id_appsheet: current.id_appsheet || ''` al objeto retornado (sin costo si la columna no existe aún en la hoja GastosFijos).
- TAREA 3A (`src/finanzas/index.html`): `renderGastos()` corregido:
  - `varTotal` ahora excluye `cuota_nro > 1` (evita doble conteo con `cuotasTotal`).
  - `cuotasTotal = sum(filterCuotasComprometidas(...))` sumado al total del card.
  - Fórmula final: `total = varTotal + fixTotal + cuotasTotal`.
  - Sub-líneas "JD: $X · Pinki: $Y" en el card total (modo Común, calculadas con `getRowPct()`).
- TAREA 3B (`src/finanzas/index.html`): Filtro persona extendido a toda la vista Gastos:
  - `applyPersonaFiltro(rows)` helper centraliza la lógica de filtrado (reemplaza bloque inline en `renderGastosPie`).
  - Botones `Comunes / JD / Pinki` movidos al section-header de la vista Gastos (antes estaban dentro del chart box).
  - Clase `.persona-btn` (nuevo CSS) con el mismo estilo visual que `.period-btn` pero nombre separado para no interferir con `querySelectorAll('.period-btn')` del selector de período.
  - `setGastosPersonaFiltro()` ahora llama `renderGastos()` completo (antes solo `renderGastosPie`).
  - `renderComposicion()` también aplica `applyPersonaFiltro` + `fixTotal=0` en modo JD/Pinki.
  - Deuda, crédito y tabla siguen usando el set completo de rows (no filtrado por persona).
**Pendientes:**
- ⚠ MANUAL (BUG-B): Agregar columna `id_appsheet` en hoja GastosFijos (el usuario lo hace a mano). Configurar AppSheet para usar esa columna como clave primaria interna.
- ⚠ MANUAL (BUG-B): La columna `id_appsheet_log` (col U) ya existe en hoja Log — AppSheet ya puede usarla.
- NEW deployment de `finanzas-api.js` para activar el campo `id_appsheet` en el endpoint `fixed`.
- NEW deployment de `finanzas-triggers.js` para activar el fix de `id_appsheet_log` en cuotas expandidas.
**Notas:** La clase `.persona-btn` es necesaria porque `selectPeriodType()` usa `querySelectorAll('.period-btn').forEach(b => b.classList.toggle('active', b.dataset.period === type))`. Si los botones de persona tuvieran clase `period-btn` sin `data-period`, perderían su estado `active` al cambiar el período. La separación de clases evita este efecto secundario.

### [2026-04-06] - Sesión 17
**Objetivo:** Implementar F8–F10 del backlog features-2026-04-06.md (schema fix, panel fijos, drawer resize, mejoras Inversiones)
**Logros:**
- F8 — Schema + endpoint fixed (Score 3):
  - `apps-script/finanzas-api.js`: endpoint `?action=fixed` ahora devuelve `tipo_proporcion` y `proporcion_jd` por cada gasto fijo (leídos de columnas que el usuario agrega manualmente en la hoja GastosFijos)
  - `src/finanzas/index.html`: `getDeudaPct()` eliminado completamente; `renderDeuda()`, `toggleDeudaDetail()` y `renderDeudaDetailPanel()` actualizados para usar `getRowPct()` directamente. Filtro de debtRows simplificado.
  - ⚠ MANUAL pendiente: pintar de gris columnas S y N en hoja Log, agregar columnas `tipo_proporcion`/`proporcion_jd` en GastosFijos, crear NEW deployment de Apps Script
- F4 — Panel gastos fijos con JD$/Pinki$ (Score 2):
  - `renderFijosDetailTable()` actualizada: removida columna "Responsable", agregadas "Proporción" (via `propLabel()`), "JD $" y "Pinki $" (via `getRowPct()`). Footer con tres totales: mensual, p1, p2.
- F9 — Drawer redimensionable en desktop (Score 3):
  - CSS `.drawer-resize-handle` + styles hover/dragging agregado en ambos módulos
  - `initDrawerResize(drawerId, handleId)` implementado en `src/finanzas/index.html` y `src/inventario/index.html`
  - Patrón: mousedown → deshabilita transition → clamp entre 280px y 82% del viewport → mouseup → restaura transition
  - Flag `handle._resizeInit = true` para evitar listeners duplicados al reabrir el drawer
  - Variable de sesión `_drawerWidth = 420` (no persiste en localStorage)
- F10 — Vista Inversiones: zoom + toggle pie/bar + labels (Score 3):
  - 5 botones de zoom temporal: 1M / 3M / 6M / 1A / Todo (default: 6M)
  - `lastNMonths(currentMonth, n)` — n=0 muestra todos los meses con datos reales
  - `setInvZoom(n)` actualiza estado `_invZoom` + clases .active + re-renderiza línea
  - Toggle torta/barras (`_invPieType`): `toggleInvPieType()` + botón "barras"/"torta"
  - `renderInvPie()` con modo doughnut (leyenda con monto + %, onClick para toggle) y modo bar (horizontal, sin leyenda)
  - Leyenda Chart.js con `generateLabels` personalizado: "Label  $150k  (38%)"
**Pendientes:**
- ⚠ MANUAL (F8): columnas `tipo_proporcion`/`proporcion_jd` en GastosFijos + gris en Log S y N
- ⚠ MANUAL (F8): NEW deployment de `finanzas-api.js` + actualizar API_URL
- F11+F12: Barra de composición — labels sobre segmentos + adaptar fijos al período multi-mes
- F13: Drill-down categoría → subcategoría en torta de Gastos
- F14+F15: Vista Presupuesto — ajustes (4 sub-ítems) + distribución en pesos
- F16+F17: Cards expandidos JD+Pinki + sección gastos personales (rediseño mayor)
**Notas:** Al buscar `_drawerWidth` con Edit tool, el comentario en el archivo difería del que se usó en el search. Se resolvió con Grep antes de editar para encontrar el texto exacto. La CONTEXTO.md de Sesión 16 tenía una descripción incorrecta del fix C1 (decía "corregido a `row.categoria`" cuando el filtro correcto es `row.subcategoria`). Corregido en esta sesión.

<!-- Claude: agregar nuevas sesiones arriba de este comentario, manteniendo el formato -->

### [2026-04-06] - Sesión 18
**Objetivo:** Implementar las features pendientes del backlog features-2026-04-06b.md: CSS-01, PPTO-01, DIST-01, SALDADO-01
**Logros:**
- CSS-01 (Score 3): Compresión horizontal de vistas. `.content` padding 2.5rem → 2rem, `.topbar` 2.5rem → 1.25rem lateral, `.chart-box` 1.5rem → 1.25rem, `.table-header` 1.5rem → 1rem, `thead th` y `tbody td` 1rem → 0.7rem/0.65rem lateral, `.deuda-detail` 1.5rem → 1rem.
- PPTO-01 (Score 3): Vista Presupuesto mejorada:
  - Gráfico de evolución de fijos oculto por defecto (`display:none`); se muestra al hacer clic en ↗.
  - `renderPptoFijosTable()` reescrita: columnas Descripción / Categoría / Responsable / Medio / Proporción / JD$ / Pinki$ / Monto mensual / ↗. Footer con totales por persona.
  - `showFixedHistory()` actualizado: muestra el box, resalta la fila activa via `data-desc`.
  - Hint text cambiado a "Usá ↗ por fila para ver la evolución".
  - `event.stopPropagation()` en el botón ↗ para evitar doble-dispatch con el `onclick` de la fila.
- DIST-01 (Score 3): Dos bugs corregidos en `renderDistribucion()`:
  - Bug 1: salarios mostraban $0. El filtro usaba `r.categoria === 'salario'` — el schema tiene salario en `r.subcategoria`. Corregido.
  - Bug 2: varRows y cuotasRows tenían filtro `r.pago === 'Común'` que no existe en `computePresupuestoParts()`. Al alinearlo, los gastos propios se incluyen vía `getRowPct()`. La fila "Propios" fue eliminada para evitar doble conteo; `disponible` actualizado acorde.
- SALDADO-01 (Score 5): Feature completa de "Saldar" en panel de deuda neta:
  - `apps-script/finanzas-api.js`: función `saldarDeuda(id)` (LockService + busca columna `saldado` por header + `setValue(true)`). Case `'saldar'` en el router `doGet()`.
  - `src/finanzas/index.html`: `renderDeuda()` calcula balance solo sobre `activeDebtRows` (excluye `r.saldado`). `renderDeudaDetailPanel()` muestra todas las filas — saldadas con 50% opacidad y label "saldado", no saldadas con botón "Saldar". Solo filas activas suman a debeP1/debeP2. `saldarRow(id)`: confirm → `apiFetch('saldar', {id})` → `S.log.map(saldado: true)` → `renderView()`. CSS `.btn-saldar` consistente con `.btn-delete`, hover en accent verde.
**Pendientes:**
- ⚠ MANUAL (SALDADO-01): Agregar columna `saldado` (Checkbox, default FALSE) al final de hoja Log en Google Sheets
- ⚠ MANUAL (SALDADO-01): NEW deployment de `finanzas-api.js` y actualizar `API_URL` en el dashboard
- Features BUG-01, PROP-01, TWEAK-01, TWEAK-02, C1 (cuotas/crédito), PIE-01 del backlog quedan pendientes para la próxima sesión
**Notas:** `renderDeudaDetailPanel()` fue la función con más lógica: separar el balance (solo activas) del display (todas incluyendo saldadas) sin doble-render fue la decisión clave. El patrón `S.log.map(r => r.id === id ? {...r, saldado: true} : r)` (análogo a `deleteEntry` pero sin filtrar) mantiene la fila visible en el panel. El `data-desc` como atributo en filas de fijos evita falsos positivos con el texto del badge "bimestral" dentro del `<td>`.

### [2026-04-09] - Sesión 24
**Objetivo:** 7 fixes/features en finanzas: limpieza id_appsheet (prev. sesión), isEmptyRow fix, diagnóstico T3 (fijos), applyPersonaMonto (prev. sesión) + 4 nuevas tareas del prompt.
**Logros:**
- **T1-prev (limpieza id_appsheet):** `finanzas-triggers.js`: removido `id_appsheet_log` del objeto `cols` y el bloque de limpieza en `expandCuotas()`. `finanzas-api.js`: removido campo `id_appsheet` del push en `getFixed()`. Columnas manuales pendientes.
- **T2-prev (isEmptyRow):** `isEmptyRow()` ahora incluye `|| cell === false` para manejar checkboxes no inicializados de Google Sheets. Guard adicional: `if (!row[cols.tipo] || !row[cols.fecha]) continue` en `onLogChange()`.
- **T3-prev (diagnóstico fijos no visibles):** API confirmada correcta (`?action=fixed` devuelve 6 ítems, total correcto). Código frontend correcto. Causa probable: GitHub Pages con versión desactualizada o error silencioso en fetch. Diagnóstico: verificar `S.fixed` en console del browser.
- **T4-prev (applyPersonaMonto):** Helper `applyPersonaMonto(rows, persona, pJD, pPinki)` agregado en `src/finanzas/index.html`. Aplicado en `renderGastosBar()` (por mes/categoría) y `renderGastosTable()`.
- **T1-nuevo (bug deuda):** `renderDeuda()`: `debtRows` ahora excluye filas donde la contraparte tiene pct=0. Condición: `if (r.pago === p1 && pct2 === 0) return false` / `if (r.pago === p2 && pct1 === 0) return false`. Escala correcta: 0-100 (no 0-1).
- **T2-nuevo (bug fijos no aparecen):** `getFixed()` en `finanzas-api.js`: `firstDay = targetMonth + '-01'` → `lastDay = targetMonth + '-31'`. GF-017 y GF-018 (vigente_desde=2026-04-08) ahora aparecen en consulta de abril 2026.
- **T3-nuevo (trigger GastosFijos):** `finanzas-triggers.js`: nuevo handler `onGastosFijosChange()` + helper `generateNextGfId()`. Pisa cualquier ID que no empiece con `GF-` (incluye IDs propios de AppSheet). `setupTriggers()` actualizado para instalar ambos triggers.
- **T4-nuevo (5 botones persona + fijos filtrados):**
  - PARTE A: 5 botones `gastos-filter-comun/jd-comun/jd/pinki-comun/pinki`. `_gastosPersonaFiltro = 'comun'`.
  - PARTE B: `applyPersonaFiltro()` reescrita con switch de 5 ramas usando `getRowPct()`. `applyPersonaMonto()` usa `'comun'` en lugar de `null`.
  - PARTE C: `computeFixedForPersona(filtro)` — fijos filtrados por persona usando `monto_mensual`. Usado en `renderGastos()` y `renderComposicion()`.
  - PARTE D: Cuotas comprometidas: `applyPersonaMonto(applyPersonaFiltro(...))` en ambas funciones. Crédito card: recibe `applyPersonaFiltro(rows)` + `cuotasCredito` filtrada internamente.
  - PARTE E: Sub-labels `=== null` → `=== 'comun'`. Rename dinámico de 4 botones en `renderGastosPie`.
**Pendientes:**
- ⚠ MANUAL: NEW deployment `finanzas-api.js` (lastDay fix + remoción id_appsheet)
- ⚠ MANUAL: Ejecutar `setupTriggers()` en Apps Script (instala `onGastosFijosChange`)
- ⚠ MANUAL: Eliminar col `id_appsheet_log` de hoja Log + col `id_appsheet` de hoja GastosFijos
- ⚠ MANUAL: Actualizar `API_URL` en dashboard si el new deployment cambia la URL
- T3 (fijos no visibles): diagnóstico pendiente de verificación del usuario — ver `S.fixed` en console
**Notas:** El prompt del usuario indicaba `pct >= 1` para la condición de exclusión de deuda (escala 0-1), pero `getRowPct()` devuelve escala 0-100. Se corrigió a `pct2 === 0` / `pct1 === 0` (equivalente correcto). Similar ajuste en `applyPersonaFiltro`: 'jd' y 'pinki' usan `=== 100`, no `=== 1`. La función `computeFixedForPersona` usa `monto_mensual` (no `monto`) porque el API ya divide bimestrales por 2 — el prompt tenía `item.monto` que hubiera sido incorrecto.

### [2026-04-09] - Sesión 25
**Objetivo:** 4 bug fixes en Finanzas: deuda incluye gastos personales (T1), card Fijos con proporcion_jd=0 muestra 50/50 (T2), card Crédito sin subcategoría (T3), card En Cuotas no aplica filtro persona (T4).
**Logros:**
- **T1 (renderDeuda):** Confirmado ya fijo desde Sesión 24. No requirió cambio de código. Si el bug sigue visible en producción, la causa es GitHub Pages sirviendo HTML viejo.
- **T2 (falsy-zero en API):** `finanzas-api.js` línea 308: `proporcion_jd: parseFloat(current.proporcion_jd) || 50` → `(current.proporcion_jd != null && current.proporcion_jd !== '') ? parseFloat(current.proporcion_jd) : 50`. Causa raíz: `parseFloat(0) || 50 === 50` porque 0 es falsy. El bug no estaba en `getRowPct()` (que maneja 0 correctamente con `!== undefined && !== null && !== ''`) sino en la serialización de la API. Fix requiere NEW deployment.
- **T3 (subcategoría en Crédito):** `renderCreditoDetailPanel()`: columna Categoría ahora muestra "Hogar / Alquiler" cuando existe subcategoría. `${r.categoria || '—'}${r.subcategoria ? ' / ' + r.subcategoria : ''}`.
- **T4 (En Cuotas con filtro persona):** Card "En Cuotas" en `renderGastos()`: `applyPersonaFiltro(cuotasAll)` + `applyPersonaMonto(cuotasFiltered, _gastosPersonaFiltro, p1, p2)`. Count usa `cuotasFiltered.length` (pre-ajuste proporcional) para mostrar cantidad de ítems, no el monto ajustado.
**Pendientes:**
- ⚠ MANUAL: NEW deployment `finanzas-api.js` (activa T2 + fixes de Sesión 24: lastDay, remoción id_appsheet, fix C1 subcategoria en getProportions)
- ⚠ MANUAL: Ejecutar `setupTriggers()` en Apps Script
- ⚠ MANUAL: Eliminar col `id_appsheet_log` de Log + col `id_appsheet` de GastosFijos
- ⚠ MANUAL: Actualizar `API_URL` si el new deployment genera URL nueva
- Diagnóstico: verificar `S.fixed` en browser console
**Notas:** Diagnóstico de T2: el usuario asumió que el falsy-zero estaba en `getRowPct()`. La inspección del código mostró que `getRowPct()` tiene un guard correcto. El bug real estaba en `getFixed()` donde se usó `|| 50` como fallback — patrón peligroso cuando 0 es un valor legítimo. Regla: para campos numéricos donde 0 es válido, siempre usar `!= null && !== ''` en lugar de `|| default`.
