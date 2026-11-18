# Ingesta de recetas por Telegram — candidato LAB

Para guardar, mandá un mensaje nuevo de texto en el DM de Lasso. La primera línea tiene que ser exacta; debajo va la receta libre:

```text
Guardá esta receta:
Sopa. Ingrediente: sal a gusto. Paso: mezclar.
```

El modelo sólo extrae título, ingredientes y pasos del cuerpo de ese mensaje; no completa con el historial ni inventa datos. Una cantidad o unidad no informada queda en `null`. Si falta una sección, el tool pide reenviar la receta completa en un nuevo mensaje con el mismo encabezado. Consultas, reenvíos, respuestas a otro mensaje, citas, ediciones, adjuntos y transcripciones no autorizan escrituras. Un mensaje que el gateway transforma o concatena tampoco queda autorizado: volvé a enviarlo solo y como texto plano.

```json
{"accion":"guardar","receta":{"titulo":"Sopa","ingredientes":[{"nombre":"Sal","cantidad":null,"unidad":"a gusto"}],"pasos":["Mezclar."]}}
```

`pre_gateway_dispatch` observa el `Message` crudo sin autorizar nada. Sólo `post_gateway_admission` habilita la operación si corresponde al mismo evento y tarea de ingreso, tras la autorización normal de Hermes. El tool exige la identidad del turno (DM, hilo, sesión e ID de mensaje), la misma acción y un permiso de un uso que vence al terminar el turno o a los dos minutos. Ni los argumentos del modelo ni variables de entorno de sesión reemplazan ese permiso. El único write es `POST /api/recetas`; la clave `telegram:lasso:<chat>:<mensaje>` conserva la idempotencia.

Ante `duplicada`, el tool devuelve una instrucción `Confirmá duplicado: <código>`. El usuario debe enviar esa línea exacta, sola y en un mensaje posterior del mismo DM/hilo/sesión. No sirve un «sí» ni un código provisto por el modelo. El código dura diez minutos, corresponde sólo a la propuesta vigente y se usa el payload original. Si reiniciás el proceso, hay que volver a pedir el guardado. `guardada` devuelve el registro confirmado por la API con ingredientes y pasos.

## Validación aislada y futura activación

Desde la raíz de LIFE, prepará un directorio de plugin de prueba (no el perfil activo):

```sh
scratch="$(mktemp -d "${TMPDIR:?}/lasso-recetas-plugin.XXXXXX")"
dest="$scratch/plugins/lasso-recetas"
mkdir -p "$dest"
cp lab/hermes/lasso-recetas/{__init__.py,plugin.yaml} lab/{telegram_recetas.py,telegram_ingesta.py} "$dest/"
HERMES_HOME="$scratch" hermes plugins validate "$dest"
python -m pytest lab/tests/test_telegram_recetas.py -q
```

Para un piloto aprobado, montá los mismos cuatro archivos en un perfil de prueba aislado cuya identidad sea `lasso`. Configurá `LASSO_RECETAS_API_BASE` con un origen HTTP loopback y puerto explícito de una **API candidata con SQLite de prueba** y `LASSO_RECETAS_API_SECRET_FILE` con la ruta privada (0600/0400) de su secreto de prueba. No hay fallback a gastos. No apuntes al puerto ni al secreto de producción. Este candidato requiere gateway dedicado (sin multiplexado) y ejecución `in_process`: necesita el `Message` crudo y contexto local sin fallback (interfaces internas del runtime). No reduzcas un aislamiento `host` existente para activarlo. `plugins validate` valida el empaquetado, no la entrega de identidad. Revalidá con cada cambio de runtime que ambos hooks corran en la misma tarea y que el ejecutor conserve el contexto hasta el tool. Antes de aprobar el piloto, comprobá DM autorizado, otro perfil/grupo rechazado, ausencia de mutaciones en gastos y lectura posterior de las recetas sintéticas. No crees otro bot ni arranques un segundo poller con el token de Lasso.
