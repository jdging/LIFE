# CLI determinista de ingesta por Telegram (`lab/telegram_ingesta.py`)

Brief S2/S3, T3 de `CTO-DISENO.md` §1(a)/§1(c). Copia aislada de laboratorio
(`lab/reinvencion@ef0f1b0`) -- nada de repo real, datos reales, infra ni
deploy. Diseño y decisiones de alcance: `CTO-DISENO.md` y `DECISIONES.md`.

## Qué es

Telegram es el frontend conversacional LLM de LIFE para escribir en la base
SQLite mediante la API. No crea un registro financiero paralelo. Durante las
pruebas, la planilla sigue siendo el registro vigente y Telegram no la
sustituye.

Un cliente HTTP **puro-stdlib** (`urllib`) de la API candidata (`lab/api.py`,
ver `lab/README-api.md`). Nunca importa `db.py`/`api.py` ni abre la base
SQLite directo: toda lectura y escritura pasa por `/api/*` con el header
`X-Internal-Proxy-Secret` (justificación en `CTO-DISENO.md` §1(a) -- la API
ya es el único proceso que escribe el archivo SQLite; un segundo proceso
escribiendo directo compite por locks sin `busy_timeout`).

Es tanto un **CLI** (`python3 telegram_ingesta.py <subcomando> ...`) como un
**módulo importable** (`import telegram_ingesta`, usado así por los tests).

Pedidos de Juan (2026-10-25), ya aplicados en esta versión:

- **"Tenés que preguntar siempre quién hizo el gasto, porque a lo mejor
  Pinki carga un gasto hecho por JD."** `pagado_por` NUNCA tiene default por
  `telegram_user_id` -- ver "Defaults" más abajo.
- **"La onda del comprobante es que se lea todo desde ahí directamente sin
  tener que aclarar."** Con comprobante, la pregunta solo pide lo que el
  comprobante no trae -- ver `extraer-campos` y `pregunta --con-comprobante`
  más abajo.

Cada subcomando imprime **un solo objeto JSON por stdout** y termina con
`exit code 0`. Cualquier fallo (validación, archivo, red, o error de la API)
imprime `{"error": "..."}` -- con más claves estructuradas cuando aplica
(ej. `guardar` bloqueado por dedupe incluye `"duplicado": true, "dedupe":
{...}`) -- y termina con `exit code != 0`. Nunca deja escapar una traza de
Python sin capturar hacia el usuario.

Esto incluye errores de **argumentos de línea de comandos** (opción
desconocida, subcomando inexistente, falta un argumento requerido, incluido
`--secret` en claro, que no existe como opción): `main()` captura el
`ArgumentParser.error()` de `argparse` (vía una subclase que lo convierte en
excepción en vez de imprimir texto de uso por stderr y salir directo) y
también imprime `{"error": "..."}` por stdout, con `exit code 2`.

Como última red de contención, `main()` también captura cualquier
excepción no anticipada (un bug del CLI que no sea `CliError`/`ApiError`)
e imprime `{"error": "error interno: <NombreDeLaExcepción>"}` por stdout
con `exit code 1` -- sin traceback de Python ni datos del error original
hacia el usuario.

**Texto de comprobantes como DATO.** Todo lo que llega en campos de texto
(comercio, descripción, texto extraído de un PDF o de la visión de Lasso)
se trata con regex y comparaciones de string exactas -- el CLI nunca
ejecuta ni interpreta como instrucción nada que venga de un comprobante.

## Secreto interno

Nunca se acepta por valor de argumento (no existe un `--secret` como en
`lab/api.py`; solo `--secret-file`) ni se imprime en ningún mensaje de
error. Se resuelve así:

1. `--secret-file RUTA` si se especifica.
2. Si no, la variable de entorno `LIFE_API_SECRET_FILE`.
3. Si ninguno está presente: error claro (`exit code != 0`), sin adivinar
   ni usar un default.

