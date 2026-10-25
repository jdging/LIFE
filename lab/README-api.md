# API HTTP local de LIFE (candidato)

Implementación WSGI con la biblioteca estándar de Python. Usa las funciones de
`db.py` para escribir y consultar SQLite; las modificaciones de dominio en
`db.py` resuelven el historial de versiones del mismo día y el reparto de
cada versión de gasto fijo, y la baja lógica de ingresos (t_ce790609, mismo
patrón que la baja lógica de gastos). No instala
dependencias de terceros. La importación de `api.py` no inicia un servidor.

## Inicio y alcance

```python
from api import create_app

app = create_app(db_path="/ruta/explicita/a/base-efimera.sqlite",
                 internal_secret="valor-provisto-por-el-operador")
```

Ambos argumentos son obligatorios. La factoría inicializa o migra únicamente
la base indicada; nunca selecciona `data/lasso.sqlite`. También acepta
`db_path=":memory:"`: conserva una conexión ancla y abre una conexión distinta
por request, de modo que el contenido persiste durante la vida de la app.
`app.close()` libera el ancla al terminar. Con una ruta de archivo, cada request
abre y cierra su propia conexión. Las altas, bajas y versiones conservan las
transacciones de `db.py`.

La entrada CLI requiere puerto, ruta y secreto explícitos. Escucha solamente
en `127.0.0.1`:

```text
python api.py --port PUERTO --db-path RUTA_EFIMERA --secret-file ARCHIVO_LOCAL
```

También existe `--secret VALOR`, aunque ese valor queda visible en la lista de
procesos. No hay valores predeterminados para el puerto, la base o el secreto.
Esta entrega no activa infraestructura ni publica la API.

## Contrato general

Todas las rutas `/api` requieren `X-Internal-Proxy-Secret`, comparado en tiempo
constante. Una credencial ausente o incorrecta devuelve `401`, incluso en
`/api/health`. No hay autenticación individual: las escrituras auditadas usan
`sesion_compartida:no_verificado`. `actor`, `confirmado`, `origen` y otros campos
de control no se aceptan del cliente; la API fija `confirmado=True` en altas de
gastos e ingresos. Eso habilita la barrera del dominio, pero no atribuye una
identidad JD/Pinki al request.

Las respuestas son JSON (`application/json; charset=utf-8`) y llevan
`Cache-Control: no-store`. Los errores tienen `{"error":"mensaje"}` sin reflejar
valores enviados por el cliente. Se usan `400` para entrada
inválida, `401` para autenticación, `404` para recurso inexistente, `405` para
método no admitido, `409` para conflictos de estado, integridad o SQLite ocupado,
`413` para cuerpos de más de 64 KiB y `422` si datos legacy o acumulados
impiden calcular una respuesta fiable. Una falla inesperada devuelve un error genérico `500`
sin traza ni secreto. Se rechazan claves JSON repetidas, campos y parámetros
desconocidos, parámetros repetidos, `NaN`, infinito y booleanos en campos
numéricos. Las respuestas se serializan con `allow_nan=False`: no contienen
`NaN` ni `Infinity`. Cada ruta y método admite solo los parámetros query
indicados en la tabla; las escrituras requieren query vacía. `POST`, `PATCH`
y la baja de fijos requieren un objeto JSON y
`Content-Type: application/json`.

Si la ruta existe pero el método no está permitido, la respuesta `405` incluye
`Allow` con los métodos admitidos. Una ruta desconocida devuelve `404` sin ese
encabezado.

Las fechas de entrada usan `YYYY-MM-DD` válido y los meses `YYYY-MM` válido.
Las fechas de alta de gastos e ingresos son opcionales, según el dominio; si se
omiten, `db.py` registra la fecha y hora actual. `cuotas_total` omitido usa el
valor de dominio `1`. No se asigna un responsable por defecto a un fijo.

Los montos de entrada (`monto`, `monto_estimado`) deben ser positivos, finitos,
representables con hasta dos decimales y no superar `1e12` en valor absoluto.
Es un límite técnico del servidor; no define el alcance económico del producto.
Se valida antes de cualquier escritura, incluido el monto heredado por versiones
y bajas de fijos. Si falla, responde `400` sin alterar la base. `cuotas_total`
debe ser un entero entre `1` y `120`, con al menos un centavo por cuota. Los IDs
de ruta deben ser positivos, de hasta 19 dígitos y como máximo
`9223372036854775807`. Los resúmenes comprueban montos legacy y acumulados
antes de usar los cálculos de deuda y proporción; si son inválidos o exceden
el límite técnico, responden `422` sin números inventados.

