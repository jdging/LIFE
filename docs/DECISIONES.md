# Registro de Decisiones

> Cada decisión técnica importante se documenta acá.

---

### DEC-001: Template de proyecto con documentación viva
- **Fecha:** 2026-03-27
- **Contexto:** Necesidad de mantener contexto del proyecto sincronizado entre sesiones
- **Decisión:** Estructura de carpetas con docs/ auto-actualizado, almacenado en Google Drive
- **Alternativas descartadas:** Depender solo del historial de chat
- **Razón:** El chat se pierde, los archivos persisten. Drive sincroniza entre dispositivos.
- **Consecuencias:** Requiere disciplina de actualización (automatizada via skills)

---

### DEC-002: Apps Script como API backend de Finanzas
- **Fecha:** 2026-04-01
- **Contexto:** Necesidad de exponer datos de Google Sheets como JSON para el dashboard
- **Decisión:** Google Apps Script deployado como web app pública
- **Alternativas descartadas:** Firebase Functions, Supabase Edge Functions, backend Node.js
- **Razón:** 100% gratuito, dentro del ecosistema Google, sin servidores que mantener, deploy en segundos
- **Consecuencias:** Latencia de cold start (~1-2s en primer request). Sin auth en la URL (datos de uso personal, aceptable).

---

### DEC-003: Proporcionalidad dinámica desde el Log
- **Fecha:** 2026-04-01
- **Contexto:** Definir cómo calcular cuánto debe pagar cada persona de los gastos comunes
- **Decisión:** Calcular la proporción JD/Pinki dinámicamente desde los ingresos de tipo Salario del mes consultado
- **Alternativas descartadas:** Proporción fija en Config, proporción manual por gasto
- **Razón:** Los salarios cambian. Una proporción fija sería injusta ante aumentos o cambios de situación.
- **Consecuencias:** Si un mes no tiene salarios cargados, hace fallback al último mes con datos. Si no hay datos históricos, usa 50/50.

---

### DEC-004: Soft delete en lugar de borrado real
- **Fecha:** 2026-04-01
- **Contexto:** Necesidad de poder "borrar" entradas desde el dashboard sin perder el historial
- **Decisión:** Campo booleano "borrado" en Log. El API filtra borrado=TRUE. La fila sigue en la Sheet.
- **Alternativas descartadas:** Borrado real de filas, hoja de "papelera" separada
- **Razón:** Permite recuperar errores accidentales directamente desde la Sheet. Las filas borradas se ven en gris en la Sheet gracias al formato condicional.
- **Consecuencias:** La Sheet crece más lento pero nunca pierde datos.

---

### DEC-005: Chart.js 4.4.3 desde CDN para visualizaciones
- **Fecha:** 2026-04-02
- **Contexto:** Necesidad de gráficos interactivos en el dashboard sin build tools
- **Decisión:** Chart.js 4.4.3 desde CDN de jsdelivr
- **Alternativas descartadas:** D3.js (demasiado complejo para este caso), Recharts (requiere React), Google Charts
- **Razón:** Amplia documentación, sin dependencias, compatible con vanilla JS, dark theme configurable.
- **Consecuencias:** Depende de CDN externo (no funciona offline sin cache).

---
### DEC-006: AppSheet panel como drawer lateral + FAB flotante
- **Fecha:** 2026-04-02
- **Contexto:** Necesidad de embeber el formulario de carga AppSheet dentro del dashboard sin interrumpir el flujo de lectura
- **Decisión:** Botón flotante (+) en esquina inferior derecha. Al clickear, abre un drawer lateral (translateX animation) con el iframe de AppSheet.
- **Alternativas descartadas:** Página separada para carga, modal overlay, tab adicional en la topbar
- **Razón:** El drawer no tapa el contenido principal mientras se carga un dato. El usuario puede ver el dashboard y el formulario al mismo tiempo en pantallas grandes. Cierre con Escape es ergonómico.
- **Consecuencias:** El iframe se crea en el DOM solo al primer abrir (lazy load). Si AppSheet hace redirect post-submit, el iframe queda en la confirmación hasta que el usuario cierre y reabra.

---