El contenido del archivo (sin saltos de línea finales) es el secreto.

## Opciones globales (antes del subcomando)

| Opción | Default | Nota |
| --- | --- | --- |
| `--api-base URL` | `http://127.0.0.1:8765` | Base de la API candidata. Solo `http://`/`https://`; `http://` solo se acepta contra loopback (`127.0.0.1`/`localhost`/`::1`) -- cualquier otro host exige `https://`. |
| `--secret-file RUTA` | `$LIFE_API_SECRET_FILE` | Ver arriba. |
| `--usuarios-file RUTA` | `lab/telegram_usuarios.json` (junto a este script) | Mapeo `telegram_user_id -> {persona, nombre}`, usado por `normalizar`. |

**`--secret-file`, requisitos del archivo:** regular (no symlink, no FIFO/dispositivo), del mismo usuario que corre el CLI, y sin permisos de lectura/escritura/ejecución para grupo ni para otros (`0600` o `0400`). Cualquier otra combinación es un error explícito, sin leer el contenido.

**Cliente HTTP:** el opener nunca sigue redirecciones (`HTTPRedirectHandler` que las rechaza) -- el header `X-Internal-Proxy-Secret` no se reenvía nunca a un origen distinto del configurado en `--api-base`. Una respuesta 3xx de la API es un error explícito (`{"error": "..."}`), no se resuelve en silencio.

## `lab/telegram_usuarios.json`

Única fuente de verdad del mapeo usuario de Telegram -> persona del hogar
(ver `DECISIONES.md`):

```json
{
  "7355824354": {"persona": "JD", "nombre": "Juan"},
  "8842208210": {"persona": "Pinki", "nombre": "Regi"}
}
```

Lo carga `normalizar` para popular `telegram_user_id` en el borrador (quién
CARGÓ el mensaje -- ya no para defaultear `pagado_por`, ver "Defaults" más
abajo) y para validar que `telegram.user_id`, si viene, sea conocido. **Un
`user_id` que no está en este archivo es siempre un error explícito**
(`exit code != 0`), nunca se infiere una persona por default.

**Clave `"titulares"`**: mapeo `{"<nombre normalizado>": "JD"|"Pinki"}`
de titulares de cuenta de origen de un comprobante a la persona del hogar.
Incluye `juan david guzman → JD` y `regina pinchetti → Pinki`. Lo usan
`extraer-campos` y `normalizar` para
proponer `pagado_por_sugerido` cuando `titular_origen` (extraído de un
comprobante) matchea un titular mapeado -- con el mismo matching tolerante
(`_slug`, sin acentos/mayúsculas) que categorías. Un titular SIN
mapeo no sugiere nada: `pagado_por` simplemente queda en
`campos_faltantes`, igual que si no hubiera comprobante. Ejemplo:

```json
{
  "7355824354": {"persona": "JD", "nombre": "Juan"},
  "8842208210": {"persona": "Pinki", "nombre": "Regi"},
  "titulares": {"juan david guzman": "JD", "regina pinchetti": "Pinki"}
}
```

## Retención máxima de comprobantes: 40 días

En el VPS, **originales (PDF/fotos), PNG derivados y texto extraído sensible**
de comprobantes se eliminan al cumplir 40 días desde su **recepción**, nunca
desde la fecha impresa en el comprobante. No deben quedar copias de originales
ni renderizados fuera de esta política. El hash, el número de operación y los
vínculos contables con gastos/ingresos permanecen para deduplicación y
trazabilidad. La planilla sigue vigente durante las pruebas.

`lab/telegram_retencion.py` implementa la integración **local del candidato**,
sin cron ni activación real. `--root RUTA --init` marca un directorio absoluto
vacío fuera del repo y crea `incoming/`, `adjuntos/`, bloqueo y manifiesto.
El receptor escribe el archivo temporal en `incoming/` y llama
`--root RUTA --receive RUTA/incoming/archivo.pdf` al recibirlo; puede pasar
`--received-at` con la hora original ISO con zona si el handoff fue demorado.
El comando mueve el original a `adjuntos/` y registra `received_at` de forma
atómica. `extraer-pdf --out-dir RUTA/adjuntos` solo acepta un original
registrado en esa raíz y registra cada PNG con la misma hora de recepción.