## Endpoints

| Método y ruta | Entrada | Respuesta exitosa |
| --- | --- | --- |
| `GET /api/health` | Sin parámetros | `{"ok":true,"capabilities":["expenses","income","fixed","inventory"],"mode":"live"}` |
| `GET /api/expenses?month=YYYY-MM` | `month` opcional | `{"expenses":[...]}`; excluye bajas lógicas |
| `POST /api/expenses` | `fecha`, `monto`, `moneda`, `categoria`, `subcategoria`, `medio_pago`, `pagado_por`, `descripcion_original`, `tarjeta_id`, `tipo_proporcion`, `proporcion_jd`, `proporcion_pinki`, `cuotas_total` | `201 {"expenses":[...]}`; una fila por cuota |
| `DELETE /api/expenses/:id` | Sin cuerpo | `{"deleted":true,"id":N}`; borra lógicamente solo esa cuota |
| `GET /api/income` | Sin parámetros | `{"income":[...]}`; excluye bajas lógicas |
| `POST /api/income` | `fecha`, `monto`, `moneda`, `categoria`, `persona`, `descripcion_original` | `201 {"income":{...}}` |
| `PATCH /api/income/:id` | Subconjunto no vacío de los campos del alta | `{"income":{...}}`; rechaza con `404` si el ingreso está borrado |
| `DELETE /api/income/:id` | Sin cuerpo | `{"deleted":true,"id":N}`; borra lógicamente ese ingreso |
| `GET /api/inventory` | Sin parámetros | `{"inventory":[...]}`; excluye bajas lógicas |
| `POST /api/inventory` | `nombre` y `valor_estimado` obligatorios; `categoria`, `ubicacion`, `fecha_adquisicion`, `notas`, `precio_ars`, `cotizacion_usd_compra`, `precio_usd_compra`, `proporcion_jd`, `precio_venta_estimado_usd`, `estado` opcionales | `201 {"inventory":{...}}` |
| `PATCH /api/inventory/:id` | Subconjunto no vacío de los campos del alta; cualquier campo opcional (incluido `fecha_adquisicion`) puede mandarse en `null` explícito para vaciarlo | `{"inventory":{...}}`; rechaza con `404` si el bien está borrado |
| `DELETE /api/inventory/:id` | Sin cuerpo | `{"deleted":true,"id":N}`; borra lógicamente ese bien |
| `GET /api/fixed?dateISO=YYYY-MM-DD` | `dateISO` opcional; sin fecha usa hoy | `{"fixed":[...]}`; una versión activa por serie, cada una con `monto_mensual` |
| `GET /api/fixed/versions` | Sin parámetros | `{"versions":[...]}`; todas las versiones, incluidas las bajas, con `monto_mensual` |
| `GET /api/fixed/range?fromISO=...&toISO=...` | Dos fechas obligatorias, rango inclusivo | `{"range":[{"fijo_grupo_id":N,"tramos":[...]}]}` |
| `GET /api/fixed/:id/historial` | `id` de cualquier versión | `{"historial":[...]}` de toda la serie, con `vigente_hasta` y `monto_mensual` |
| `POST /api/fixed` | `nombre`, `monto_estimado`, `periodicidad`, `responsable`, `vigente_desde` obligatorios; `tipo_proporcion` y `proporcion_jd` según la tabla siguiente | `201 {"fixed":{...}}` |
| `PATCH /api/fixed/:id` | `vigente_desde` obligatorio y cambios en `nombre`, `monto_estimado`, `periodicidad`, `responsable`, `tipo_proporcion`, `proporcion_jd` | `{"fixed":{...}}` con id de la nueva versión |
| `DELETE /api/fixed/:id` | `{"fecha_baja":"YYYY-MM-DD"}` | `{"fixed":{...}}` con versión inactiva nueva |
| `GET /api/summary?month=YYYY-MM` | `month` opcional | Con mes: objeto resumen; sin mes: `{"months":[...]}` |
| `GET /api/categories?tipo=Gasto\|Ingreso\|Inversión` | `tipo` obligatorio, uno de esos tres valores exactos | `{"categories":[{"categoria":"Hogar","subcategorias":["Alquiler","Expensas",...]},...]}` |