### DEC-007: Ocultar medio_pago para tipo=Ingreso en AppSheet
- **Fecha:** 2026-04-02
- **Contexto:** El campo medio_pago aparecia en el formulario AppSheet para todos los tipos, incluyendo Ingreso. Para un salario cobrado por transferencia bancaria, el campo era confuso (el usuario no "paga", recibe).
- **Decisión:** Agregar Show_If [tipo] <> "Ingreso" en el campo medio_pago en AppSheet. Para Gastos e Inversiones se mantiene visible.
- **Alternativas descartadas:** Mantener visible como campo opcional para Ingresos (canal por el que se recibio el dinero)
- **Razón:** El campo es intuitivo para gastos (medio de pago), confuso para ingresos. El canal de cobro no aporta al dashboard.
- **Consecuencias:** Los ingresos cargados en AppSheet no tendran medio_pago. El campo queda null para esas filas.

---

### DEC-008: GastosFijos como tabla separada con versionado por fecha
- **Fecha:** 2026-04-03
- **Contexto:** Los gastos fijos (alquiler, expensas, etc.) tienen montos que cambian con el tiempo. El campo `es_fijo` en el Log era una solución parcial que no guardaba historial ni montos proyectados.
- **Decisión:** Crear una hoja `GastosFijos` separada con lógica de versionado: cada cambio de precio genera una nueva fila con `vigente_desde` distinto. El endpoint `?action=fixed` siempre toma la versión más reciente aplicable al mes consultado.
- **Alternativas descartadas:** Editar filas directamente (pierde historial), usar `es_fijo` del Log con monto fijo en Config (no escala, no tiene historial).
- **Razón:** El alquiler sube, la tarifa de gas cambia. El historial permite ver la evolución de costos en el tiempo sin perder datos.
- **Consecuencias:** El usuario nunca edita filas en GastosFijos — siempre agrega nuevas. Requiere disciplina. La función `actualizarMontoFijo()` en el setup script facilita esto.

---

### DEC-009: History embedido en la respuesta del endpoint fixed
- **Fecha:** 2026-04-03
- **Contexto:** El dashboard necesita mostrar un gráfico de evolución histórica por cada gasto fijo al hacer clic en la tabla. Un fetch extra por gasto sería lento e innecesario.
- **Decisión:** El endpoint `?action=fixed` retorna además un objeto `history: { [descripcion]: [{vigente_desde, monto}, ...] }` con el historial completo de todas las versiones, ordenado cronológicamente.
- **Alternativas descartadas:** Endpoint separado `?action=fixed-history&descripcion=X`, fetch al hacer clic.
- **Razón:** Un solo fetch al cargar la vista Presupuesto da toda la data necesaria. El gráfico se renderiza instantáneamente al hacer clic.
- **Consecuencias:** La respuesta del endpoint es algo más grande, pero sigue siendo liviana (pocos gastos fijos).

---

### DEC-011: Gráfico de evolución de fijos — normalización % por defecto, toggle "$ / %"
- **Fecha:** 2026-04-03
- **Contexto:** Al mostrar todos los gastos fijos juntos en un gráfico de evolución, la diferencia de magnitudes (Alquiler $1.2M vs Internet $15K) aplasta los gastos chicos contra el eje X. Un eje Y absoluto compartido no permite apreciar la evolución de los menores.
- **Decisión:** Modo "Todos" = normalización porcentual (variación % desde el primer registro de cada gasto). Modo individual (clic en fila) = montos absolutos con escala adaptada al rango del gasto. Toggle "$ / %" en el gráfico permite cambiar entre ambos en cualquier momento.
- **Alternativas descartadas:** Eje Y dual (complejo en Chart.js, confuso visualmente), escala logarítmica (no intuitiva para el usuario).
- **Razón:** La normalización % es la forma más legible de comparar tendencias entre magnitudes muy distintas. El toggle da control al usuario sin imponer una sola vista.
- **Consecuencias:** El eje Y en modo % no muestra pesos — el usuario debe saber que está viendo evolución relativa, no absoluta.

---