`lab/telegram_retencion.py --root RUTA --db BASE.sqlite` coordina limpieza de
archivos manifestados y `comprobantes_telegram.texto_extraido`: hace dry-run
por defecto y requiere `--apply` para borrar. Prevalida ambos conjuntos,
borra archivos y luego limpia texto. Es idempotente para permitir reintento
si SQLite falla después de borrar archivos. El manifiesto contiene hasta
10.000 entradas con `path`, `kind` (`original` o `rendered_png`) y
`received_at` ISO con zona, por ejemplo:

```json
[{"path":"adjuntos/ejemplo.pdf","kind":"original","received_at":"2026-08-11T10:00:00+00:00"}]
```

Rechaza symlinks, rutas fuera de la raíz y entradas duplicadas; no borra
archivos ajenos al manifiesto. El receptor real todavía debe usar este handoff
para todos los adjuntos. La copia real de `fixtures-reales` y el documento de
cache quedan PENDIENTES de incorporar al ciclo real: no se inspeccionan ni
limpian aquí. No ejecutar `--apply` contra archivos reales en esta etapa.

**Evidencia y límites de esta corrida.** Hay tests sintéticos para recepción,
PNG, corte 39/40/41 días, rechazo de rutas no gestionadas, texto comprimido,
página alargada y timeout. El coordinador informó 9 fallos y 553 tests
aprobados antes de este ajuste; la suite posterior no se ejecutó porque el
wrapper de esta corrida lo prohíbe. La hipótesis del fallo común de PDF es
que `RLIMIT_AS` de 768 MiB limita también el espacio virtual del runtime al
importar PyMuPDF. El worker ahora mantiene un techo de 2 GiB durante ese
arranque y, en Linux, lo ajusta al espacio virtual medido más 768 MiB antes
de abrir el PDF. Queda pendiente verificarlo con el venv de ingesta. El
aislamiento de PDF y el bloqueo del manifiesto requieren un runtime POSIX
(`resource`/`fcntl`). El receptor real, el cron y las copias preexistentes no
están conectados ni activados aquí.

El candidato corrige la asimetría de cuotas del endpoint web: al expandir
un gasto de monto 120 en 120 cuotas, `lab/db.py` valida la disponibilidad de
centavos contra el total original y exige monto positivo en cada fila, igual
que en el flujo Telegram ya corregido. Hay cobertura HTTP para 120/120,
el límite de 0,01, un reparto no divisible y rollback ante falla intermedia.
Estas pruebas quedaron pendientes de ejecución por la restricción de esta
corrida; esta corrección no implica que Telegram o la retención estén activos
en producción.

El texto `comprobantes_telegram.texto_extraido` se prepara por separado con
`db.limpiar_texto_comprobantes_vencidos(conn, ahora=..., apply=False)`:
dry-run por defecto y `apply=True` explícito. Usa `creado_en` (recepción),
no `fecha_detectada`; solo pone `texto_extraido` en `NULL`, sin modificar
hash, número de operación, `gasto_id`, `ingreso_id` ni registros financieros.
La CLI `telegram_retencion.py --db` coordina esta función con el borrado de
archivos. No se creó cron ni se tocó el gateway.

## Subcomandos

### `extraer-pdf <ruta> [--out-dir DIR]`

```json
{"texto": str|null, "paginas": int, "fuente": "pdf_texto"|"sin_texto", "imagenes": [str, ...], "truncado": bool, "advertencias": [str, ...]}
```

