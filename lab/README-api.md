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
| `GET /api/health` | Sin parámetros | `{"ok":true,"capabilities":["expenses","income","fixed"],"mode":"live"}` |
| `GET /api/expenses?month=YYYY-MM` | `month` opcional | `{"expenses":[...]}`; excluye bajas lógicas |
| `POST /api/expenses` | `fecha`, `monto`, `moneda`, `categoria`, `subcategoria`, `medio_pago`, `pagado_por`, `descripcion_original`, `tarjeta_id`, `tipo_proporcion`, `proporcion_jd`, `proporcion_pinki`, `cuotas_total` | `201 {"expenses":[...]}`; una fila por cuota |
| `DELETE /api/expenses/:id` | Sin cuerpo | `{"deleted":true,"id":N}`; borra lógicamente solo esa cuota |
| `GET /api/income` | Sin parámetros | `{"income":[...]}`; excluye bajas lógicas |
| `POST /api/income` | `fecha`, `monto`, `moneda`, `categoria`, `persona`, `descripcion_original` | `201 {"income":{...}}` |
| `PATCH /api/income/:id` | Subconjunto no vacío de los campos del alta | `{"income":{...}}`; rechaza con `404` si el ingreso está borrado |
| `DELETE /api/income/:id` | Sin cuerpo | `{"deleted":true,"id":N}`; borra lógicamente ese ingreso |
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
`401` sin el header de auth interno.
El comando para el coordinador es `python3 -m pytest -q tests` (desde `lab/`).
Esta corrida no tuvo shell disponible para ejecutarlas; el coordinador debe
correrlas antes de aceptar el candidato.