`monto` de gastos e ingresos debe ser positivo. Un ingreso requiere `persona`
`JD` o `Pinki`; `Común` no es válida. Un fijo exige `responsable` `Común`, `JD`
o `Pinki`, y `periodicidad` `mensual` o `bimestral`. Para el detalle de todas las
reglas de reparto y cuotas se aplican las validaciones del dominio. La baja de
fijos crea una versión inactiva desde `fecha_baja`; las versiones anteriores
siguen consultables. `PATCH /api/fixed/:id` también crea una versión, y el `id`
puede ser de cualquier versión de la serie. `DELETE /api/income/:id` hace baja
lógica, mismo contrato que `DELETE /api/expenses/:id` (ver más abajo): sin
cuerpo, `200` con `{"deleted":true,"id":N}`, `404` si el id no existe o ya
está borrado, auditoría en `auditoria` con tabla `'ingresos'`, y `UPDATE`
condicionado a `deleted_at IS NULL` para resolver la carrera de una doble
baja concurrente.

### Reparto de gastos fijos

Los campos `tipo_proporcion` y `proporcion_jd` describen la **versión** del
fijo. La API devuelve ambos campos en el alta, la edición, la baja y todas las
lecturas de fijos (`/api/fixed`, `/versions`, `/range` y `/historial`). No
calcula porcentajes dinámicos al serializar: el consumidor los obtiene para
el mes consultado. En modo `custom`, el porcentaje de Pinki es
`100 - proporcion_jd`.

| Responsable | Entrada admitida | Valores guardados y devueltos |
| --- | --- | --- |
| `Común`, dinámico | Omitir ambos campos, o enviar `"tipo_proporcion":"dinamica"` y omitir `proporcion_jd` o enviarlo como `null`. También se acepta `"dinamico"` como alias de entrada. | `"tipo_proporcion":"dinamica","proporcion_jd":null` |
| `Común`, manual | `"tipo_proporcion":"custom","proporcion_jd":N` con `N` numérico finito de `0` a `100` inclusive. | `"tipo_proporcion":"custom","proporcion_jd":N` |
| `JD` | Omitir los campos de reparto o enviarlos como `null`. | `"tipo_proporcion":null,"proporcion_jd":100` |
| `Pinki` | Omitir los campos de reparto o enviarlos como `null`. | `"tipo_proporcion":null,"proporcion_jd":0` |

`proporcion_jd` no acepta booleanos, `NaN`, infinito, valores fuera de rango
ni strings numéricos. `custom` exige porcentaje; `dinamica` exige porcentaje
ausente o `null`. No se aceptan valores de reparto explícitos para un
responsable personal. Un fijo nuevo requiere `responsable` válido; la lectura
de versiones legacy con `responsable:null` sigue disponible. La capa de
dominio conserva esas versiones legacy sin inventarles responsable, mientras
que `POST` y `PATCH` web exigen pertenencia válida.

Ejemplos de altas (además de `nombre`, `monto_estimado`, `periodicidad` y
`vigente_desde`):

```json
{"responsable":"Común","tipo_proporcion":"custom","proporcion_jd":0}
```

```json
{"responsable":"Común","tipo_proporcion":"dinamica"}
```

```json
{"responsable":"JD"}
```

En `PATCH`, omitir reparto al editar solo nombre, monto o periodicidad conserva
el reparto de la versión vigente en `vigente_desde`. Omitir `tipo_proporcion`
en un fijo común también permite editar solo `proporcion_jd` cuando la versión
vigente ya es `custom`. Cambiar a `dinamica` limpia el porcentaje. Cambiar de
`Común` a `JD` o `Pinki` guarda el 100 % personal indicado en la tabla, sin
arrastrar un porcentaje común anterior. Volver de personal a `Común` sin
reparto explícito selecciona `dinamica`; para volver a `custom`, enviar tipo y
porcentaje juntos. Cada cambio real crea una versión y una auditoría, sin
alterar versiones previas. Un `PATCH` sin cambio real devuelve `400` y no crea
versión ni auditoría. También devuelven `400` las combinaciones inválidas de
reparto, antes de escribir.