Importa `pymupdf` de forma perezosa (solo al correr este subcomando): si no
está instalado, error claro y específico (`exit code != 0`), sin tocar el
resto del CLI. En la VPS, instalarlo en
`/home/ai-os/hermes/workspaces/lasso/tools/venv-ingesta` (`pip install
pymupdf` **solo en ese venv**).

**Límites contra PDFs hostiles (antes de abrir o procesar nada pesado):**

- `<ruta>` debe ser un archivo regular existente, nunca un symlink.
- Tamaño máximo **10 MB**: se chequea con `stat()` antes de abrir el PDF.
- `--out-dir`, si se pasa, debe ser `adjuntos/` de una raíz gestionada y el
  PDF debe estar registrado como original en su manifiesto.
- Máximo **20 páginas** procesadas para extracción de texto; si el PDF
  tiene más, se procesan solo las primeras 20 y la respuesta trae
  `"truncado": true`.
- Máximo **50.000 caracteres** de texto devuelto; PyMuPDF materializa el
  texto de cada página antes del recorte. La extracción corre en un
  subproceso con techo de espacio virtual de 2 GiB durante la carga de
  PyMuPDF. En Linux, antes de abrir el PDF se ajusta a la base virtual real
  del worker más 768 MiB (sin superar los 2 GiB); en otros POSIX queda el
  techo de 2 GiB. CPU de 10 s y timeout de 20 s, con entorno reducido sin
  variables de credenciales heredadas.
  Un exceso devuelve JSON de error limpio.
- PDF cifrado con contraseña (`doc.needs_pass`) o corrupto/con formato
  inválido: error claro en el JSON de salida (`{"error": "..."}`), nunca
  una traza de Python.
- Renderizado a imagen (solo si no hay texto extraíble): hasta **3**
  páginas, con DPI acotado a un valor fijo (150), nunca configurable por el
  usuario. Antes de renderizar cada página se calculan las dimensiones del
  pixmap resultante a partir de `page.rect` (en puntos) y el zoom
  (`dpi/72`): si superan **4.000.000 de píxeles** (ej. un `MediaBox`
  extremo), se reduce el zoom para que el pixmap entre en ese límite y cada
  dimensión sea <=4096 píxeles; si
  ni reduciendo el zoom al mínimo razonable entra, esa página se omite con
  una advertencia explícita en `"advertencias"` en vez de renderizarla.

**Comportamiento:**

- Si el PDF tiene texto extraíble (`page.get_text()`), devuelve
  `fuente="pdf_texto"` con el texto concatenado (hasta los límites de
  arriba) e `imagenes: []`.
- Si no tiene texto (PDF escaneado), requiere `--out-dir` ya existente:
  renderiza hasta 3 páginas a PNG en ese directorio para que Lasso las lea
  con visión nativa, y devuelve `fuente="sin_texto"` con `"texto": null` y
  las rutas de los PNG generados. Sin `--out-dir`, error claro explicando
  que hace falta para renderizar.
- `"advertencias"` siempre está presente (lista vacía si no hay nada que
  avisar); junta las advertencias de zoom reducido/página omitida por
  dimensiones extremas del renderizado.

### `hash <ruta>`

`{"sha256": "<hex>"}`. SHA-256 del archivo completo, leído en bloques (no
carga el archivo entero en memoria).

### `extraer-campos --texto <archivo.txt o ->`

Parseo determinista (brief, parte C): **solo regex, sin LLM** -- el texto de
un comprobante es un DATO, nunca se interpreta como instrucción. Extrae los
campos que salen directo del texto de un comprobante, para que la pregunta
final no tenga que volver a pedirlos.

```json
{"monto": float|null, "fecha": "YYYY-MM-DD"|null, "medio_pago": str|null,
 "comercio": str|null, "descripcion": str|null, "nro_operacion": str|null,
 "titular_origen": str|null, "emisor": str|null,
 "formato_desconocido": bool, "pagado_por_sugerido": "JD"|"Pinki"|null}
```