### DEC-012: F-01 — Separar "variables ejecutados" de "cuotas comprometidas" como capas distintas
- **Fecha:** 2026-04-04
- **Contexto:** Al agregar gastos reales a la Vista Presupuesto, surgió la pregunta de si mostrar variables + cuotas juntos o separados.
- **Decisión:** Dos capas separadas con colores distintos. Variables ejecutados = gastos del mes corriente (cuota_nro=1). Cuotas comprometidas = cuotas de compras previas que vencen este mes (cuota_nro > 1).
- **Alternativas descartadas:** Mostrarlos juntos como "gastos variables totales".
- **Razón:** Son naturalezas distintas. Los variables son decisiones del mes. Las cuotas son compromisos ya tomados — no se pueden evitar. Separarlos da información de gestión real al usuario.
- **Consecuencias:** La barra tiene 5 segmentos. El disponible = ingresos - fijos - variables - cuotas - simulados.

---

### DEC-018: Inventario en Sheet separada de Finanzas
- **Fecha:** 2026-04-05
- **Contexto:** Al generar el modulo Inventario, habia que decidir si usar el mismo Spreadsheet de Finanzas (nueva hoja) o un Spreadsheet propio.
- **Decision:** Spreadsheet separado para Inventario (ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw), con su propio Apps Script API deployado como Web App independiente.
- **Alternativas descartadas:** Nueva hoja en el Spreadsheet de Finanzas + endpoint en finanzas-api.js. Seria mas simple pero acopla dos dominios distintos.
- **Razon:** El inventario es un dominio independiente (bienes fisicos, cotizacion USD, participacion por bien). Acoplarlo a Finanzas haria que cualquier cambio en uno afecte al otro, y el API de Finanzas ya es complejo.
- **Consecuencias:** Requiere un deploy adicional de Apps Script. La ventaja es que cada modulo es autonomo y puede evolucionar independientemente.

---

### DEC-019: Cotizacion USD como input editable en el dashboard (no fetcheada)
- **Fecha:** 2026-04-05
- **Contexto:** Para calcular el valor actual de los bienes en ARS, se necesita la cotizacion del dia. Opciones: fetchear una API de cotizacion, o dejar que el usuario la ingrese manualmente.
- **Decision:** Input editable en el dashboard (default 1200). El usuario lo actualiza cuando quiere ver el valor real de hoy. Recalculo inmediato via oninput.
- **Alternativas descartadas:** Fetch a una API de cotizacion publica (Bluelytics, dolarapi.com, etc.) -- agrega dependencia externa y complejidad de CORS/auth.
- **Razon:** Para uso personal con datos que no cambian todos los dias, el input manual es suficiente y mas robusto. Sin dependencias externas.
- **Consecuencias:** El usuario debe acordarse de actualizar la cotizacion para ver valores exactos. El valor por defecto (1200) puede quedar desactualizado.

---

### DEC-016: H4 - corresponde_a como campo separado de pago
- **Fecha:** 2026-04-05
- **Contexto:** La logica de deudas usaba solo el campo `pago` para determinar quien debe a quien. Esto no cubria el caso de que JD pague algo que le corresponde 100% a Pinki (o viceversa).
- **Decision:** Nuevo campo `corresponde_a` en el Log (columna S). Puede ser `Comun / JD / Pinki`. Nueva funcion `getDeudaPct()` que retorna 100%/0% cuando el campo apunta a una persona especifica, o delega en `getRowPct()` si es Comun.
- **Alternativas descartadas:** Manejar esto solo con `tipo_proporcion = custom` y `proporcion_jd = 0` o `= 100`. Esa combinacion ya existe pero mezcla la semantica de "quien pago" con "de quien es".
- **Razon:** Separar pago de pertenencia es semanticamente correcto. Permite que JD pague la farmacia de Pinki y que eso genere 100% de deuda de Pinki hacia JD, independientemente de los ingresos del mes.
- **Consecuencias:** El filtro de debtRows excluye explicitamente el caso "la persona pago su propio gasto" (no genera deuda). AppSheet necesita el campo en el formulario con valor default Comun.

---

