# Proyecto: LIFE

## Identidad del Proyecto
- **Cliente:** JDG (proyecto propio)
- **Descripción:** Sistema de gestión personal multi-módulo, alojado en GitHub Pages
- **Estado:** En desarrollo
- **Fecha inicio:** 2026-03-27
- **Stack:** HTML/CSS/JS vanilla, Google Sheets, Google Apps Script, AppSheet, Chart.js, GitHub Pages

## Reglas de Oro (no negociables)

1. **NUNCA escribas código sin antes consultarme.** Mostrá un resumen de lo que entendiste, qué vas a hacer, y esperá mi OK.
2. **Actualizá el contexto del proyecto** después de cada cambio significativo (ver `docs/BITACORA.md` y `docs/CONTEXTO.md`).
3. **Herramientas gratuitas primero.** Siempre priorizá soluciones gratuitas y de código abierto.
4. **Ecosistema Google preferido:** Google Sheets, Apps Script, Firebase, AppSheet, Looker Studio, Drive.
5. **Sugerí herramientas del vault** (`docs/VAULT.md`) cuando detectes que una puede servir.
6. **Consultá con R.P.** (diseñadora gráfica) cuando algo involucre decisiones de diseño visual, branding, o UX que excedan lo técnico.
7. **Documentos HTML con marca:** Todo documento generado debe usar los assets de `marca/jdg/`.

## Módulos de LIFE

### Jardín (completo)
- **Ruta:** `src/jardin/index.html`
- **Qué es:** Catálogo de 26 plantas con georreferencia visual, compatibilidad de productos (chufa), filtros por zona/floración/D-SIST
- **Datos:** Fotos en `src/jardin/data/Plantas 260327/IMG_XXXX.webp`
- **Productos rastreados:** GlacoXAN (D-SIST Ambiente, D-SIST Planta, FungoXAN Planta, FungoXAN Ambiente), DMT (Enzimas, Booster, Limpia Raíces, Bioestimulante Floración), Top Crop (Top Barrier, Top Bloom), Great White (Premium Mycorrhizae)
- **Restricción crítica:** D-SIST prohibido en Anthurium, Asparagus, Ficus, Philodendron

### Finanzas en Pareja (en desarrollo)
- **Ruta:** `src/finanzas/index.html`
- **Qué es:** Sistema de gestión financiera para pareja con dashboard en tiempo real
- **Arquitectura:** AppSheet (carga) → Google Sheets (base) → Apps Script (API JSON) → Dashboard HTML
- **Componentes externos:**
  - Google Sheet: base de datos (hojas: Log, Tarjetas, Categorías, Config, GastosFijos)
  - Apps Script: API web que expone datos como JSON (6 endpoints)
  - AppSheet: formulario de carga embebido como iframe
- **Código local:**
  - `src/finanzas/index.html` — dashboard con 4 vistas (Gastos, Inversiones, Ingresos, Presupuesto)
  - `apps-script/finanzas-api.js` — API REST: log, config, proportions, fixed, delete
  - `apps-script/finanzas-setup-gastosfijos.js` — crea hoja GastosFijos (ejecutar 1 vez, PENDIENTE)
  - `tutoriales/SETUP-PRESUPUESTOS.html` — guía completa de setup del módulo Presupuestos
  - `appsheet/SETUP-FINANZAS.md` — guía de configuración de AppSheet

### Inventario (completo, en produccion)
- **Ruta:** `src/inventario/index.html`
- **Que es:** Registro de bienes en dolares. Valor actual segun cotizacion editable, participacion por persona (JD/Pinki) y precio de reventa estimado.
- **Arquitectura:** AppSheet (carga) -> Google Sheets separado (ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw) -> Apps Script API propia -> Dashboard HTML
- **AppSheet:** https://www.appsheet.com/start/a80bcfb2-256e-48a8-8ed1-ae1f458b8025
- **Codigo local:**
  - `src/inventario/index.html` — dashboard con cotizacion editable, 4 cards, tabla filtrable, drawer AppSheet
  - `apps-script/inventario-setup.js` — crea hoja Inventario con 12 columnas, validaciones y trigger auto-ID (ejecutar 1 vez)
  - `apps-script/inventario-api.js` — API: endpoints inventario (lista) y delete (soft delete)