**Formato soportado hoy: comprobante de transferencia de Mercado Pago**
(formato exacto, ver `tests/test_telegram_ingesta.py::TEXTO_COMPROBANTE_
MERCADOPAGO` para el texto de referencia -- fechas en castellano con día de
semana y mes en letras, montos con punto de miles y coma decimal opcional).
De ese formato se extrae: `monto`, `fecha` (ISO), `medio_pago="Transferencia"`,
`comercio` (titular de la cuenta destino), `descripcion` (`"Motivo: ..."`
solo si el motivo no es el genérico `"Varios"` que pone Mercado Pago por
default), `nro_operacion`, `titular_origen` (titular de la cuenta origen) y
`emisor` (`"Mercado Pago"`).

**Formato no reconocido:** todos los campos quedan en `null` y
`"formato_desconocido": true` -- nunca se inventa un valor a partir de un
texto que no matchea exactamente un formato soportado.

**`pagado_por_sugerido`:** si `titular_origen` matchea un titular mapeado en
`telegram_usuarios.json["titulares"]` (ver arriba), se propone la persona
mapeada -- pero es solo una SUGERENCIA; `pagado_por` sigue yendo a
`campos_faltantes` en `normalizar`, y `pregunta --con-comprobante` la
muestra para confirmar, nunca la asume. `null` si no hay mapeo o no
matchea.

### `normalizar --tipo gasto|ingreso --json <borrador.json o ->`

Recibe los campos que leyó Lasso (visión, `extraer-pdf` o `extraer-campos`)
y devuelve `{"borrador": {...}, "campos_faltantes": [...],
"defaults_aplicados": [...], "advertencias": [...], "pagado_por_sugerido":
"JD"|"Pinki"}` (esta última clave solo aparece si hay sugerencia -- ver
abajo; vive al nivel superior, NUNCA dentro de `borrador`, porque
`borrador` viaja tal cual como payload de `guardar` hacia la API, que
rechaza campos desconocidos). Nunca escribe nada.

**Entrada esperada:** `monto`, `fecha`, `comercio` o `descripcion`, `categoria`,
`subcategoria`; para gastos, `medio_pago`, `pagado_por`, `tipo_proporcion`,
`proporcion_jd`, `cuotas_total` y `titular_origen`; para ingresos, `persona`.
`telegram` puede aportar IDs de chat, usuario y mensaje. El medio de pago
Crédito o Débito y las cuotas conservan su significado, sin identificar
una tarjeta o banco. Las claves legacy de identificación se ignoran.

**Salida `borrador`:** usa el contrato de `POST /api/expenses/telegram` o
`POST /api/income/telegram`, con `descripcion_original` e IDs Telegram
validados. Nunca incluye identificación de tarjeta o banco.

**Validación tolerante:** categoría y subcategoría se resuelven contra
`GET /api/categories?tipo=` con `_slug` y alias simples. Los valores
no reconocidos generan error con opciones válidas.

**Defaults (siempre en `defaults_aplicados`, nunca en silencio):**

| Campo | Default | Condición |
| --- | --- | --- |
| `tipo_proporcion` | `"dinamico"` | Gasto, `tipo_proporcion` ausente -- para **cualquier** pagador (Común, JD o Pinki), no solo Común (el valor que acepta el dominio es `dinamico`, no `dinamica` -- ver `validaciones.TIPO_PROPORCION_VALIDOS` en `lab/validaciones.py`) |
| `cuotas_total` | `1` | Gasto, siempre que no venga explícito |
| `fecha` | hoy (ISO) | Siempre que falte -- además agrega una entrada en `advertencias` |

`cuotas_total` solo admite enteros de 1 a 120 y un monto con suficientes
centavos para todas las cuotas. La pregunta final muestra siempre el número
de cuotas, incluido el default 1, junto con el resto del borrador.