Una baja repetida de un gasto o de un ingreso devuelve `404`: el recurso ya no
existe como activo. Dos bajas concurrentes (mismo id, misma tabla) se
serializan con `BEGIN IMMEDIATE` sobre conexiones SQLite separadas; una
devuelve `200`, la otra `404`, y se conserva una sola auditoría. Si SQLite no
concede el bloqueo dentro de su espera, devuelve `409` para reintentar.

En `GET /api/fixed/:id/historial`, todas las versiones permanecen auditables.
Una versión desplazada por otra con la misma `vigente_desde` lleva
`supersedida_mismo_dia:true`, `tiene_intervalo_vigencia:false` y
`vigente_hasta:null`. La última versión de ese día lleva
`supersedida_mismo_dia:false`, `tiene_intervalo_vigencia:true` y conserva
vigencia hasta el día anterior a la siguiente fecha distinta, o sin fin si no
hay siguiente fecha. El frontend debe ignorar las versiones sin intervalo al
dibujar períodos; `GET /api/fixed/range` ya las excluye de `tramos`.

El resumen mensual contiene `month`, `expenses_total`, `income_total`,
`fixed_total_mensual`, `proportion`, `debt_month`,
`debt_pending_through_month` y `debt_status`. Usa las funciones de proporción,
deuda y estado de `db.py`. `fixed_total_mensual` suma los fijos vigentes al
último día del mes para incluir altas dentro del mes; no suma todas las
versiones. Los totales de gastos e ingresos incluyen solo movimientos de ese
mes, y tanto gastos como ingresos excluyen bajas lógicas. Sin `month`, se
devuelve un resumen por cada mes presente en gastos activos o ingresos
activos, ordenado de menor a mayor. La proporción salarial conserva el
fallback histórico definido por `db.py`, también excluyendo ingresos
borrados lógicamente (un ingreso borrado no cuenta ni para el mes consultado
ni para el fallback a un mes anterior).

`GET /api/categories` expone de solo lectura el catálogo dinámico de
`db.get_categorias` (tabla `categorias`) para poblar el desplegable de
categoría/subcategoría al dar de alta un gasto. `tipo` es obligatorio y debe
ser exactamente `Gasto`, `Ingreso` o `Inversión`; si falta o no es uno de esos
tres valores, responde `422` (excepción puntual a la convención `400` del
resto de la validación de query, pedida así por el dominio). Las filas se
agrupan por `categoria`, en el orden de primera aparición por `id`; dentro de
cada categoría, las subcategorías se listan sin valores nulos ni vacíos, sin
duplicados, en el orden en que aparecen por `id`. Una categoría sin ninguna
subcategoría válida igual aparece, con `"subcategorias":[]`. Una base sin
filas en `categorias` devuelve `{"categories":[]}`, nunca un error. No agrega
ninguna ruta de escritura ni validación nueva sobre altas de gastos: las
categorías que ya aceptan `POST /api/expenses` no cambian.

### Inventario (`/api/inventory`)

Tabla `inventario_bienes`: `nombre`, `categoria`, `ubicacion`, `valor_estimado`,
`fecha_adquisicion`, `notas`, más los seis campos de paridad financiera con el
legacy descritos abajo. `nombre` es obligatorio y no puede estar vacío.
`valor_estimado` es obligatorio, numérico, finito y mayor a `0` (mismo criterio
que `monto` de gastos/ingresos); además debe pasar por la validación general de
montos del servidor (positivo, hasta dos decimales, no superar `1e12`).
`categoria`, `ubicacion` y `fecha_adquisicion` son opcionales; si se envían
con un valor no nulo, `categoria`/`ubicacion` no pueden ser strings vacíos y
`fecha_adquisicion` debe ser `YYYY-MM-DD` válida. `notas` es de texto libre y
admite vacío. `POST`/`PATCH` rechazan campos desconocidos con `400`; `PATCH`
exige al menos un campo y responde `404` si el bien no existe o ya está
borrado.

**Vaciar un campo en `PATCH` (t_0e38e74e, corrección del hallazgo 3 del
revisor 46d4f3d5).** Cualquier campo opcional —incluido `fecha_adquisicion`—
puede mandarse en `null` explícito para borrarlo: la validación de formato
(`fecha_adquisicion` ISO, montos opcionales, `estado` en
`INVENTARIO_ESTADOS`) solo se aplica cuando el valor enviado no es `null`.
El `POST` de alta sigue sin aceptar `null` para estos campos — el frontend
directamente omite los que están vacíos al crear, porque ahí no hay nada
previo que borrar.