### DEC-017: H1 - S.period como objeto con from/to en lugar de S.month
- **Fecha:** 2026-04-05
- **Contexto:** El dashboard usaba un selector de mes unico. Para soportar rangos (3M, 6M, Ano, Todo, Rango libre) se necesitaba un modelo de estado mas rico.
- **Decision:** `S.period = { type, from, to, refMonth }` donde `from` y `to` son strings YYYY-MM-DD. `S.month` se mantiene como alias de `refMonth` para compatibilidad con funciones de charts y fetch que lo usaban.
- **Alternativas descartadas:** Reemplazar S.month completamente (requeria actualizar charts y fetch calls). Usar un array de meses en lugar de from/to (mas complejo para filtrar).
- **Razon:** La comparacion lexicografica de fechas YYYY-MM-DD funciona directamente como operadores < y >. Usar YYYY-MM-31 como upper bound del mes es valido porque ningun mes tiene dia 31 > 28/29/30 reales en comparacion de strings.
- **Consecuencias:** Todos los filterLog y filterCuotasComprometidas usan from/to. Los charts siguen usando S.month (refMonth) para definir el eje X y hacer fetch del mes de referencia.

---

### DEC-013: F-04 — tipo_proporcion como campo en el Log (no en endpoint)
- **Fecha:** 2026-04-04
- **Contexto:** Para permitir que cada gasto tenga su propia regla de división (dinámica / 50/50 / custom), había que decidir dónde vivía esa lógica.
- **Decisión:** Dos columnas nuevas en la hoja Log (`tipo_proporcion`, `proporcion_jd`). El cálculo vive 100% en el frontend con `getRowPct(row, p1, p2)`. El endpoint no se modifica.
- **Alternativas descartadas:** Calcular en el endpoint `proportions` (requería cambios en Apps Script y nuevo deployment).
- **Razón:** Los datos ya llegan en el Log al dashboard. Calcular en el frontend evita un nuevo deployment y mantiene la lógica centralizada donde se usa.
- **Consecuencias:** `getRowPct()` es una función global reutilizable — ya se usa en `renderDeuda()`, `renderDistribucion()`, y disponible para cualquier cálculo futuro.

---

### DEC-015: H2 como módulo independiente (no extensión de Finanzas)
- **Fecha:** 2026-04-04
- **Contexto:** H2 (inventario de bienes invertidos) surgió como una idea dentro del módulo Finanzas. Al especificarlo más, quedó claro que es un dominio distinto: registra bienes físicos y su valor en dólares, no transacciones financieras.
- **Decisión:** Módulo separado en `src/inventario/index.html`, registrado en el hub LIFE con su propia tarjeta y entrada en el sidebar, igual que Jardín y Finanzas.
- **Alternativas descartadas:** Subsección dentro del dashboard de Finanzas, nueva vista dentro del módulo existente.
- **Razón:** El inventario tiene su propia lógica (cotización USD, porcentaje de participación por bien, precio de venta estimado). Mezclarlo con Finanzas haría crecer el dashboard innecesariamente.
- **Consecuencias:** Requiere crear index.html nuevo, actualizar hub (src/index.html), posiblemente su propio Apps Script o usar la misma Sheet con una nueva hoja.

---

### DEC-014: F-05 — Gastos propios como fila condicional en distribución
- **Fecha:** 2026-04-04
- **Contexto:** JD o Pinki pueden pagar gastos propios (pagó=JD o pagó=Pinki, no "Común"). No siempre existen en un mes dado.
- **Decisión:** La fila "Gastos propios" aparece en la tabla de distribución solo si `propios1 > 0 || propios2 > 0`. Si no hay gastos propios en el mes, la fila desaparece para no agregar ruido visual.
- **Alternativas descartadas:** Mostrar siempre la fila (con $0 o "—" si no hay datos).
- **Razón:** La tabla es más limpia sin filas vacías. La mayoría de los meses los gastos se cargan como "Común".
- **Consecuencias:** Si el usuario espera ver la fila y no está, puede confundirse. El comportamiento es consistente con cómo maneja el panel de deuda.

---

