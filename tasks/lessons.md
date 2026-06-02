# Lecciones Aprendidas

> Errores corregidos, gotchas descubiertos, reglas para la próxima vez.

---

### LEC-022: querySelectorAll('.period-btn') puede borrar el estado de botones no relacionados
- **Fecha:** 2026-04-08
- **Qué pasó:** `selectPeriodType()` llama `querySelectorAll('.period-btn').forEach(b => b.classList.toggle('active', b.dataset.period === type))`. Al cambiar el período, cualquier botón con clase `period-btn` que no tenga `data-period` pierde su clase `active`. Si los botones del filtro persona usaran `period-btn`, quedarían desactivados al cambiar el mes.
- **Solución:** Usar una clase CSS diferente (`.persona-btn`) con el mismo estilo visual pero nombre separado. El `querySelectorAll` no la toca.
- **Regla:** Antes de reutilizar una clase CSS en un elemento nuevo, verificar si existe algún `querySelectorAll` o `querySelector` que la use para manipular estado. Si existe, crear una clase nueva con el mismo aspecto visual pero nombre diferente.

---

### LEC-023: expandCuotas() copia id_appsheet_log de la fila madre a todas las cuotas
- **Fecha:** 2026-04-08
- **Qué pasó:** El trigger de expansión de cuotas construye cada cuota copiando `originalRow[j]` para todos los campos, incluyendo `id_appsheet_log`. Las cuotas 2..N heredan el ID interno de AppSheet de la fila madre — AppSheet no puede distinguir la madre de sus cuotas.
- **Solución:** Después de construir `newRow`, limpiar explícitamente `newRow[cols.id_appsheet_log] = ''`. Las cuotas trigger-generated no tienen ID de AppSheet propio.
- **Regla:** Cuando un trigger copia una fila para crear filas derivadas, revisar si hay campos de identidad externa (id_appsheet, id_externo, etc.) que deban limpiarse. Solo la fila original tiene ese ID; las derivadas deben quedar vacías.

---

### LEC-024: varTotal en vista Gastos incluía cuota_nro > 1 causando doble conteo
- **Fecha:** 2026-04-08
- **Qué pasó:** `renderGastos()` calculaba `varTotal = sum(rows, 'monto_total')` donde `rows` incluía cuotas diferidas (cuota_nro > 1). Esas mismas cuotas también aparecían en el card "En cuotas" y en `filterCuotasComprometidas()`. El card total era incorrecto por doble conteo.
- **Solución:** `varTotal = sum(rows.filter(r => (parseInt(r.cuota_nro)||1) === 1), 'monto_total')`. Agregar `cuotasTotal` como suma separada de `filterCuotasComprometidas()`. `total = varTotal + fixTotal + cuotasTotal`.
- **Regla:** En cualquier cálculo de total que tenga un breakdown (variables + fijos + cuotas), verificar que cada fila aparezca en exactamente una categoría. `renderComposicion()` ya tenía esta lógica correcta; `renderGastos()` no — la inconsistencia estaba silenciosa.

---

### LEC-001: Template como fuente de verdad
- **Fecha:** 2026-03-27
- **Qué pasó:** En proyectos anteriores, el contexto se perdía entre sesiones de chat
- **Solución:** Crear estructura de documentación viva en carpeta del proyecto
- **Regla:** Siempre actualizar docs/ al final de cada sesión. El chat es efímero, los archivos persisten.

---