**Mapeo de campos del legacy (t_0e38e74e).** Juan pidió explícitamente paridad
con la pestaña de inventario legacy (`reference-legacy/inventario-setup.js` /
`inventario-index.html`, BRIEF.md punto 1); esto revierte una decisión previa
de esta misma tarea que dejaba esos campos solo como texto libre en `notas`.

| Campo de la API | Nombre en el legacy | Tipo / validación |
| --- | --- | --- |
| `nombre` | `descripcion` | Texto, obligatorio, no vacío (mismo campo, nombre heredado del esquema previo) |
| `fecha_adquisicion` | `fecha_compra` | `YYYY-MM-DD`, opcional (mismo campo, nombre heredado) |
| `precio_ars` | `precio_ars` | Monto opcional, admite `0`, hasta 2 decimales, ≤ `1e12` |
| `cotizacion_usd_compra` | `cotizacion_usd_compra` | Monto opcional, admite `0`, hasta 2 decimales, ≤ `1e12` |
| `precio_usd_compra` | `precio_usd_compra` | Monto opcional, admite `0`; si se omite y llegan `precio_ars` y `cotizacion_usd_compra` válidos (cotización > 0), la API lo sugiere como `precio_ars / cotizacion_usd_compra`, redondeado a 2 decimales (`_sugerir_precio_usd_compra`); un valor explícito, incluido `0`, nunca se pisa |
| `proporcion_jd` | `proporcion_jd` | Numérico finito, `0`-`100` inclusive; opcional al crear (default `50` en `insert_inventario_bien` si se omite); Pinki = `100 - proporcion_jd`, igual que el legacy |
| `precio_venta_estimado_usd` | `precio_venta_estimado_usd` | Monto opcional, admite `0`, hasta 2 decimales, ≤ `1e12` |
| `estado` | `estado` | Texto opcional, uno de `INVENTARIO_ESTADOS` (`Activo`, `Vendido`, `Donado`, `Desechado`); default `'Activo'` al crear si se omite |

Los seis campos de paridad (`precio_ars`, `cotizacion_usd_compra`,
`precio_usd_compra`, `proporcion_jd`, `precio_venta_estimado_usd`, `estado`) se
agregaron como columnas `REAL`/`TEXT` **nullable** vía `ALTER TABLE ADD COLUMN`
idempotente (`_migrar_columnas_inventario_bienes`), nunca `NOT NULL` a nivel
SQL. Los defaults de negocio (`proporcion_jd=50`, `estado='Activo'`) se
aplican en Python (`insert_inventario_bien`) solo al crear un bien sin
especificarlos, no en el `ALTER TABLE`. `estado` se valida contra
`INVENTARIO_ESTADOS` en `validar_inventario_bien`, no con un `CHECK` de SQL
(mismo criterio que `PAGADO_POR_VALIDOS` en `validaciones.py`). Los cuatro
campos monetarios opcionales (`precio_ars`, `cotizacion_usd_compra`,
`precio_usd_compra`, `precio_venta_estimado_usd`) admiten `0` a diferencia de
`valor_estimado`, que exige estrictamente mayor a `0`
(`INVENTORY_MONEY_OPTIONAL_FIELDS` en `api.py`).

**Migración y backfill (t_0e38e74e, corrección del hallazgo 1 del revisor
46d4f3d5; procedencia endurecida en el hallazgo 1 y 2 del revisor fc195491).**
`migrar_datos_reales.migrar_inventario_bienes` escribe los seis campos de
paridad en sus columnas estructuradas desde `inventario_raw.json` (no solo en
`notas`); `notas` queda únicamente con la nota real del Excel. Para una base
donde `inventario_bienes` ya fue migrado con el código VIEJO (esos campos
quedaron solo como texto libre en `notas`, generado por
`_armar_notas_inventario`), existe `backfill_inventario_legacy(conn,
inventario_raw)`: idempotente, empareja por `(nombre, fecha_adquisicion,
categoria)` — las tres, no solo nombre+fecha, para no emparejar con el bien
equivocado — y un bien solo es **elegible** si, además de ese emparejamiento,
su `notas` actual es EXACTAMENTE el bloque que `_armar_notas_inventario`
genera para esa misma fila del raw (única prueba de que nunca fue tocado
desde la web, ya que la web no genera ese bloque, y de que los valores que
encierra el bloque —cotización, USD de compra, reparto, reventa, estado—
coinciden con los del raw actual). Si la nota fue editada, ya fue limpiada
por un backfill anterior, o el raw tiene valores distintos a los que el
bloque encierra, el bien se omite por completo (ni columnas ni notas) y se
reporta en `bienes_sin_procedencia_legacy`, sin inventar ninguna
coincidencia. Un bien elegible solo completa columnas en `NULL` (nunca pisa
un valor ya cargado por la web, ni siquiera un `0`) y al aplicar limpia el
bloque de `notas`, reemplazándolo por la nota real — eso hace que un bien ya
procesado deje de ser elegible para siempre, y que un vaciado posterior de
una columna hecho desde la web (enviando `null` por `PATCH`) nunca se vuelva
a repoblar en una corrida futura. CLI: `python3 migrar_datos_reales.py
--backfill-legacy` corre en modo dry-run por default (imprime el resumen, no
escribe nada); agregar `--apply` para aplicar los cambios de verdad. El
coordinador la ejecuta sobre la base real cuando corresponda.