### DEC-010: Vista Gastos = panorama real / Vista Presupuesto = proyección
- **Fecha:** 2026-04-03
- **Contexto:** Al implementar GastosFijos, surgió la pregunta de cómo mostrar gastos fijos vs variables en el dashboard.
- **Decisión:** La vista Gastos muestra el panorama completo del mes: total = gastos variables registrados en el Log + gastos fijos del endpoint fixed. La vista Presupuesto es la herramienta de proyección: ingresos vs fijos vs simulados (gastos variables hipotéticos no registrados aún).
- **Alternativas descartadas:** Mostrar solo variables en Gastos y moverlo todo a Presupuesto.
- **Razón:** El usuario necesita ambas perspectivas: "qué gasté este mes" (Gastos) y "qué me queda si gasto X más" (Presupuesto).
- **Consecuencias:** La card "Gastos fijos" en la vista Gastos muestra el total del endpoint fixed, no el conteo de filas con `es_fijo=TRUE` (ese campo deja de usarse).


---

### DEC-020: precio_usd_compra calculado en el frontend (no en el trigger de Apps Script)
- **Fecha:** 2026-04-05
- **Contexto:** El schema de la hoja Inventario tiene una columna `precio_usd_compra`. La idea original era que el trigger de Apps Script la calculara al insertar una fila (precio_ars / cotizacion_usd_compra). Pero el trigger de auto-ID no implementa ese calculo, y agregar logica al trigger requiere un nuevo deployment.
- **Decision:** Funcion `usdCompra(item)` en el frontend que prioriza el campo `precio_usd_compra` si viene cargado directamente, y sino calcula `precio_ars / cotizacion_usd_compra`. La columna queda vacia en la Sheet para la mayoria de los items.
- **Alternativas descartadas:** Actualizar el trigger de Apps Script para auto-calcular (requiere nuevo deployment); exigir al usuario que ingrese el USD directamente en AppSheet (friction innecesaria).
- **Razon:** El calculo es simple y los datos necesarios (precio_ars y cotizacion_usd_compra) ya estan en cada fila. Hacerlo en el frontend es inmediato y no requiere cambios en el backend.
- **Consecuencias:** Si en el futuro se quiere persistir el valor calculado en la Sheet (para queries directas en Sheets), se puede agregar al trigger. Por ahora el frontend es la fuente de verdad del calculo.

---

### DEC-021: Eliminar getDeudaPct() — corresponde_a reemplazado por tipo_proporcion=custom
- **Fecha:** 2026-04-06
- **Contexto:** `getDeudaPct()` usaba el campo `corresponde_a` (Comun/JD/Pinki) para determinar si un gasto le pertenecia al 100% a una persona. Con la llegada de `tipo_proporcion=custom` y `proporcion_jd=100/0`, el mismo resultado se logra con `getRowPct()`.
- **Decision:** Eliminar `getDeudaPct()` completamente. Todos sus callers (`renderDeuda()`, `toggleDeudaDetail()`, `renderDeudaDetailPanel()`) pasan a usar `getRowPct()` directamente. El campo `corresponde_a` queda deprecado (no eliminado de la hoja, pero no usado en codigo).
- **Alternativas descartadas:** Mantener `getDeudaPct()` como wrapper de `getRowPct()` (codigo muerto redundante). Migrar datos de corresponde_a a tipo_proporcion (innecesario, el valor por defecto en getRowPct cubre el caso general).
- **Razon:** `getRowPct()` ya maneja los tres casos: dinamica (proporcion del mes), 50/50 (literal), custom (proporcion_jd definida). `getDeudaPct()` era un wrapper que solo agregaba la logica de corresponde_a, que es equivalente a custom con 0/100. La simplificacion reduce surface area de la logica de deudas.
- **Consecuencias:** El filtro de debtRows ya no pre-filtra por corresponde_a. Cualquier fila donde alguien pago es candidata; `getRowPct()` determina la division real. El campo `corresponde_a` en la Sheet queda como dato historico.

---

### DEC-B1: Sheet separada para Compras + Recetario
- **Fecha:** 2026-04-06
- **Contexto:** Módulo Compras necesita persistencia de datos. Opciones: hoja dentro de la Sheet de Finanzas, o Sheet nueva compartida con Recetario.
- **Decisión:** Sheet separada (nuevo Spreadsheet), misma que Recetario usará con hojas distintas (ListaCompras, Recetas, Ingredientes).
- **Alternativas descartadas:** Hoja ListaCompras dentro de la Sheet de Finanzas.
- **Razón:** Mismo argumento que Inventario (DEC-015) — dominio distinto, evita contaminar la Sheet de Finanzas. Compras y Recetario comparten Sheet porque son complementarios (flujo Recetario → Compras).
- **Consecuencias:** `COMPRAS_SPREADSHEET_ID` en compras-setup.js y compras-api.js debe actualizarse al crear la Sheet.