**`pagado_por` NUNCA tiene default** (Juan, 2026-10-25: "tenés que
preguntar siempre quién hizo el gasto, porque a lo mejor Pinki carga un
gasto hecho por JD"). Si no viene explícito en la entrada, siempre queda en
`campos_faltantes` -- sin excepción, aunque `telegram.user_id` sea un
usuario conocido (ese dato solo identifica quién CARGÓ el mensaje, nunca
quién pagó; queda en el borrador como `telegram_user_id`, no como
`pagado_por`). Dos formas de resolverlo sin preguntar en el chat:

1. **Texto explícito:** si Lasso ya extrajo `pagado_por` del mensaje (ej.
   "pagó JD", "lo pagó Regi", "fue común") y lo manda en la entrada de
   `normalizar`, se usa tal cual -- no es un default, es un dato explícito.
2. **Titular de comprobante mapeado:** si la entrada trae `titular_origen`
   (de `extraer-campos`) y matchea un titular en `telegram_usuarios.json
   ["titulares"]`, se propone en `pagado_por_sugerido` (al nivel superior
   del resultado, nunca dentro de `borrador`) -- pero SIGUE en
   `campos_faltantes`: la sugerencia se muestra para confirmar en `pregunta
   --con-comprobante`, nunca se asume sola.

`proporcion_jd` (gasto con `tipo_proporcion="custom"`) tiene que ser un
número finito entre 0 y 100 -- cualquier otro valor (fuera de rango, `NaN`/
infinito, string, bool) es un error explícito del CLI. `proporcion_pinki`
se deriva siempre como `100 - proporcion_jd`. El reparto siempre se muestra
en la pregunta de confirmación (`pregunta`, más abajo): `"Reparto: dinámico
(según sueldos del mes)"` o `"Reparto: X% JD / Y% Pinki"`.

**Coherencia `tipo_proporcion`/`proporcion_jd`:**

- `tipo_proporcion="custom"` **sin** `proporcion_jd`: no es un default
  inventado ni un borrador completo -- `proporcion_jd` va a
  `campos_faltantes`, y `pregunta` lo pide explícito (`"¿Qué % pone JD?"`).
- `tipo_proporcion="dinamico"` (explícito o por default) **con**
  `proporcion_jd`: el backend rechazaría ese borrador contradictorio
  (`validaciones.validar_expense`), así que el CLI la ignora de entrada
  -- no la incluye en el borrador -- y lo deja explícito en
  `advertencias`, nunca en silencio.

`medio_pago` **nunca** tiene default: si falta, va directo a
`campos_faltantes` (brief: "sin inventar").

**Ingreso con `categoria="Salario"`:** agrega la advertencia `"cambia la
proporción del mes."` (la proporción dinámica de gastos Común se recalcula
con los salarios del mes, ver `db.calcular_proporcion_mes`).

**Parseo de montos AR (`parse_monto_ar`, función aparte con tests propios en
`tests/test_telegram_ingesta.py::ParseMontoArTests`):** determinista, sin
heurísticas de IA. Formatos soportados: `"45.000"` (punto = miles),
`"45 mil"`, `"$45.000,50"` (coma = decimales, máximo 2 dígitos), `"45k"`. Un
formato no reconocido levanta error explícito -- nunca asume ni redondea a
lo que "parece" el monto.

- **Agrupación de miles validada:** si el entero tiene puntos separadores,
  tienen que agrupar de a 3 dígitos (`"1.500.000"` OK; `"1.2.3"` error). Sin
  puntos, cualquier cantidad de dígitos es válida (`"1500"` OK).
- **Validación final (igual para texto parseado y para `int`/`float` ya
  numéricos, incluido el passthrough):** finito (rechaza `NaN`/infinito),
  mayor a 0 (rechaza cero y negativos), como máximo 2 decimales, y no mayor
  al límite que acepta la API (`api.MAX_MONEY`/`api._valid_money` en
  `lab/api.py`, duplicado acá como `MONTO_MAXIMO`).
- **Enteros extremadamente grandes** (ej. `10**400`, que haría que
  `float()` levante `OverflowError` en vez de un error de rango normal):
  se comparan como `Decimal` contra `MONTO_MAXIMO` antes de convertir a
  `float`, y cualquier `OverflowError` remanente también se captura --
  siempre termina en el mismo `ValueError` de "supera el máximo permitido"
  que cualquier otro monto fuera de rango, nunca una traza sin capturar.

### `faltantes --tipo gasto|ingreso --json <borrador.json o ->`

`{"campos_faltantes": [...]}`. Acepta como entrada un borrador "pelado" o el
objeto completo `{"borrador": {...}, ...}` que devuelve `normalizar` (usa
la clave `"borrador"` si existe, si no trata todo el objeto como borrador).

Campos obligatorios por tipo:

- **Gasto:** `monto`, `fecha`, `categoria`, `medio_pago`, `pagado_por`.
- **Ingreso:** `monto`, `fecha`, `categoria`, `persona`.
- Un reparto `custom` requiere `proporcion_jd`; las cuotas siguen siendo
  independientes de la identificación de la tarjeta.

### `pregunta --tipo gasto|ingreso --json <salida-de-normalizar.json o -> [--con-comprobante]`

Arma una sola lista numerada con **todos** los campos faltantes. Si no falta
ninguno, muestra monto, categoría, descripción si existe, medio de pago,
pagador, reparto, cuotas y fecha, y cierra con `¿Subo así o cambio algo?`.
No consulta catálogos de tarjetas. Si recibe un borrador anterior con
`tarjeta`, `tarjeta_id` o `banco`, los oculta de la pregunta. Categorías
se consultan a la API para mostrar opciones reales.

**`--con-comprobante`** (equivalente: campo `"con_comprobante": true` en el
borrador o en el JSON de entrada -- brief, parte D, para un gasto cargado
desde un comprobante leído completo). Cambia el formato de la pregunta para
gasto: en vez de repetir todo lo que ya salió del comprobante, arranca con
un resumen de lo leído y solo pide lo mínimo que falta (en la práctica,
quién pagó y, si no se pudo inferir, la categoría):

```
Leí del comprobante: $27.000 · transferencia a Ignacio T. · 11/08
1) ¿Quién lo pagó? (JD / Pinki / Común)
2) ¿Categoría? (opciones: Hogar, Comida, Mascotas)
Reparto: dinámico (según sueldos del mes)
```

Si `pagado_por_sugerido` viene en la entrada (de `normalizar`, ver arriba),
la pregunta muestra la inferencia y exige respuesta explícita: «Veo que salió
de la cuenta de Juan/JD, ¿lo pagó JD?» o la equivalente para Regina/Pinki.
El remitente de Telegram y el titular del comprobante no son confirmación.
Sin campos faltantes, muestra también categoría y pagador junto al resumen,
el reparto y `"¿Subo así o cambio algo?"` para confirmar el borrador completo.

**Importante:** `con_comprobante`/`pagado_por_sugerido` son marcadores de
borrador EN PROGRESO -- antes de llamar a `guardar`, hay que sacarlos del
payload final (junto con setear el `pagado_por` real que confirmó el
usuario): la API rechaza campos desconocidos en `POST /api/expenses/
telegram`.

### `dedupe --hash H [--monto M] [--fecha F] [--comercio C] [--nro-operacion N]`

Proxy directo de `GET /api/comprobantes/dedupe` (ver `lab/README-api.md`).
`--nro-operacion` (brief, parte C): dedupe por número de operación bancaria
(ej. de un comprobante de Mercado Pago, ver `extraer-campos`) -- coincidencia
exacta, `"coincidencia": "operacion"`, más fuerte que la aproximada por
monto+fecha pero no tanto como el hash exacto del archivo.

### `guardar --tipo gasto|ingreso --json <borrador.json o -> [--comprobante <json>] --confirmado [--forzar-duplicado]`

**Único subcomando que escribe.** Reglas, en orden:

1. Exige `--confirmado`; si falta, error explícito, **sin llamar a la API**.
   El operador solo debe pasarlo después de mostrar el borrador completo con
   `pregunta` y recibir la confirmación explícita de Juan o Pinki. Confirmar
   solo la inferencia del titular o contestar un faltante no autoriza guardar.
2. Recalcula `campos_faltantes` sobre el borrador; si hay alguno, error
   explícito con la lista, **sin llamar a la API**.
3. Si viene `--comprobante` y no se pasó `--forzar-duplicado`, corre
   `dedupe` con `hash_archivo`/`monto_detectado`/`fecha_detectada`/
   `comercio_detectado`/`nro_operacion` del comprobante. Si hay duplicado
   (hash exacto, operación exacta, o aproximado), **no guarda nada** y
   devuelve `{"error": "...", "duplicado": true, "dedupe": {...}}` con el
   conflicto completo. `--forzar-duplicado` salta este chequeo (pero un
   hash o un `nro_operacion` **idénticos** siguen rechazados por la API,
   `409`, porque ambos tienen restricción `UNIQUE`/índice único en
   `comprobantes_telegram` -- forzar solo tiene efecto real ante una
   coincidencia **aproximada** con hash y operación distintos).
4. Llama a `POST /api/expenses/telegram` o `POST /api/income/telegram` con
   el borrador (y el comprobante, si vino). Devuelve `{"id": N, "ids":
   [...], "avisos_credito_nuevos": [...]}` (gasto; `"ids"` tiene más de un
   elemento si hay cuotas) o `{"id": N, "avisos_credito_nuevos": []}`
   (ingreso).

### `avisos-pendientes`

Proxy de `GET /api/avisos-credito/pendientes`.

### `marcar-avisos --items <json>`

`--items` es una ruta a una lista JSON `[{"mes": "YYYY-MM", "umbral": N},
...]` (o `-` para stdin). Proxy de `POST /api/avisos-credito/marcar-
enviados`.

### `mensaje-aviso --json <lista-o-objeto.json>`

`{"mensaje": "..."}`. Arma el texto para el grupo, ej.:

```
🚨 Los gastos en crédito de octubre superaron $200.000 (van $212.350)
```

Con el nombre del mes en castellano. Acepta como entrada una lista de
avisos (`[{"mes", "umbral", "total"|"total_al_detectar"}, ...]`, cualquiera
de las dos formas de respuesta de la API -- `avisos_credito_nuevos` usa
`total`, `avisos_credito` de `/pendientes` usa `total_al_detectar`), o un
objeto con esa lista bajo `"avisos_credito"`, `"avisos_credito_nuevos"` o
`"nuevos"`. Si se cruzaron varios umbrales de un mismo mes, arma **un solo
mensaje con el máximo** (`DECISIONES.md` punto 8). Espera que todos los
items sean del mismo mes -- si no, error explícito (llamar una vez por mes).

### `borrador get|set|clear --chat C [--usuario U] [--json <datos.json o ->]`

Cliente de `GET`/`PUT`/`DELETE /api/telegram/borrador` (rutas agregadas en
`lab/api.py` para esta tarea, ver `lab/README-api.md`). `set` requiere
`--json` con al menos `{"estado": "..."}` (más `campo_pendiente`,
`payload_parcial`, `mensaje_original`, `intent_detectado` opcionales).
`--usuario` es opcional: dos usuarios del mismo `--chat` tienen borradores
independientes (ver migración de `estado_conversacional` en
`lab/README-api.md`); omitirlo opera sobre el borrador "sin usuario
identificado" de ese chat.

## Tests

La suite sintética en `lab/tests/test_telegram_ingesta.py` y
`lab/tests/test_telegram_api.py` cubre normalización, lista consolidada de
faltantes, confirmación explícita, crédito/débito sin identificación,
cuotas y compatibilidad de históricos. En esta corrida no se ejecutó.