**Baja lógica.** Mismo patrón que ingresos: `_migrar_columnas_inventario_bienes`
agrega `deleted_at`/`deleted_by` con `ALTER TABLE ADD COLUMN` idempotente (no
recrea la tabla, no pierde datos ya migrados). `DELETE /api/inventory/:id` no
borra la fila: marca `deleted_at`/`deleted_by` con `UPDATE ... WHERE id = ? AND
deleted_at IS NULL`, deja un registro en `auditoria` con tabla
`'inventario_bienes'` y el snapshot previo, y responde `404` si el id no
existe o ya estaba borrado — incluida la carrera de una doble baja
concurrente, igual que `DELETE /api/income/:id`. `GET /api/inventory` excluye
siempre los bienes borrados lógicamente; no hay ruta de restauración.

## Telegram (brief S2/S3, T1/T2 de CTO-DISENO.md)

Rutas **internas**: no se agregan al proxy de Vercel (`middleware.js` no se
toca). Misma auth `X-Internal-Proxy-Secret`, mismo formato de errores y las
mismas validaciones que las rutas equivalentes sin `/telegram`. El CLI (T3) y
la skill de Lasso (T4) consumen este contrato en una tarea posterior.

| Método y ruta | Entrada | Respuesta exitosa |
| --- | --- | --- |
| `GET /api/tarjetas` | Sin parámetros | `{"tarjetas":[...]}`; catálogo completo, solo lectura |
| `POST /api/expenses/telegram` | Mismos campos que `POST /api/expenses`, más `chat_id`, `telegram_user_id`, `telegram_message_id` opcionales y `comprobante` opcional | `201 {"expenses":[...],"avisos_credito_nuevos":[...],"comprobante":{...}?}` |
| `POST /api/income/telegram` | Mismos campos que `POST /api/income`, más `chat_id`, `telegram_user_id`, `telegram_message_id` opcionales y `comprobante` opcional | `201 {"income":{...},"comprobante":{...}?}` |
| `GET /api/comprobantes/dedupe?hash=...&monto=&fecha=&comercio=` | `hash` obligatorio; `monto`, `fecha`, `comercio` opcionales | `{"duplicado":bool,"gasto_id":N\|null,"ingreso_id":N\|null,"coincidencia":"hash"\|"aproximada"\|null}` |
| `GET /api/avisos-credito/pendientes` | Sin parámetros | `{"avisos_credito":[{"mes","umbral","total_al_detectar","detectado_en","enviado_en":null},...]}` |
| `POST /api/avisos-credito/marcar-enviados` | `{"items":[{"mes":"YYYY-MM","umbral":N},...]}` | `{"actualizados":[{"mes","umbral"},...]}` |

`chat_id`, `telegram_user_id` y `telegram_message_id` son strings de dígitos,
con `-` inicial opcional (los `chat_id` de grupo de Telegram son negativos) y
longitud acotada a 32 caracteres; se validan igual en las dos rutas de alta.
`origen` se fija en `'telegram'` del lado del servidor, igual que las rutas
sin `/telegram` fijan `'api'` — el cliente nunca lo declara (`validaciones.py`
no restringe `origen` a una lista cerrada de valores; si la tuviera, habría
que agregar `'telegram'` ahí también, pero hoy no hace falta). Con `cuotas_total`,
`POST /api/expenses/telegram` expande en N filas igual que la ruta normal, y
cada fila hereda `chat_id`/`telegram_user_id`/`telegram_message_id`.