---

### DEC-B2: Deduplicación de ítems en endpoint `add` de compras-api.js
- **Fecha:** 2026-04-06
- **Contexto:** Al agregar ingredientes desde el Recetario a la lista de compras, un mismo ingrediente puede existir ya en la lista (pendiente, sin borrar).
- **Decisión:** El endpoint `action=add` busca un ítem con mismo nombre (case-insensitive) + misma unidad + estado=pendiente + borrado=FALSE. Si existe, suma la cantidad; si no, inserta fila nueva.
- **Alternativas descartadas:** Deduplicación en el cliente (requiere GET previo + lógica extra en Recetario).
- **Razón:** Centralizar en el API simplifica todos los clientes (Recetario no necesita verificar). Comportamiento correcto para el flujo "agregar 2 recetas que usan la misma harina".
- **Consecuencias:** El campo `origen` de la fila deduplicada no se actualiza (conserva el origen de la primera inserción). Comportamiento aceptable.

---

### DEC-B3: Una sola app AppSheet para Compras y Recetario
- **Fecha:** 2026-04-06
- **Contexto:** Compras y Recetario usan la misma Sheet (DEC-B1). AppSheet puede conectarse a toda la Sheet o a hojas específicas.
- **Decisión:** Una sola app AppSheet con vistas para ListaCompras, Recetas e Ingredientes.
- **Alternativas descartadas:** Dos apps AppSheet separadas (una por módulo).
- **Razón:** Más simple de mantener. Un solo `APPSHEET_URL` compartido (o vistas diferentes dentro de la misma app). Reduce la cantidad de deployments y configuraciones de seguridad.
- **Consecuencias:** El `APPSHEET_URL` en src/compras/index.html y src/recetario/index.html apunta a la misma app; la vista inicial puede diferir según la pantalla de entrada.

---

### DEC-022: Clase CSS separada (.persona-btn) para botones de filtro persona
- **Fecha:** 2026-04-08
- **Contexto:** Los botones de filtro persona en la vista Gastos (Comunes / JD / Pinki) necesitan el mismo look visual que `.period-btn`, pero `selectPeriodType()` tiene un `querySelectorAll('.period-btn').forEach(...)` que resetea `active` en todos los `.period-btn` al cambiar el período. Si los botones de persona usaran esa clase, perderían su estado activo al cambiar el mes.
- **Decisión:** Nueva clase `.persona-btn` con las mismas reglas CSS que `.period-btn` (fondo, hover, `.active`), pero nombre diferente para no ser alcanzada por el `querySelectorAll` del selector de período.
- **Alternativas descartadas:** Agregar `data-persona` y filtrar dentro del `querySelectorAll` (requería modificar `selectPeriodType()`); usar `.btn-chart-toggle` (estilo diferente, sin `background` en active).
- **Razón:** Mínimo cambio, cero side effects. La separación de clase es la forma más explícita de declarar que estos botones tienen un ciclo de vida de estado diferente.
- **Consecuencias:** Patrón replicable: cada grupo de botones con estado propio debe tener su propia clase CSS, especialmente si hay `querySelectorAll` que resetean estado globalmente.

---

### DEC-023: lastDay en lugar de firstDay para vigencia de gastos fijos
- **Fecha:** 2026-04-09
- **Contexto:** `getFixed()` usaba `firstDay = targetMonth + '-01'` para filtrar `vigente_desde <= firstDay`. Un gasto nuevo con `vigente_desde = '2026-04-08'` no aparecía en la consulta de abril 2026 porque `'2026-04-08' <= '2026-04-01'` es false.
- **Decisión:** Cambiar la cota a `lastDay = targetMonth + '-31'`. La comparación es lexicográfica: `'2026-04-08' <= '2026-04-31'` = true (correcto), `'2026-05-01' <= '2026-04-31'` = false (correcto).
- **Alternativas descartadas:** Calcular el último día real del mes (requiere lógica de días por mes/año bisiesto innecesariamente compleja para una comparación string).
- **Razón:** Gastos que arrancan a mitad del mes son vigentes ese mes. El criterio correcto es "el gasto empezó antes de que termine el mes", no "antes de que empiece el mes".
- **Consecuencias:** Un gasto con `vigente_desde = '2026-04-30'` también es vigente en abril (correcto). El boundary es el fin del mes, no el inicio.