- **Estado:** 100% en produccion -- setup ejecutado, API deployada, AppSheet conectado.

### Compras (completo, en produccion)
- **Ruta:** `src/compras/index.html`
- **Que es:** Lista del super compartida. Agregar items, marcar comprados, enviar por email.
- **Arquitectura:** AppSheet (carga) → Google Sheets separado (mismo que Recetario) → Apps Script API propia → Dashboard HTML
- **Codigo local:**
  - `src/compras/index.html` — dashboard: lista agrupada por categoria, checkboxes, limpiar, enviar, drawer AppSheet
  - `apps-script/compras-setup.js` — crea hoja ListaCompras con 10 columnas, validaciones, trigger auto-ID COMP-XXXXX (ejecutar 1 vez)
  - `apps-script/compras-api.js` — API: lista, add (con deduplicacion), comprado, delete, limpiar, enviar (MailApp)
- **Estado:** 100% en produccion -- setup ejecutado, API deployada, AppSheet conectado.
- **ORDEN_CATEGORIAS (API):** Verduras → Carnes → Lacteos → Panaderia → Almacen → Bebidas → Limpieza → Otro

### Recetario (completo, en produccion)
- **Ruta:** `src/recetario/index.html`
- **Que es:** Catalogo de recetas con ingredientes y porciones ajustables. Envia ingredientes directo a la lista del super.
- **Arquitectura:** AppSheet (carga) → Google Sheets (misma Sheet que Compras, hojas Recetas + Ingredientes) → Apps Script API read-only → Dashboard HTML
- **Codigo local:**
  - `src/recetario/index.html` — dashboard: grid de tarjetas, filtro por categoria, detalle expandible, selector de porciones, "Agregar al super"
  - `apps-script/recetario-setup.js` — crea hojas Recetas e Ingredientes con triggers auto-ID RECETA-XXXXX / ING-XXXXX (ejecutar 1 vez)
  - `apps-script/recetario-api.js` — API read-only: lista y detalle
- **Estado:** 100% en produccion -- setup ejecutado, API deployada, AppSheet conectado.
- **Constante clave:** `RECETARIO_API_URL` en index.html — ya configurada con URL del deployment.
- **Logica de porciones:** `cantidad_ajustada = cantidad_base * (porciones_sel / porciones_base)`. Cache en `data-cant-base` del `<tr>` para preservar referencia original.
- **Mapeo de unidades para Compras:** cdita/cda/taza → 'u' al llamar compras-api.js `?action=add` (esas unidades no existen en el dropdown de Compras).

## Comandos del Proyecto
- `npm run dev` → No aplica (HTML estático, abrir con Live Server o similar)
- Deploy: push a `main` en GitHub, Pages sirve desde `src/`
- Re-inicializar Sheet: ejecutar `setupFinanzasSheet()` en apps-script/finanzas-setup.js (⚠ borra todo)
- Crear hoja GastosFijos: ejecutar `setupGastosFijos()` en apps-script/finanzas-setup-gastosfijos.js (1 vez)
- Actualizar monto de un fijo: ejecutar `actualizarMontoFijo(desc, monto, desde)` en el mismo script
- Testear API localmente: `testGetLog()` / `testGetConfig()` / `testGetProportions()` / `testGetFixed()` desde el editor de Apps Script

## Comandos de Sesión (Claude Code)
- `/project:init` → Inicializar proyecto nuevo desde template
- `/project:status` → Ver resumen rápido del estado actual
- `/project:update-context` → Actualizar toda la documentación
- `/project:close-session` → Cerrar sesión y documentar todo
- `/project:suggest-tools` → Sugerir herramientas útiles del vault
- `/project:sync-to-template` → Proponer sincronización de aprendizajes al template maestro

## Arquitectura