**`comprobante` (opcional en el body de alta).** Campos: `hash_archivo`
(obligatorio dentro del sub-objeto si este viene, hasta 128 caracteres),
`texto_extraido`, `monto_detectado`, `fecha_detectada`, `comercio_detectado`,
`ruta_archivo` (todos opcionales). Si viene, se inserta en
`comprobantes_telegram` en la MISMA transacción que el gasto/ingreso
(`db.insert_gasto_telegram`/`db.insert_ingreso_telegram`): si `hash_archivo`
ya existe, la respuesta es `409` y no se crea nada — ni el gasto/ingreso ni
el comprobante, atomicidad real, no una compensación posterior.

**Dedupe (`GET /api/comprobantes/dedupe`).** Primero busca coincidencia
exacta de `hash_archivo` (`coincidencia:"hash"`). Si no hay y se pasan
`monto` y `fecha`, busca coincidencia aproximada: mismo `monto_detectado`
(±0,01) y `fecha_detectada` dentro de ±1 día; `comercio` solo filtra si se
pasa. Sin coincidencia, `{"duplicado":false,"gasto_id":null,"ingreso_id":null,"coincidencia":null}`.

**Avisos de crédito (S3).** Cambio respecto del CTO 66f52e78 (ver
DECISIONES.md): esta API no tiene token de Telegram, así que **solo
detecta y registra** (`enviado_en` arranca en `NULL`); el envío al grupo y
el marcado como enviado los hace Lasso vía `hermes cron`, llamando primero a
`GET /api/avisos-credito/pendientes` y después a `POST
/api/avisos-credito/marcar-enviados`. Umbrales: `100000 + 50000·n` sobre
`total_credito_mes` (suma de `gastos.monto` con `medio_pago='Crédito'`,
`deleted_at IS NULL`, mes calendario — no ciclo de cierre de tarjeta; cada
cuota ya es su propia fila con su propia fecha). Tras un alta o baja de
gasto en `medio_pago='Crédito'`, **por cualquier ruta** (`/api/expenses`,
`/api/expenses/telegram` y `DELETE /api/expenses/:id`), la respuesta incluye
`avisos_credito_nuevos: [{"mes","umbral","total"},...]` con los umbrales
recién cruzados para el mes de cada fila involucrada (una por cuota en un
alta con cuotas). Un umbral ya registrado para un mes nunca se vuelve a
registrar ni se borra, aunque el total baje y vuelva a subir (sin
"desaviso", sin repetir un aviso ya mandado en el mismo mes).

**Migraciones (`db.py`, aditivas e idempotentes, mismo patrón `ALTER TABLE
ADD COLUMN` que ya usa el archivo).** `gastos` gana `telegram_user_id`/
`telegram_message_id` (`chat_id` ya existía); `ingresos` gana `chat_id`/
`telegram_user_id`/`telegram_message_id` (no tenía ninguno). Tablas nuevas
`comprobantes_telegram` y `avisos_credito` (ver `db.py` para el esquema
completo). `estado_conversacional` pasa de `UNIQUE(telegram_chat_id)` a
`UNIQUE(telegram_chat_id, usuario)`: dos usuarios del mismo chat tienen
borradores independientes. SQLite no permite alterar una restricción UNIQUE
existente, así que `db._migrar_estado_conversacional` recrea la tabla
preservando las filas en una transacción explícita (rename -> create ->
copy -> drop); es idempotente (detecta el índice único compuesto antes de
tocar nada) y segura sin pérdida de datos, porque bajo el esquema viejo
nunca pudo existir más de una fila por `telegram_chat_id`. `set_estado`/
`get_estado`/`clear_estado` ahora toman `usuario` opcional (default `None`
= mismo comportamiento que antes de esta migración, comparado con `IS` en
vez de `=` para que `NULL` siga matcheando `NULL` de forma determinística).

## Pruebas preparadas