---

### DEC-024: 5 estados de filtro persona en vista Gastos (T4)
- **Fecha:** 2026-04-09
- **Contexto:** Los 3 botones originales (Comunes/JD/Pinki) no cubrían el caso de ver todos los gastos donde JD participa (incluyendo los compartidos), ni el simétrico para Pinki.
- **Decisión:** 5 estados: `comun` (ambos pct>0), `jd_comun` (pct_jd>0), `jd` (pct_jd===100), `pinki_comun` (pct_pinki>0), `pinki` (pct_pinki===100). `applyPersonaFiltro` reescrita con `getRowPct()` en lugar de inspección directa de `tipo_proporcion`.
- **Alternativas descartadas:** Mantener 3 estados + filtro adicional por rango; combinar `jd` y `jd_comun` en un solo botón toggle.
- **Razón:** Los modos `+Común` son útiles para ver "todo lo que me impacta" incluyendo los gastos compartidos. La separación de `jd` puro permite ver solo los 100% personales. El uso de `getRowPct()` evita duplicar la lógica de proporción — `applyPersonaFiltro` ahora respeta `tipo_proporcion` dinámico.
- **Consecuencias:** `computeFixedForPersona()` necesario para fijos (no pasan por applyPersonaFiltro porque vienen de S.fixed, no del Log). Los sub-labels del card total solo se muestran en modo `comun`.

---

### DEC-025: getTarjetaLabel como helper global con t.label como fuente primaria
- **Fecha:** 2026-04-11
- **Contexto:** Dos funciones locales `labelTarjeta` con lógica idéntica. Al agregar una tercera necesidad del mismo lookup, se decidió centralizar.
- **Decisión:** Función global `getTarjetaLabel(id)` al principio del script. Usa `t.label` (columna H de la Sheet Tarjetas) si existe; fallback a `t.banco + ' – ' + t.nombre`; fallback final al raw ID.
- **Alternativas descartadas:** Mantener closures locales por función (difícil de mantener). Almacenar un objeto `{id: label}` en `S.tarjetasMap` (innecesariamente complejo para pocos items).
- **Razón:** `t.label` permite que el usuario defina el nombre a mostrar sin depender de concatenación automática. El fallback garantiza retrocompatibilidad con Tarjetas que no tengan la columna.
- **Consecuencias:** `S.tarjetas` debe estar cargado antes de llamar `getTarjetaLabel`. En la inicialización, las funciones de render que muestran tarjetas siempre corren después de `loadAll()`.

---

### DEC-026: sub-labels card Total replica 3 capas (var + fijos + cuotas) — no proxy de filteredRows
- **Fecha:** 2026-04-11
- **Contexto:** Los sub-labels "JD: $X · Pinki: $Y" debajo del card Total necesitan ser consistentes con el total mostrado. El total es var + fix + cuotas comprometidas; los sub-labels originalmente usaban solo filteredRows (var + cuotas sin separar).
- **Decisión:** Calcular sub-labels iterando exactamente las mismas 3 capas que el total: (1) filteredRows con cuota_nro === 1, (2) S.fixed.data directo, (3) filterCuotasComprometidas filtrado por persona. La suma JD + Pinki = total del card.
- **Alternativas descartadas:** Usar `applyPersonaMonto` para calcular todo en una pasada (no funciona porque fijos y cuotas son fuentes separadas). Calcular sub1/sub2 del total ya computado (requeriría dividirlo, imposible post-suma).
- **Razón:** Coherencia numérica: el usuario debe poder verificar que JD + Pinki = Total. Si se omite una capa, la suma no cierra.
- **Consecuencias:** Los sub-labels solo se muestran en modo `comun`. En otros modos de filtro persona, el total ya representa solo una persona, por lo que el desglose no aplica.

---