### LEC-002: Hook cbm-code-discovery-gate bloquea tool Read en archivos .md
- **Fecha:** 2026-04-02
- **Qué pasó:** El tool Read queda bloqueado por un hook que exige usar codebase-memory-mcp antes de leer cualquier archivo. En archivos de documentación (no código), esto es innecesario.
- **Solución:** Usar Bash con cat para leer archivos .md de docs/ y tasks/
- **Regla:** Para leer docs/*.md o tasks/*.md en este proyecto, usar Bash cat en lugar del tool Read.

---

### LEC-003: Backticks en strings dentro de node -e causan interpolación de shell
- **Fecha:** 2026-04-02
- **Qué pasó:** Al escribir contenido con backticks (paths de archivos en markdown) dentro de node -e "...", bash los interpreta como command substitution
- **Solución:** Usar heredoc (node << 'JSEOF' ... JSEOF) con comillas simples para evitar interpolación
- **Regla:** Para node con contenido que incluya backticks o comillas especiales, siempre usar heredoc con comillas simples en el delimitador.

---
### LEC-004: Node heredoc es el método más robusto para editar archivos con contenido complejo
- **Fecha:** 2026-04-02
- **Qué pasó:** Intentos de usar Edit tool o node -e con strings complejos (backticks, comillas, caracteres especiales) fallaron. El heredoc con delimitador de comillas simples (node << 'EOF') previene toda interpolación.
- **Solución:** Para cualquier edición de archivos con contenido que incluya CSS, JS, o markdown con caracteres especiales, usar node con heredoc + replace de string en memoria.
- **Regla:** node << 'EOF' ... EOF es el método preferido para ediciones programáticas complejas en este proyecto.

---

### LEC-005: Revisar Show_If de campos segun tipo de transaccion
- **Fecha:** 2026-04-02
- **Que paso:** El campo medio_pago aparecia para tipo=Ingreso en AppSheet, confundiendo al usuario
- **Solucion:** Show_If [tipo] <> "Ingreso" en AppSheet para ese campo
- **Regla:** Al disenar formularios con multiples tipos de transaccion, revisar que campos tienen sentido para cada tipo y agregar Show_If apropiados. Candidatos a revisar: medio_pago (solo Gasto/Inversion), tarjeta (solo Gasto con credito/debito), es_fijo (tiene sentido para todos?), cuotas_total (solo Gasto con tarjeta de credito).

---

### LEC-007: Embedido de datos relacionados en la respuesta del API evita round trips
- **Fecha:** 2026-04-03
- **Qué pasó:** Para el gráfico de historial de gastos fijos, la primera idea era hacer un fetch extra al hacer clic en cada fila de la tabla. Eso implica latencia + cold start de Apps Script cada vez.
- **Solución:** Incluir el `history` completo (mapa descripcion → array de versiones) directamente en la respuesta del endpoint `?action=fixed`. Al cargar la vista, ya están todos los datos disponibles.
- **Regla:** Cuando un endpoint probablemente va a necesitar datos relacionados para funcionalidades secundarias (gráficos, drill-down), incluirlos embedidos en la respuesta principal si el overhead es pequeño. Evita latencia extra en apps de uso personal donde el dataset es chico.

---

### LEC-008: Cuota self-reference — primera fila del grupo usa cuota_ref = su propio id
- **Fecha:** 2026-04-04
- **Qué pasó:** Al construir grupos de cuotas en el seed, la primera fila necesita cuota_ref para que el dashboard pueda vincular todas las cuotas. Pero el id de la primera fila aún no existe cuando se empieza a construirla.
- **Solución:** `const firstId = nextId(); rows.push(mkR(firstId, ..., firstId, ...))` — se genera el id antes de construir la fila y se pasa como cuota_ref de sí misma.
- **Regla:** Siempre usar self-reference en la primera cuota del grupo. Las cuotas 2..N referencian firstId. Esta convención es la que usa el trigger de Apps Script al expandir cuotas reales.

---

### LEC-009: propJd = 0 es un valor válido que NO debe tratarse como falsy
- **Fecha:** 2026-04-04
- **Qué pasó:** Al construir filas de cuotas con proporcion_jd=0 (Pinki paga el 100%), el check `propJd || ''` convertiría 0 en '' — incorrectamente.
- **Solución:** `(propJd !== undefined && propJd !== null) ? propJd : ''` — verificación explícita de undefined/null, no de falsiness.
- **Regla:** Cualquier campo numérico que pueda ser 0 como valor legítimo debe verificarse con `!== undefined && !== null`, no con el operador lógico `||`.

---

### LEC-006: Node heredoc falla con paths de Windows que tienen espacios y backslashes
- **Fecha:** 2026-04-03
- **Qué pasó:** Al usar `node << 'EOF'` con paths como `G:\My Drive\15 - Sistemas\...`, las secuencias `\t`, `\r`, `\1` son interpretadas como escape sequences, corrompiendo el path aunque el heredoc esté en comillas simples (las comillas simples solo previenen interpolación de shell, no de Node).
- **Solución:** Usar los tools Write o Edit directamente para archivos de documentación. Si se necesita Node, pasar el path como variable de entorno: `FILE_PATH="..." node -e "require('fs').writeFileSync(process.env.FILE_PATH, ...)"`.
- **Regla:** Preferir Write/Edit tools sobre Bash+Node para modificar archivos .md en este proyecto. Node heredoc es seguro solo si el path no contiene backslashes o secuencias de escape.

---

### LEC-010: Windows cp1252 trunca la escritura de Python si hay caracteres Unicode en print()
- **Fecha:** 2026-04-05
- **Que paso:** Un script Python escribia un archivo grande en 7 pasos. Los pasos 1-6 habian aplicado cambios en memoria. El paso 7 tenia un `print(f"7. filterLog -> from/to OK")` con la flecha U+2192 (->). Windows stdout usa cp1252 por defecto -- ese caracter no es encodeable. La excepcion aborto el script ANTES de llegar a `f.write(content)`. El archivo no se modifico, pero los prints 1-6 ya habian salido en la consola, dando la impresion de exito.
- **Solucion:** Reemplazar todo caracter Unicode no-ASCII en sentencias print() por equivalentes ASCII. La flecha -> es el sustituto directo de U+2192.
- **Regla:** En scripts Python que corren en Windows con stdout cp1252, nunca usar caracteres Unicode fuera del rango ASCII en print(). El error puede parecer exitoso si ocurre despues de varios prints pero antes del write(). Alternativa: `sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)` al inicio del script.

---


### LEC-011: Apps Script debe deployarse con acceso abierto para fetch desde browser
- **Fecha:** 2026-04-05
- **Que paso:** El dashboard de Inventario no cargaba datos. El error en consola era HTTP 403 o redirect a login. Apps Script estaba deployado con "Execute as: Me / Who has access: Only myself" (o similar autenticado).
- **Solucion:** Redeployar el Web App con "Execute as: Me / Who has access: Anyone" (sin autenticacion requerida). El usuario lo corrigio manualmente en la consola de Apps Script.
- **Regla:** Todo Apps Script deployado como Web App que sea llamado desde `fetch()` en un browser sin autenticacion debe tener "Who has access: Anyone". Si se olvida, el primer request falla con redirect a login o 403. Esto aplica a todos los modulos: finanzas-api.js, inventario-api.js, cualquier API futura.

---

### LEC-012: AppSheet requiere configuracion de seguridad publica para embeberse en iframe
- **Fecha:** 2026-04-05
- **Que paso:** El drawer del dashboard de Inventario abria pero el iframe mostraba error CSP (frame-ancestors). La app de AppSheet tenia seguridad configurada para usuarios autenticados solamente.
- **Solucion:** En la configuracion de la app AppSheet, configurar Security > Require Sign-in como "No" (o equivalente) para que cualquier usuario pueda abrir la app sin autenticarse. El usuario lo corrigio manualmente en AppSheet.
- **Regla:** Al crear una app AppSheet que se va a embeber como iframe en un sitio publico, configurar la seguridad como publica antes de pegar la URL en el dashboard. El error CSP frame-ancestors es la senal de que falta este paso.

---

### LEC-014: Bugs de fallback silencioso son mas dificiles de detectar que crashes
- **Fecha:** 2026-04-06
- **Que paso:** `getProportions()` filtraba salarios por `row.subcategoria === 'Salario'` cuando el schema tiene `categoria = 'Salario'` (no subcategoria). El filtro nunca encontraba filas, pero en vez de crashear retornaba la proporcion por defecto (50/50 o ultimo mes con datos). La feature parecia funcionar.
- **Solucion:** Fix de una linea — cambiar el nombre del campo. El bug estuvo en produccion durante todo el desarrollo sin que nadie lo notara porque el fallback enmascaraba el error.
- **Regla:** Cuando una funcion tiene un fallback automatico (50/50, ultimo mes conocido, valor por defecto), agregar logging o un campo `source` en la respuesta que indique si se uso el fallback. Un campo `source: 'fallback'` en el JSON del API ya estaba implementado — usarlo como alarma en el dashboard seria util. Verificar siempre nombres de campos contra el schema real antes de escribir filtros.

---

### LEC-013: Iframe de AppSheet debe crearse lazily (en el primer clic, no en init)
- **Fecha:** 2026-04-05
- **Que paso:** El dashboard de Inventario creaba el iframe de AppSheet en `init()` al cargar la pagina, antes de que el usuario haga clic en el boton +. Esto causaba que el iframe intentara cargar aunque el drawer estuviera cerrado, potencialmente fallando silenciosamente o afectando performance.
- **Solucion:** Crear el iframe dentro de `openDrawer()` solo si no existe ya uno. Patron: `if (!body.querySelector('iframe')) { const iframe = document.createElement('iframe'); ... body.appendChild(iframe); }`. Este patron viene de finanzas/index.html y funciona correctamente en ambos modulos.
- **Regla:** Los iframes de AppSheet deben crearse lazily (la primera vez que se abre el drawer). Esto evita requests innecesarios al cargar la pagina y asegura que el iframe solo se crea cuando el usuario lo necesita. Atributo requerido: `allow="camera; microphone"`.

---

### LEC-015: Verificar texto exacto con Grep antes de usar Edit tool en archivos grandes
- **Fecha:** 2026-04-06
- **Que paso:** Al intentar editar `_drawerWidth` en `src/inventario/index.html`, el string usado para `old_string` incluia el texto del comentario de la variable. El comentario real en el archivo diferia del que se habia generado en sesion anterior ("ancho en px, variable de sesion (se resetea al recargar)" vs "ancho inicial en px (variable de sesion, no localStorage)"). El Edit tool fallo con "string not found".
- **Solucion:** Antes de cualquier Edit en un archivo que no se acaba de leer completo, usar Grep para encontrar el texto exacto del patron que se quiere reemplazar.
- **Regla:** En archivos grandes (>500 lineas), siempre hacer Grep del texto a reemplazar antes de llamar al Edit tool. Los comentarios pueden diferir de lo que se recuerda de sesiones anteriores.

---

### LEC-016: corresponde_a fue reemplazado por tipo_proporcion=custom — no usar ambos
- **Fecha:** 2026-04-06
- **Que paso:** El campo `corresponde_a` (Comun/JD/Pinki) fue la primera implementacion de "a quien le corresponde el gasto". Al agregar `tipo_proporcion` y `proporcion_jd`, el mismo comportamiento se logra con `custom + proporcion_jd=100/0`. `getDeudaPct()` que usaba `corresponde_a` fue eliminado.
- **Solucion:** Toda la logica de division de gastos pasa por `getRowPct(row, p1, p2)`. El campo `corresponde_a` queda en la Sheet como dato historico pero no se usa en codigo.
- **Regla:** No agregar logica nueva que lea `corresponde_a`. Si una fila historica necesita ser interpretada, `tipo_proporcion=custom` con el valor adecuado es la forma correcta. `getRowPct()` es el punto central de toda la logica de proporcion.

---

### LEC-017: Separar balance de display en paneles que muestran ítems históricos
- **Fecha:** 2026-04-06
- **Que paso:** Al implementar SALDADO-01, el panel de deuda necesitaba mostrar todas las filas (incluyendo saldadas) pero calcular el balance solo sobre las activas. La tentacion inicial era filtrar debtRows antes de pasarlos al panel.
- **Solucion:** Calcular `activeDebtRows = debtRows.filter(r => !r.saldado)` para el balance del card, pero pasar `debtRows` completo a `renderDeudaDetailPanel()`. Dentro del panel, las filas saldadas no suman a debeP1/debeP2 pero si se renderizan (con opacity y label saldado).
- **Regla:** Cuando un panel muestra historial pero el card muestra estado activo, separar los dos conjuntos explicitamente. No usar el mismo array filtrado para ambos. El usuario quiere ver que existen items saldados aunque no afecten el balance.

---

### LEC-018: data-desc para identificar filas cuando el td tiene contenido mixto
- **Fecha:** 2026-04-06
- **Que paso:** Al implementar el highlight de fila activa en la tabla de gastos fijos, el intento inicial era usar `tr.querySelector('td').textContent.trim()`. Pero el primer `<td>` contenia el nombre del gasto mas el badge " bimestral" en un span interno. El textContent incluia ese texto y el match fallaba o daba falsos positivos.
- **Solucion:** Agregar atributo `data-desc="${r.descripcion}"` en el `<tr>` y comparar con `tr.dataset.desc === descripcion`. Limpio, no depende del contenido DOM.
- **Regla:** Cuando el contenido visible de una celda puede diferir del valor logico (badges, spans, iconos), usar data-attributes en el elemento para el matching programatico. Es mas robusto que parsear textContent.

### LEC-019: State de input en renderGastosPie debe guardarse antes de filtrar
- **Fecha:** 2026-04-06
- **Que paso:** Al implementar FEAT-01 (filtro por persona en torta de gastos), `_gastosCategRows = rows` estaba asignado DESPUES de calcular los grupos por categoria. Al llamar `setGastosPersonaFiltro()`, el state ya era el resultado filtrado de la llamada anterior — los re-renders consumian filas ya filtradas como input, perdiendo datos.
- **Solucion:** Mover `_gastosCategRows = rows` a la PRIMERA linea de `renderGastosPie(rows)`, antes de cualquier filtrado. El state siempre guarda el input original completo.
- **Regla:** Cuando una funcion de render tiene un estado de cache (`_gastosCategRows`), asignar el cache ANTES de cualquier transformacion del input. Si el cache se asigna despues de filtrar, los re-renders desde funciones externas usaran datos ya transformados como punto de partida.

---

### LEC-020: Sidebars incompletos pueden pasar desapercibidos durante el desarrollo
- **Fecha:** 2026-04-06
- **Que paso:** El sidebar de `src/jardin/index.html` tenia solo 2 items (Home + Jardin) desde la sesion inicial del modulo. Al agregar nuevos modulos en sesiones posteriores, solo se actualizo el hub y los modulos nuevos. Jardin quedo desactualizado silenciosamente.
- **Solucion:** Al crear o actualizar el sidebar de cualquier modulo, verificar que TODOS los modulos existentes tengan el nuevo item. No solo el hub y el modulo nuevo.
- **Regla:** Cada vez que se agrega un modulo al sistema, hacer un pass por todos los `index.html` existentes y agregar el nav item. Crear un checklist mental: hub + jardin + finanzas + inventario + compras + recetario + cualquier modulo existente.

---

### LEC-021: Colision de nombres de constantes en Apps Script entre archivos del mismo proyecto
- **Fecha:** 2026-04-07
- **Que paso:** `recetario-setup.js` declara `const COMPRAS_SPREADSHEET_ID` con el mismo nombre que `compras-setup.js`. En Apps Script, todos los archivos de un mismo proyecto comparten el mismo scope global — si ambos archivos se pegan en el mismo proyecto, la segunda declaracion falla con "Identifier has already been declared".
- **Solucion:** `recetario-api.js` usa `COMPRAS_SS_ID_R` (sufijo R) para evitar la colision. Para el setup, el usuario debe asegurarse de que cada archivo de setup de un modulo diferente use nombres de constantes distintos, o pegar los scripts en archivos separados dentro del proyecto Apps Script.
- **Regla:** Al crear un nuevo Apps Script que comparte Sheet con un modulo existente, usar sufijos descriptivos en las constantes globales (ej: `_R` para Recetario, `_C` para Compras). Documentar en Watch Out For de CLAUDE.md.

---

---

### LEC-022: getRowPct devuelve escala 0-100, no 0-1
- **Fecha:** 2026-04-09
- **Que paso:** El prompt del usuario especificaba `pct1 >= 1` como condición para "100% de JD". Como `getRowPct()` devuelve porcentajes en escala 0-100, la condición correcta es `pct1 === 100` (no `=== 1`). Similarmente, "pct > 0" para "tiene algún %".
- **Solucion:** Verificar siempre la escala de retorno antes de usar comparadores. `getRowPct()` retorna `{pct1, pct2}` donde 50/50 = `{50, 50}`, custom 100% JD = `{100, 0}`.
- **Regla:** `getRowPct` siempre en escala 0-100. Condiciones: `=== 0` (no participa), `=== 100` (100% solo), `> 0` (participa en cualquier %). No usar `=== 1` ni `>= 0.5`.

---

### LEC-023: monto vs monto_mensual en S.fixed.data
- **Fecha:** 2026-04-09
- **Que paso:** Al implementar `computeFixedForPersona()`, el prompt decía "item.monto ya es el monto mensual". Leyendo `getFixed()` en finanzas-api.js: `monto` es el raw de la hoja (sin dividir por 2 para bimestrales); `monto_mensual` es el valor calculado (= monto/2 si es_bimestral).
- **Solucion:** Usar `item.monto_mensual` en toda lógica que necesite el costo mensual efectivo. `item.monto` es solo para mostrar el valor original del gasto.
- **Regla:** En `S.fixed.data`, siempre usar `monto_mensual` para cálculos. `monto` es el valor de la hoja, `monto_mensual` es el valor correcto ya procesado (bimestrales divididos por 2).

---

### LEC-024: vigente_desde con comparación de fecha como string — usar lastDay del mes
- **Fecha:** 2026-04-09
- **Que paso:** `getFixed()` usaba `firstDay = targetMonth + '-01'` como cota para `vigente_desde <= firstDay`. Un gasto nuevo el día 8 del mes no pasaba el filtro. El concepto correcto es "el gasto empezó durante o antes de este mes", no "antes de que empiece el mes".
- **Solucion:** `lastDay = targetMonth + '-31'`. La comparación lexicográfica de strings YYYY-MM-DD es correcta porque `'2026-05-01' > '2026-04-31'` aunque abril no tenga día 31.
- **Regla:** Para filtrar "cosas vigentes en el mes X": usar `vigente_desde <= (X + '-31')`. Para filtrar "cosas empezadas antes del mes X": usar `vigente_desde < (X + '-01')`. La diferencia es importante para gastos que arrancan a mitad del mes.

---

### LEC-025: falsy-zero con `|| default` en serialización de API — 0 es un valor legítimo
- **Fecha:** 2026-04-09
- **Que paso:** `getFixed()` en `finanzas-api.js` serializaba `proporcion_jd: parseFloat(current.proporcion_jd) || 50`. Cuando `proporcion_jd = 0` en la Sheet (gasto 100% de Pinki), `parseFloat(0) = 0` y `0 || 50 = 50`. La API devolvía 50 en lugar de 0, haciendo que el frontend mostrara 50/50 en lugar del 100% correcto para Pinki.
- **Solucion:** `(current.proporcion_jd != null && current.proporcion_jd !== '') ? parseFloat(current.proporcion_jd) : 50`. El check `!= null` (con coercion) descarta `null` y `undefined` pero permite `0`.
- **Regla:** Para campos numéricos donde 0 es un valor válido, NUNCA usar `valor || default`. Siempre usar `(val != null && val !== '') ? parseFloat(val) : default`. El operador `||` trata 0 como falsy. Aplica especialmente en serialización de datos de Sheets donde campos vacíos son string '' y valores válidos pueden ser 0.

---

### LEC-026: Diagnosticar en qué capa está un bug antes de asumir la causa
- **Fecha:** 2026-04-09
- **Que paso:** El usuario reportó que el card de Fijos mostraba 50/50 para un gasto 100% Pinki, y asumió que el bug estaba en `getRowPct()` del frontend. Leyendo el código de `getRowPct()`, la función maneja 0 correctamente (`raw !== undefined && raw !== null && raw !== ''`). El bug real estaba en `getFixed()` de la API.
- **Solucion:** Leer ambas capas (API y frontend) antes de proponer el fix. El flujo es: Sheet → API serializa → `S.fixed.data` → `getRowPct()` lee. Si el 0 llega mal desde la API, `getRowPct()` nunca puede corregirlo.
- **Regla:** Cuando un valor numérico se ve mal en el frontend, trazar el flujo completo: origen (Sheet) → API (`getFixed`) → estado (`S.fixed.data`) → función de display (`getRowPct`). No asumir que el bug está en la última función que toca el dato.

---

### LEC-027: filteredRows para sub-labels debe replicar las 3 capas del total (no solo varRows)
- **Fecha:** 2026-04-11
- **Que paso:** Los sub-labels "JD: $X · Pinki: $Y" se calculaban iterando solo `filteredRows`, que equivale a gastos variables del período. Pero el total del card incluye 3 capas: varTotal (cuota_nro === 1), fixTotal (gastos fijos de S.fixed.data), y cuotasTotal (cuotas comprometidas cuota_nro > 1). Los sub-labels sumaban menos que el total visible porque omitían fijos y cuotas, y encima incluían cuota_nro > 1 causando doble-conteo con cuotasTotal.
- **Solucion:** Replicar las 3 capas exactas en el cálculo de sub-labels: (1) filteredRows filtrando cuota_nro === 1, (2) S.fixed.data directo, (3) filterCuotasComprometidas + applyPersonaFiltro.
- **Regla:** Si un número visible N se calcula como la suma de M capas, sus sub-totales por persona también deben descomponer las mismas M capas. Usar una sola fuente de filas como proxy de N es incorrecto salvo que esa fuente los incluya a todos.

---

### LEC-028: getTarjetaLabel global helper — centralizar ID→label antes de escalarlo
- **Fecha:** 2026-04-11
- **Que paso:** Dos funciones distintas (`renderCuotasDetailTable` y `renderCreditoDetailPanel`) tenían closures locales `labelTarjeta` con lógica idéntica. Al agregar T2 (una tercera función que necesitaba el label), se detectó la duplicación.
- **Solucion:** Función global `getTarjetaLabel(id)` al inicio del script. Prioridad: `t.label` (columna H de Tarjetas) > `banco + ' – ' + nombre` > raw ID. Eliminadas las closures locales.
- **Regla:** Cuando una función de lookup se duplica dos veces, extraerla a helper global antes de duplicarla una tercera. El patrón `t.label || fallback_compuesto` es útil cuando la Sheet tiene una columna de label precalculada.

---

### LEC-029: toggleCreditoDetail vs renderCreditoCard — filtro persona difiere según contexto
- **Fecha:** 2026-04-11
- **Que paso:** Al agregar Capa 3 (fijos con Crédito) a la card de Crédito, la función `renderCreditoCard()` necesita aplicar filtro persona para el total económico (JD vs Pinki). Pero `toggleCreditoDetail()` (panel desplegable) muestra todas las filas sin filtro — para que el usuario vea el contexto completo aunque no sean "suyos".
- **Regla:** El filtro persona aplica a los totales económicos (cuánto me cuesta a mí), no necesariamente al listado informativo (qué existe). Mantener esta distinción al agregar fuentes de datos a cards existentes.

---

### LEC-030: Asimetría en paths de render — mismo dato, distintas rutas, distintas reglas
- **Fecha:** 2026-04-12
- **Que paso:** `renderDeuda()` calcula `debtRows` con filtro correcto (excluye pago=Común y pctOtro=0) y lo pasa a `renderDeudaDetailPanel()`. Pero `toggleDeudaDetail()` — el path que se activa cuando el usuario hace clic en la card — reconstruía los rows con `.filter(r => r.pago === p1 || r.pago === p2)` sin aplicar el check de proporción. El panel mostraba filas que el card no contaba.
- **Regla:** Cuando una función se puede invocar desde dos lugares distintos (render automático y acción del usuario), verificar que ambos paths apliquen exactamente las mismas reglas de filtrado. El bug de "dos paths" suele aparecer cuando el render automático pasa datos pre-filtrados pero el toggle reconstruye los datos desde cero.

---

### LEC-031: AppSheet envía campos opcionales vacíos — el trigger debe corregir valores default
- **Fecha:** 2026-04-12
- **Que paso:** Cuando Pinki carga un gasto con `tipo_proporcion=custom` en AppSheet pero no toca el campo `proporcion_jd`, AppSheet envía la celda vacía. El frontend (`getRowPct`) cae al fallback de 50 para `proporcion_jd` vacío, interpretando el gasto como 50/50 en lugar de 0% JD.
- **Regla:** Para campos donde el vacío tiene semántica incorrecta (no equivale a "sin dato"), el trigger de Apps Script debe corregir el valor default explícitamente. El frontend no debería ser responsable de inferir intenciones de campos vacíos que AppSheet omitió. Patrón: `if (condicion && campo_vacio) sheet.getRange(...).setValue(default_correcto)`.

---

### LEC-032: La visibilidad/clasificación de un gasto recurrente es una propiedad del gasto, no un cálculo dinámico
- **Fecha:** 2026-06-02
- **Que paso:** En Finanzas, los gastos fijos desaparecían de la vista Común en meses con proporción 100/0 (un solo salario cargado). La causa: la visibilidad usaba `pct1>0 && pct2>0`, y para un fijo `dinamica`, `getRowPct()` devolvía la proporción del mes activo → pct de una persona = 0 → el filtro lo descartaba.
- **Solucion:** Helper `getFixedKind(item)` que clasifica shared/personal_p1/personal_p2 por `tipo_proporcion`/`proporcion_jd` (regla propia del gasto), independiente del mes. Un fijo compartido (dinámico) es SIEMPRE shared, aunque el mes sea 100/0.
- **Regla:** Si un dato es conceptualmente estable (un fijo compartido es compartido siempre), su visibilidad/clasificación debe derivarse de una propiedad estable, NO de un cálculo dinámico que puede tomar valores de borde (0, 100, fallback). Acoplar visibilidad a un cálculo volátil hace desaparecer datos en los bordes.

---

### LEC-033: Lógica duplicada en N lugares — al cambiar la regla, propagar a TODAS las copias
- **Fecha:** 2026-06-02
- **Que paso:** La regla shared/personal y el patrón `monto_mensual × meses` viven en 4+ lugares (`renderFijosDetailTable`, `computeFixedForPersona`, `renderCreditoCard`, `toggleCreditoDetail`, + totales en `computeFixedTotalForPeriod`/`computePresupuestoParts`). El fix F-A se aplicó en 2 lugares; la card de Crédito quedó con el criterio viejo y el Bug A reaparecía ahí. Misma clase que LEC-030 (asimetría render/toggle).
- **Solucion:** Auditar todos los sitios que comparten la regla y propagar el cambio a cada uno. Anotado como deuda técnica (H8): unificar en un helper único.
- **Regla:** Antes de cerrar un fix sobre lógica que sospechás duplicada, `grep` el patrón completo en el archivo y verificá cada ocurrencia. El bug recurrente "arreglé una copia y olvidé las otras" se previene buscando antes de cerrar, no después.

---

### LEC-034: Total = suma de N capas → toda vista derivada debe usar el mismo set y multiplicador (universal)
- **Fecha:** 2026-06-02
- **Que paso:** Tras filtrar el card de fijos a solo `shared`, la sub-línea "JD · Pinki" seguía sumando TODOS los fijos → sub1+sub2 ≠ total. Y los bimestrales se mensualizaban (/2) en mes único pero se contaban completos en multi-mes → card multi-mes ≠ suma real.
- **Solucion:** Cada vista derivada (sub-línea, detalle, panel, composición) debe iterar el MISMO conjunto de filas y aplicar el MISMO multiplicador (×meses) y normalización (bimestral /2) que el total que pretende desglosar.
- **Regla (universal):** Cuando un número visible es la suma de N capas con transformaciones (filtro, ×meses, /2), cualquier desglose o vista alternativa de ese número debe replicar exactamente las mismas capas y transformaciones. Verificar el invariante: "la suma de las partes mostradas == el total mostrado", en todas las combinaciones de filtros y períodos.