`tests/test_api.py` usa archivos temporales y `:memory:`; incluye inyección
WSGI, regresión del enrutamiento (`200`/`404`/`405` y `Allow`), parser JSON
estricto, rechazo sin escritura, reparto de fijos en altas y versiones,
normalización al cambiar responsable, historial del mismo día, concurrencia WSGI
con dos conexiones a un archivo SQLite efímero, una prueba HTTP de loopback,
migración de una base temporal legacy, y el contrato completo de
`DELETE /api/income/:id` (`200`/`404`/`401`/cuerpo rechazado, exclusión del
`GET` y recálculo del resumen mensual). `tests/test_ingresos.py` cubre la baja
lógica de ingresos a nivel `db.py` (baja, doble baja, inexistente, auditoría,
recálculo de `calcular_proporcion_mes` sin el borrado, edición rechazada
sobre un ingreso borrado, y migración idempotente de columnas sobre una base
vieja sin `deleted_at`/`deleted_by`). El mismo `tests/test_api.py` también
cubre `GET /api/categories`: base sin categorías, agrupado y orden por `id`,
deduplicación y exclusión de subcategorías nulas/vacías, filtrado por `tipo`,
`422` con `tipo` ausente/inválido, `400` con query desconocida o repetida, y
`401` sin el header de auth interno. `tests/test_inventario.py` cubre los seis
campos de paridad con el legacy end-to-end (alta, edición y lectura por
`GET`/`POST`/`PATCH /api/inventory`), la sugerencia de `precio_usd_compra` a
partir de `precio_ars`/`cotizacion_usd_compra` sin pisar un valor explícito
(incluido `0`), los rangos válidos (`proporcion_jd` `0`-`100`, montos ≥ `0`,
`estado` en `INVENTARIO_ESTADOS`), la migración idempotente de las columnas
nuevas sobre una tabla `inventario_bienes` vieja sin ellas, y que `PATCH`
acepte `null` explícito en los campos opcionales (incluido `fecha_adquisicion`)
para vaciarlos sin romper la validación de formato.
`tests/test_backfill_inventario.py` cubre `backfill_inventario_legacy` con un
dataset sintético: completa columnas `NULL` desde `inventario_raw`, recupera
la nota real cuando `notas` coincide exactamente con el bloque legacy, nunca
pisa un valor ya cargado por la web, reporta sin match/match ambiguo sin
tocar nada, es idempotente en una segunda corrida, e incluye el CLI
(`--backfill-legacy` dry-run por default, `--apply` para escribir de
verdad). Además (fix al revisor fc195491): una `notas` editada no es
elegible y por lo tanto tampoco completa columnas; un campo vaciado por la
web después de un primer backfill no se repuebla en una segunda corrida;
mismo nombre y fecha con otra categoría no empareja; y un bloque legacy
cuyos valores no coinciden con los del raw actual se omite por completo en
vez de completar con datos que no corresponden.
`tests/test_telegram_api.py` (nuevo, brief S2/S3 T6) cubre: migración
idempotente de `estado_conversacional` sobre una base vieja con filas
cargadas (preserva `usuario`/`estado`/`payload_parcial`); migración
idempotente de las columnas Telegram nuevas en `gastos`/`ingresos`; dos
usuarios del mismo chat con borradores independientes (alta, update y
borrado de uno sin tocar el otro) y el caso sin `usuario` explícito
(compatibilidad con el comportamiento previo a la migración); `POST
/api/expenses/telegram` e `/api/income/telegram` (origen fijado
server-side, ids de Telegram devueltos, validación idéntica a la ruta sin
`/telegram`, formato de `chat_id`/`telegram_user_id`/`telegram_message_id`,
cuotas, comprobante insertado en la misma transacción, `409` por hash
duplicado sin crear nada, `401` sin auth); `GET /api/tarjetas`; `GET
/api/comprobantes/dedupe` (hash exacto, aproximado por monto+fecha+comercio,
sin coincidencia, `400` sin `hash`); umbrales de crédito (cruce simple,
varios de golpe en un solo alta — 80k→210k registra 100k/150k/200k —, baja
que no desregistra, resuba que no repite un umbral ya registrado, cuotas en
meses distintos con mes calendario, gasto no-Crédito que no cuenta) tanto a
nivel `db.py` como en la respuesta de las rutas HTTP; y `GET
/api/avisos-credito/pendientes` + `POST /api/avisos-credito/marcar-enviados`
(idempotente, valida la forma de `items`).

El comando para el coordinador es `python3 -m pytest -q tests` (desde `lab/`).
Esta corrida no tuvo shell disponible para ejecutarlas; el coordinador debe
correrlas antes de aceptar el candidato.