### DEC-027: Corrección de proporcion_jd vacío en el trigger, no en el frontend
- **Fecha:** 2026-04-12
- **Contexto:** AppSheet envía `proporcion_jd` vacío cuando el usuario elige `tipo_proporcion=custom` pero no modifica el campo. El frontend (`getRowPct`) tiene fallback a 50 para valores vacíos, lo que interpreta incorrectamente el gasto como 50/50.
- **Decisión:** Corregir el valor en el trigger `onLogChange` de Apps Script: detectar `tipo_proporcion=custom` + `proporcion_jd` vacío y escribir 0 en la Sheet. El frontend no cambia.
- **Alternativas descartadas:** Cambiar el fallback de `getRowPct` a algo distinto de 50 (rompería otros casos donde vacío sí significa "usar proporción dinámica"). Agregar validación en AppSheet (más complejo y no cubre entradas manuales en la Sheet).
- **Razón:** La Sheet es la fuente de verdad. Corregir en origen (trigger) es más robusto que corregir en cada punto de consumo. El valor 0 es el correcto cuando Pinki carga algo con `custom` y no especifica proporción de JD — indica que JD no participa.
- **Consecuencias:** Requiere que el trigger esté activo (guardado en el editor de Apps Script). Las filas ya existentes con vacío no se corrigen retroactivamente — son edge cases manuales.

### DEC-028: Estado local para ordenamiento y filtrado de tablas
- **Fecha:** 2026-04-16
- **Contexto:** La tabla de detalles de Gastos era estática y requería scroll largo. El usuario necesitaba ordenar y filtrar localmente sin alterar los gráficos (Cards/Torta).
- **Decisión:** Implementar variables de estado locales (`_tableSortCol`, `_tableFilterCat`, etc.) y re-renderizar solo la tabla al cambiar un filtro de encabezado, manteniendo el set de datos base intacto.
- **Razón:** Separa el "filtro global" (que afecta a todo el dashboard) del "filtro local" (que solo afecta la vista de tabla para buscar un dato puntual).
- **Consecuencias:** La función `renderGastosTable()` ahora maneja su propia lógica de ordenamiento y filtrado pre-renderizado.

---

### DEC-029: Ingreso con pago='Común' — no se modela, se divide por fuera
- **Fecha:** 2026-06-02
- **Contexto:** La vista Ingresos splittea el total por `pago === p1` / `pago === p2`. Un ingreso marcado `pago='Común'` no cae en ninguna pila → el total no coincide con la suma JD + Pinki.
- **Decisión:** No agregar lógica para repartir ingresos comunes. JD confirmó que en la práctica no se cargan ingresos como "Común" (la plata que entra siempre es de alguien). Si llegara a pasar, dividen el monto por fuera y cargan lo de cada uno por separado.
- **Alternativas descartadas:** Repartir 50/50 (arbitrario); repartir por la proporción del mes (suma supuestos sobre un caso que no ocurre).
- **Razón:** No introducir lógica para un caso que no se da. La data se mantiene limpia cargando ingresos siempre a una persona.
- **Consecuencias:** Si alguien carga un ingreso "Común", el desglose JD/Pinki no cerrará con el total. Es un error de carga conocido, no un bug del sistema.

### DEC-030: Gasto variable en mes con proporción 100/0 — se mantiene el comportamiento dinámico
- **Fecha:** 2026-06-02
- **Contexto:** A diferencia de los fijos (donde se desacopló la visibilidad de la proporción del mes, ver LEC-032), un gasto variable común cargado en un mes donde una persona no tuvo ingresos (proporción 100/0) se reparte 100% a quien ganó, y sale de la vista Común.
- **Decisión:** Dejarlo como está. No alinear `applyPersonaFiltro('comun')` con la lógica `getFixedKind`.
- **Alternativas descartadas:** Clasificar variables como shared/personal por `tipo_proporcion` (radio de impacto grande: lista principal de Gastos, elegibilidad de deuda, composición) para un caso de borde.
- **Razón:** Para un gasto variable, que lo banque 100% quien tuvo ingresos ese mes es el propósito mismo de la proporción dinámica — no es un error. El riesgo de tocar la lista principal supera el beneficio.
- **Consecuencias:** En meses 100/0, los gastos variables comunes de ESE mes se atribuyen 100% al que ganó. Comportamiento esperado y aceptado.