### Sistema de diseño (global LIFE)
- **Theme:** Dark (fondos near-black)
- **Heading font:** Cormorant Garamond (serif)
- **Body font:** DM Mono (monospace)
- **Acento:** #8fb87a (verde)
- **Sidebar:** fija, 72px de ancho
- **Imágenes:** `loading="lazy"`, `onerror` hiding para fallback graceful
- **Responsive:** sí

### Módulo Finanzas — Detalle técnico

#### Google Sheets — Estructura de hojas

**Hoja `Config`:**
| Campo | Valor |
|-------|-------|
| Nombre persona 1 | JD |
| Nombre persona 2 | Pinki |
| Moneda | ARS |

**Hoja `Tarjetas`:**
| Columna | Tipo |
|---------|------|
| ID | Texto (TC1, TD1, etc.) |
| Nombre | Texto (Visa, Mastercard, etc.) |
| Tipo | Lista: Crédito / Débito |
| Banco | Texto |
| Titular | Lista: JD / Pinki |
| Día cierre | Número (solo crédito) |
| Día vencimiento | Número (solo crédito) |

**Hoja `Categorías`:**
| Tipo | Categoría | Subcategorías |
|------|-----------|---------------|
| Gasto | Hogar | Alquiler, Expensas, Electricidad, Gas, Internet, Ferretería, Decoración, Limpieza, Mantenimiento |
| Gasto | Comida | Supermercado, Verdulería, Carnicería, Delivery, Almacén |
| Gasto | Entretenimiento | Restaurantes, Bares, Cine/Teatro, Streaming, Eventos |
| Gasto | Transporte | Nafta, Peajes, SUBE, Mantenimiento vehículo |
| Gasto | Salud | Obra social, Farmacia, Consultas |
| Gasto | Personal | Ropa, Cuidado personal, Educación |
| Gasto | Mascotas | Veterinaria, Alimento |
| Inversión | Plazo fijo, FCI, Dólar/MEP, Crypto, Otro | — |
| Ingreso | Salario, Extra, Freelance, Otro | — |

**Hoja `Log` (tabla principal):**
| Campo | Tipo | Notas |
|-------|------|-------|
| id | Texto auto | LOG-00001 |
| fecha | Date | — |
| tipo | Lista | Gasto / Ingreso / Inversión |
| categoría | Lista filtrada | Según tipo |
| subcategoría | Lista filtrada | Según categoría |
| descripción | Texto | Libre |
| monto_total | Número | — |
| cuotas_total | Número | Default 1 |
| cuota_nro | Número | 1 si sin cuotas |
| cuota_ref | Texto | ID del gasto original (vincula cuotas) |
| medio_pago | Lista | Crédito / Débito / Efectivo / Transferencia |
| tarjeta | Lista filtrada | Solo si medio_pago = Crédito o Débito |
| pagó | Lista | Común / JD / Pinki |
| es_fijo | Boolean | Para gastos recurrentes |
| notas | Texto | — |
| borrado | Boolean | Default FALSE, soft delete |

#### Lógica de proporcionalidad (CRÍTICO)
- NO hay salarios fijos en Config
- La proporción se calcula dinámicamente por mes:
  1. Filtrar Log: tipo="Ingreso" AND categoría="Salario" AND mes=mes_consultado
  2. Sumar montos por persona (campo "pagó" identifica de quién es el ingreso)
  3. Calcular % de cada uno sobre el total
  4. Fallback: si un mes no tiene salarios, usar proporción del último mes que sí tenga
  5. Las deudas de cada mes usan la proporción DE ESE MES

#### Lógica de cuotas
- Cuando cuotas_total > 1, se generan N filas consecutivas en Log
- Cada fila: cuota_nro incremental, cuota_ref = id de la primera fila
- Fechas mensuales (mes+1, mes+2, etc.)
- Monto por fila = monto_total / cuotas_total

#### Lógica de deudas
- Cuando pagó = "JD" o "Pinki" (no "Común"):
  - Se obtiene la proporción del mes correspondiente
  - Si JD pagó $100.000 y proporción es 57/43 → Pinki le debe $43.000 a JD
  - Dashboard muestra saldo neto acumulado del período

#### Apps Script — Endpoints
- GET ?action=log&month=YYYY-MM → Log filtrado (excluye borrado=TRUE)
- GET ?action=log → Todo el log
- GET ?action=config → Config + Tarjetas + Categorías
- GET ?action=proportions&month=YYYY-MM → Proporciones calculadas
- GET ?action=delete&id=LOG-XXXXX → Marca borrado=TRUE

#### Dashboard — 3 vistas + filtro global
- **Filtro:** Mes vigente (default) / Rango de fechas
- **Vista Gastos:** Cards resumen + fijos + cuotas comprometidas + deudas + recordatorio tarjetas. Torta por categoría. Barras apiladas 6 meses. Tabla con botón borrar.
- **Vista Inversiones:** Card resumen. Torta por tipo. Línea evolución acumulada. Tabla.
- **Vista Ingresos:** Card resumen + fondo común. Líneas JD vs Pinki evolución. Barras por categoría. Tabla. Card proporción actual.
- **Tecnología:** Chart.js (CDN), fetch a Apps Script, AppSheet iframe

## Estructura de Carpetas
```
LIFE/
├── CLAUDE.md
├── CLAUDE.local.md
├── CLAUDE-AI.md
├── .claude/
│   ├── settings.json
│   ├── rules/
│   ├── commands/
│   ├── skills/
│   └── agents/
│       └── context-keeper.md
├── docs/
│   ├── CONTEXTO.md
│   ├── BITACORA.md
│   ├── DECISIONES.md
│   ├── STACK.md
│   └── VAULT.md
├── tasks/
│   ├── todo.md
│   └── lessons.md
├── marca/jdg/
├── apps-script/
│   └── finanzas-api.js
├── appsheet/
│   └── SETUP-FINANZAS.md
└── src/                        ← GitHub Pages sirve desde acá
    ├── index.html              ← LIFE hub
    ├── jardin/
    │   ├── index.html
    │   └── data/Plantas 260327/
    └── finanzas/
        └── index.html
```

## Convenciones
- Idioma del código: inglés (variables, funciones, comentarios técnicos)
- Idioma de documentación: español (argentino)
- Commits: conventional commits en español
- Los archivos de contexto (`docs/`) se actualizan en cada sesión de trabajo
- Nunca usar "vale la pena" ni "no vale la pena" en ninguna respuesta
- Término "chufa" = fertilizantes, pesticidas, productos de cuidado de plantas

## Watch Out For
- **HEIC en Safari:** Google Drive HEIC links fallan en Safari. Solución: convertir a .webp y servir localmente
- **Georreferencia:** Describir posición de plantas respecto al entorno físico (paredes, muebles), NUNCA respecto a otras plantas
- **D-SIST:** Prohibido en Anthurium, Asparagus, Ficus, Philodendron — validar siempre contra ficha técnica
- **Proporcionalidad:** Cada mes tiene su propia proporción basada en salarios de ese mes. No usar proporción fija
- **GitHub Pages source:** Configurar para servir desde `src/` (o el branch/carpeta que corresponda)
- **Apps Script cold start:** El primer request después de inactividad tarda ~1-2s. Normal, no es un bug.
- **Apps Script re-deploy:** Cambios al código del API requieren crear un NEW deployment, no editar el existente. La URL cambia.
- **ID autogenerado (Log):** Implementado via Apps Script trigger (finanzas-triggers.js). Requiere ejecutar `setupTriggers()` una sola vez desde el editor Apps Script.
- **AppSheet iframe post-submit:** Después de enviar un formulario en AppSheet, el iframe queda en la pantalla de confirmación. El usuario debe cerrar y reabrir el drawer para cargar otro dato.
- **APPSHEET_URL vacío:** Si la constante está vacía, el drawer muestra un mensaje de configuración en lugar del iframe. No es un error.
- **Apps Script acceso publico:** Todo Web App de Apps Script llamado desde `fetch()` del browser sin autenticacion debe deployarse con "Execute as: Me / Who has access: Anyone". Si se deploya con acceso restringido, el fetch falla con 403 o redirect a login. Aplica a finanzas-api.js, inventario-api.js, y cualquier API futura.
- **AppSheet seguridad publica:** Antes de embeber una app AppSheet como iframe en un sitio publico, configurar Security > Require Sign-in como desactivado. Si falta este paso, el iframe muestra error CSP frame-ancestors.
- **AppSheet iframe lazy loading:** El iframe de AppSheet debe crearse dentro de `openDrawer()` (primer clic en el boton +), no en `init()`. Patron: `if (!body.querySelector('iframe')) { ... body.appendChild(iframe); }`. Atributo requerido: `allow="camera; microphone"`.
- **Read tool bloqueado en .md:** El hook cbm-code-discovery-gate bloquea tool Read. Usar Bash cat para leer archivos de docs/ y tasks/.
- **C1 fix pendiente de re-deploy:** El bug en `getProportions()` (filtraba `row.categoria === 'Salario'` en lugar de `row.subcategoria === 'Salario'`) fue corregido en `finanzas-api.js` en Sesion 16. El fix NO esta activo en produccion hasta que el usuario cree un NEW deployment del Apps Script. Hasta entonces, la proporcion dinamica sigue usando fallback 50/50. (Nota: la descripcion en CONTEXTO Sesion 16 estaba invertida — el filtro CORRECTO es por `subcategoria`.)
- **Fallback silencioso en getProportions:** Si `source` en la respuesta del endpoint proportions dice `'fallback'` o `'default_50_50'`, la proporcion dinamica no esta funcionando. Verificar que el Log tenga entradas tipo=Ingreso, categoria=Salario para el mes consultado.
- **Node heredoc para ediciones complejas:**
- **corresponde_a en AppSheet:** El campo corresponde_a del Log debe agregarse manualmente en AppSheet con valor default 'Comun' y Show_If opcional. Sin esto, las nuevas entradas no tendran el campo y la logica de deudas usara 'Comun' por fallback (correcto pero sin diferenciacion).
- **Python stdout en Windows:** En scripts Python que corren en Windows, los caracteres Unicode fuera de ASCII (como flechas U+2192) en sentencias print() causan UnicodeEncodeError que aborta el script. Si el write() es posterior al print(), el archivo no se modifica aunque los prints anteriores parezcan exitosos. Usar solo ASCII en print() o configurar stdout a utf-8. Usar `node << 'EOF'` con delimitador en comillas simples para evitar interpolación de shell en contenido CSS/JS.
- **renderGastosPie state ordering:** `_gastosCategRows = rows` DEBE estar en la primera línea de `renderGastosPie()`, antes de cualquier filtrado. Si se asigna después de filtrar, los re-renders desde `setGastosPersonaFiltro()` usan filas ya filtradas como input — perdiéndose datos del conjunto original.
- **Sidebars: actualizar TODOS los módulos al agregar uno nuevo:** Cuando se agrega un módulo, verificar hub + jardin + finanzas + inventario + compras + recetario + cualquier módulo existente. Los sidebars incompletos pasan desapercibidos hasta que se revisa manualmente.
- **MailApp.sendEmail() límite:** 100 emails/día en cuentas personales de Google, 1500/día en Google Workspace. No hay un rate limit por invocación — el botón "Enviar lista" del módulo Compras usa este servicio.
- **Apps Script: colisión de nombres de constantes globales entre archivos del mismo proyecto:** Todos los archivos `.js` de un mismo proyecto Apps Script comparten el mismo scope global. Si dos archivos declaran `const COMPRAS_SPREADSHEET_ID`, el segundo falla con "Identifier has already been declared". Solución: usar sufijos descriptivos por módulo (ej: `COMPRAS_SS_ID_R` para Recetario). Aplica a cualquier constante global declarada en múltiples archivos del mismo proyecto.
- **Recetario RECETARIO_API_URL vacío:** Si la constante está vacía, el dashboard muestra un mensaje de configuración. No es error — para reactivar, pegar URL del deployment de recetario-api.js. (Setup completado en Sesion 22.)
- **Recetario unidades → Compras:** cdita/cda/taza son unidades válidas en Ingredientes pero NO existen en el dropdown de ListaCompras. Al llamar `?action=add` de compras-api.js, mapear esas unidades a 'u'. El mapping está hardcodeado en `agregarAlSuper()` de `src/recetario/index.html`.
- **renderGastosPersonales (F-16/F-17) requiere tipo_proporcion=custom:** La sección "Gastos Personales" solo muestra datos si el Log tiene entradas con `tipo_proporcion=custom` y `proporcion_jd=100 o 0`. Sin esas entradas, muestra empty state. No es un bug — es por diseño (gastos 100% personales son excepciones explícitas).
- **persona-btn vs period-btn:** Los botones de filtro persona en vista Gastos usan clase `.persona-btn` (NO `.period-btn`). Razón: `selectPeriodType()` llama `querySelectorAll('.period-btn').forEach(b => b.classList.toggle('active', b.dataset.period === type))`. Sin `data-period`, los botones de persona perderían su clase `active` al cambiar el período. Si se agregan nuevos botones de filtro tipo "toggle con estado", usar una clase CSS específica separada de `.period-btn`.
- **getRowPct() escala 0-100:** `getRowPct(row, p1, p2)` devuelve `{pct1, pct2}` en escala 0-100. Condiciones correctas: `=== 0` (no participa), `=== 100` (100% solo), `> 0` (participa). NO usar `=== 1` ni `>= 0.5`.
- **S.fixed.data: monto vs monto_mensual:** `monto` = valor bruto de la hoja. `monto_mensual` = valor mensual real (bimestrales ya divididos por 2). Siempre usar `monto_mensual` para cálculos. Aplica en `computeFixedForPersona()` y cualquier lógica que itere `S.fixed.data`.
- **getFixed() lastDay para vigencia:** El filtro `vigente_desde <= lastDay` (donde `lastDay = targetMonth + '-31'`) permite gastos que arrancan a mitad del mes. Si se vuelve a `firstDay`, gastos con vigencia al día 2+ del mes quedan excluidos.
- **5 estados _gastosPersonaFiltro (T4):** `'comun'|'jd_comun'|'jd'|'pinki_comun'|'pinki'`. Los gastos fijos NO pasan por `applyPersonaFiltro` (vienen de S.fixed, no del Log) — se filtran con `computeFixedForPersona(filtro)`. Sub-labels del card total solo visibles en modo `'comun'`.
- **onGastosFijosChange requiere setupTriggers():** El trigger para auto-ID GF-XXX en GastosFijos fue agregado en Sesión 24. Para activarlo: ejecutar `setupTriggers()` desde el editor de Apps Script. Pisa cualquier ID que no empiece con `GF-`, incluyendo los IDs propios de AppSheet.
- **id_appsheet_log en cuotas expandidas:** El trigger `expandCuotas()` copia toda la fila original incluyendo `id_appsheet_log`. Para que AppSheet no confunda las cuotas generadas por el trigger con la fila madre, se limpia `id_appsheet_log = ''` en cada cuota nueva. El guard `if (cols.id_appsheet_log >= 0)` lo hace backward-compatible si la columna no existe.
- **Card total Gastos = varTotal + fixTotal + cuotasComprometidas:** `varTotal` excluye `cuota_nro > 1` para no doble-contar con `cuotasComprometidas`. Los gastos fijos (`fixTotal`) solo aplican en modo Común del filtro persona — en modo JD/Pinki son $0 (los fijos son compartidos por naturaleza).
- **falsy-zero en serialización de API (`|| default`):** `parseFloat(0) || 50 === 50` porque 0 es falsy en JS. Para campos numéricos donde 0 es válido (como `proporcion_jd`), usar `(val != null && val !== '') ? parseFloat(val) : default` en lugar de `val || default`. Aplica en toda la serialización de `getFixed()` y cualquier endpoint que devuelva proporciones.
- **getTarjetaLabel() helper global:** La función `getTarjetaLabel(id)` resuelve IDs de tarjeta (ej: "TC1") a su label legible. Prioridad: `t.label` (col H de Tarjetas) > `banco + ' – ' + nombre` > raw ID. Siempre usarla en lugar de closures locales. Requiere que `S.tarjetas` esté cargado.
- **sub-labels card Total: 3 capas (var + fijos + cuotas):** Los sub-labels "JD: $X · Pinki: $Y" deben iterar las mismas 3 fuentes que el total: (1) filteredRows con cuota_nro === 1, (2) S.fixed.data, (3) filterCuotasComprometidas + applyPersonaFiltro. Usar solo filteredRows como proxy omite fijos y doble-cuenta cuotas.
- **toggleCreditoDetail vs renderCreditoCard — filtro persona:** En `renderCreditoCard`, aplicar filtro persona a fijos con Crédito para calcular el total económico correcto. En `toggleCreditoDetail` (panel desplegable), mostrar todos los fijos de Crédito sin filtro — el panel es informativo, no económico.
- **Asimetría de paths en render/toggle:** Cuando una función se puede invocar desde el render automático (pasa datos pre-filtrados) Y desde un toggle de usuario (reconstruye datos desde cero), verificar que ambos paths apliquen exactamente las mismas reglas de filtrado. Ejemplo: `renderDeuda()` pasa `debtRows` filtrado, pero `toggleDeudaDetail()` reconstruía rows sin el check de pct — causando discrepancia entre el card y el panel.
- **AppSheet envía campos opcionales vacíos — corregir en trigger, no en frontend:** Si AppSheet puede omitir un campo numérico donde 0 es el valor correcto (ej: `proporcion_jd` en gastos 100% de Pinki), agregar la corrección en `onLogChange` de Apps Script. Detectar `tipo_proporcion=custom` + `proporcion_jd` vacío → escribir 0. El frontend no debe inferir intenciones de campos vacíos con lógica de fallback.
- **getFixedKind() — clasificación shared/personal de gastos fijos:** `getFixedKind(item)` devuelve `'shared' | 'personal_p1' | 'personal_p2'` según `tipo_proporcion`/`proporcion_jd` (propiedad del gasto), NO según la proporción dinámica del mes. La visibilidad de un fijo en modo Común se decide por `getFixedKind(item) === 'shared'`, nunca por `pct1>0 && pct2>0`. Vive (duplicada) en `renderFijosDetailTable`, `computeFixedForPersona('comun')`, `renderCreditoCard` y `toggleCreditoDetail` — al cambiar la regla, propagar a las 4. Candidata a unificar (deuda técnica H8).
- **Visibilidad de fijos NO depende de la proporción del mes:** Un fijo compartido (`dinamica`) debe aparecer en modo Común aunque el mes tenga proporción 100/0 (un solo salario cargado). Acoplar la visibilidad al `pct` del mes hacía desaparecer todos los fijos en meses borde (bug raíz, Sesión 30). Ver [[finanzas-fijos-modelo-proporcion]] / LEC-032.
- **Total de fijos en común = monto_mensual de shared × meses del período:** `computeFixedForPersona('comun')` multiplica por `getMonthsInPeriod(S.period.from, S.period.to).length || 1`. La sub-línea "JD · Pinki" del card Total debe usar el MISMO set (shared) y el MISMO ×meses para que sub1+sub2 === total. Mes único = ×1.
- **Bimestrales en multi-mes — el history NO trae es_bimestral:** El `history` del API guarda `monto` crudo (sin /2) y sin el flag `es_bimestral`. En las ramas multi-mes de `computeFixedTotalForPeriod()` y `computePresupuestoParts()` hay que mapear `es_bimestral` desde `S.fixed.data` (que sí lo trae) y dividir `/2` los bimestrales al sumar. El gráfico de evolución (`renderFixedEvolution`) muestra el monto BRUTO a propósito — NO dividir ahí. Mes único ya usa `monto_mensual` (correcto).
- **Crédito card — mismo criterio de fijos que el resto:** `renderCreditoCard` y `toggleCreditoDetail` clasifican fijos-crédito en Común con `getFixedKind==='shared'` y aplican `monto_mensual × meses`. Ambos paths deben quedar idénticos (render vs toggle del mismo dato) — si se cambia uno, cambiar el otro.
