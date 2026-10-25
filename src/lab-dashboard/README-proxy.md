# Proxy LIFE para API del VPS (candidato local)

Este candidato protege `/api/*` con la cookie de sesión `dashboard_session` existente. La autoridad de rutas es `contrato-api-reference.md` y `api-reference.py`. No se validó una URL real del VPS ni se realizó un despliegue.

## Configuración e integración

| Variable | Uso |
| --- | --- |
| `DASHBOARD_PASSWORD` | Contraseña del gate actual y clave de firma de la cookie. |
| `VPS_API_BASE_URL` | URL HTTPS absoluta configurada **sólo en servidor**. Debe tener hostname DNS, sin credenciales, query ni fragmento. Puede incluir un prefijo de ruta, por ejemplo `https://api.example.test/private`. |
| `VPS_INTERNAL_SECRET` | Credencial interna enviada sólo como `X-Internal-Proxy-Secret`. Debe poder representarse sin cambios en un header HTTP. |
| `VPS_PROXY_TIMEOUT_MS` | Opcional. Límite total desde antes de leer el body entrante hasta terminar la respuesta upstream: 10.000 ms por defecto, máximo 60.000 ms. Un valor inválido usa el defecto. |

Las variables del VPS no provienen de headers, cookies, query ni body del navegador. Una configuración ausente o inválida devuelve JSON `503` sin registrar ni reflejar sus valores. Si falta `DASHBOARD_PASSWORD`, se conserva el error de configuración del gate existente.

La continuación al recurso estático llama a `next()` de `@vercel/functions`, según la [API de Routing Middleware de Vercel](https://vercel.com/docs/routing-middleware/api#continuing-the-routing-middleware-chain). `package.json` declara `@vercel/functions` en la versión exacta `3.10.1`, cuyo prerrequisito es Node.js `>=20` según la consulta npm del coordinador. En este candidato no se instalaron dependencias ni se generó un lockfile; el coordinador hará ese paso. La prueba local inyecta una continuación simulada para verificar el gate. El build y runtime de Vercel, y el smoke test remoto de login, cookie, logout, asset, `next()` y endpoints siguen sin probarse.

## Contrato de rutas

| Ruta | Métodos | Query admitida |
| --- | --- | --- |
| `/api/health` | `GET` | Ninguna |
| `/api/expenses` | `GET`, `POST` | `month=YYYY-MM` opcional sólo en `GET` |
| `/api/expenses/:id` | `DELETE` | Ninguna |
| `/api/income` | `GET`, `POST` | Ninguna |
| `/api/income/:id` | `PATCH`, `DELETE` | Ninguna |
| `/api/inventory` | `GET`, `POST` | Ninguna |
| `/api/inventory/:id` | `PATCH`, `DELETE` | Ninguna |
| `/api/fixed` | `GET`, `POST` | `dateISO=YYYY-MM-DD` opcional sólo en `GET` |
| `/api/fixed/versions` | `GET` | Ninguna |
| `/api/fixed/range` | `GET` | `fromISO` y `toISO` obligatorias, fechas `YYYY-MM-DD` |
| `/api/fixed/:id/historial` | `GET` | Ninguna |
| `/api/fixed/:id` | `PATCH`, `DELETE` | Ninguna |
| `/api/summary` | `GET` | `month=YYYY-MM` opcional |
| `/api/categories` | `GET` | `tipo` opcional en el proxy, debe ser `Gasto`, `Ingreso` o `Inversión` si está presente |

`:id` es un entero decimal positivo. No se admiten IDs de texto como `F-1`, aliases en español, parámetros desconocidos ni parámetros repetidos. La query permitida se conserva en la URL upstream sin traducir nombres. Una ruta desconocida devuelve `404`; un método no admitido sobre una ruta conocida devuelve `405` con `Allow`; una query inválida devuelve `400`. La API real valida el contenido de los JSON y los campos de dominio.

El allowlist de `/api/inventory` y `/api/inventory/:id` en `middleware.js` es por **ruta y método**, no por campo del body: el proxy reenvía el JSON entrante sin inspeccionar sus claves (ver "Límites y seguridad" — solo revisa tamaño, forma JSON/UTF-8 y, en la respuesta upstream, que no se filtren secretos). Por eso los seis campos de paridad con el legacy agregados en `lab/db.py`/`lab/api.py` (t_0e38e74e: `precio_ars`, `cotizacion_usd_compra`, `precio_usd_compra`, `proporcion_jd`, `precio_venta_estimado_usd`, `estado` — mapeo completo y validaciones en `lab/README-api.md`) viajan transparentes a través de este proxy sin requerir ningún cambio en `middleware.js` ni en su allowlist de rutas/métodos/query.

La cookie firmada y vigente se exige tanto para lecturas como para escrituras. Sin sesión válida, `/api/*` responde `401` JSON. Si una lectura trae `Origin`, debe coincidir exactamente con el origen de `request.url`. Para `POST`, `PATCH` y `DELETE`, ese `Origin` es obligatorio. `Referer`, `Host` y headers forwarded no sustituyen esa comprobación.

El proxy construye los headers salientes desde cero: `Content-Type: application/json` cuando hay cuerpo y `X-Internal-Proxy-Secret` desde el entorno del servidor. Nunca reenvía `Authorization`, cookies, secretos o identidad aportados por el cliente. La sesión compartida no identifica a JD ni a Pinki ante la API; ésta usa un actor fijo no verificado.

`/api/categories` usa el mismo mecanismo de allowlist de query que `month` en `/api/expenses`: el proxy no exige `tipo` (igual que `month` no es obligatorio ahí), pero si viene, valida que sea exactamente `Gasto`, `Ingreso` o `Inversión` antes de reenviarlo; cualquier otro valor o parámetro desconocido devuelve `400` sin llegar a la API real. La obligatoriedad de `tipo` (ausente → `422`) es responsabilidad exclusiva de la API detrás del proxy.

## PWA y atajos de iPhone (S5, t_a60a2f67)

- **Manifest e íconos son públicos:** `/manifest.webmanifest`, `/icons/icon-180.png`, `/icons/icon-192.png` y `/icons/icon-512.png` quedan fuera del gate de sesión — son las rutas exactas que Safari necesita leer para el prompt de "Agregar a inicio" **antes** de que exista una cookie de sesión, y no llevan datos propios del dashboard. El chequeo es por ruta exacta y sólo para `GET`: ningún otro archivo bajo `/icons/` queda expuesto, y un `POST` a esas mismas rutas sigue cayendo en el gate normal (actualmente no hay handler para eso, así que termina en 404/405 del runtime de Vercel una vez pasado `next()`, nunca en la app).
- **El destino se preserva a través del login:** si `GET /` llega sin sesión válida con exactamente `?accion=<gasto|ingreso|fijo|fijos>` (una sola query, ese valor conocido), el redirect a `/login` incluye `?next=/%3Faccion%3D...`. `login.html` reenvía ese `next` como query del propio `POST /login` (nunca en el body del form) vía un pequeño script inline. Tras validar la contraseña, `middleware.js` vuelve a validar `next` contra el mismo formato exacto (`isAllowedNextTarget`) antes de usarlo como `Location` — así un `next` forjado a mano (otro dominio, `//host` relativo-a-protocolo, otro path, query extra, o un `accion` desconocido) cae siempre a `/`, nunca a un destino arbitrario. Una contraseña incorrecta conserva el `next` validado en el redirect de vuelta a `/login?error=1`, para no perder el destino en el segundo intento.
- **La cookie larga sigue valiendo para los Atajos, vía Safari:** `dashboard_session` se emite con `SameSite=Lax`, que permite que viaje en la navegación de nivel superior que abre "Abrir URL" de un Atajo (es exactamente el mismo tipo de navegación que seguir un link, no una llamada `fetch`/XHR de otro origen). La acción "Abrir URL" de Atajos abre siempre en **Safari**, nunca en la web app instalada ("Agregar a inicio") — y, según documenta Apple, la web app instalada y Safari tienen almacenamiento de cookies **separado** para el mismo origen. Por eso la sesión que habilita los Atajos es la que se inicia en Safari (90 días con "recordarme"), no la de la app instalada; si además se usa el ícono de LIFE desde la pantalla de inicio, esa es una sesión aparte que se inicia una vez dentro de la app instalada. Al ser la cookie `Secure` y el sitio servirse por HTTPS en Vercel, no hace falta ningún cambio de atributos de cookie para que cada una de esas dos sesiones dure 90 días por su lado. No se verificó esto en un iPhone real en esta corrida — queda para el smoke test del coordinador.
- No se agregó un service worker. Si se agrega uno más adelante, no debe cachear `/api/*` ni ninguna respuesta con datos: su único rol admisible sería servir el shell estático para que el ícono abra algo incluso sin red, nunca ocultar que una escritura falló.

## Límites y seguridad

- El body entrante tiene un máximo de **64 KiB**, medido en bytes del stream aunque `Content-Length` falte o mienta. Un exceso devuelve `413`; JSON o UTF-8 inválido devuelve `400`.
- La respuesta upstream tiene un máximo de **1 MiB** y debe ser JSON válido, salvo `204` sin cuerpo. Se recorren las claves y strings del JSON **decodificado**, incluso en objetos y arrays anidados, antes de serializar la respuesta. Cualquier reflejo del secreto interno, URL base u origen upstream devuelve `502` constante.
- La lectura del body entrante, el fetch y la lectura de respuesta comparten un solo timeout. Al vencer, se aborta el fetch, se cancela el reader activo y se devuelve `504`. Los bodies upstream rechazados por redirect, status o tipo de contenido, y los que quedan pendientes tras un error, se cancelan sin esperar una promesa de cancelación que pueda quedar colgada o rechazar. La cancelación se intenta sin bloquear la respuesta; su finalización depende del stream/runtime.
- El fetch usa `redirect: 'manual'`; cualquier `3xx` devuelve `502`. No se copian headers upstream, incluidos `Set-Cookie` y `Location`. Todas las respuestas API usan `Cache-Control: no-store`.
- El destino se arma exclusivamente con la URL de servidor validada y la ruta permitida. Se exige que el hostname final sea exactamente el hostname configurado. Se rechazan IP literales, localhost y nombres internos conocidos. Un hostname DNS público puede resolver o cambiar a una dirección privada: este runtime no demuestra ni bloquea esa resolución. La selección de un destino real confiable y los controles DNS/egress contra redes privadas son tareas de integración e infraestructura pendientes; no se afirma seguridad remota sin ellos.

Las pruebas en `tests/proxy.test.mjs` usan `node:test`, Web APIs de Node y `fetch` simulado, sin llamadas a red. Incluyen el `DELETE /api/income/:id` agregado en t_ce790609 (permitido y forwardeado) y la verificación de que `DELETE /api/income` (sin id) sigue devolviendo `405`/`404` según corresponda. También cubren `/api/categories` (t_ce790609, QA de Juan ronda 2): `GET` con `tipo=Gasto` permitido y forwardeado, cualquier otro método rechazado con `405`/`Allow: GET`, y query desconocida, repetida o con un valor de `tipo` fuera de las tres opciones rechazada con `400 invalid_query` antes de llegar a la API real. S5 (t_a60a2f67) agrega: las cuatro rutas públicas de manifest/íconos (bypass total del gate, incluso sin `DASHBOARD_PASSWORD`, sólo `GET` y sólo esas rutas exactas), la preservación de `?accion=` conocido a través de `/login` (incluida la ausencia de `next` cuando el path, la cantidad de parámetros o el valor de `accion` no son exactamente los admitidos), y el redirect final de `POST /login` — éxito, contraseña incorrecta, y una lista de valores de `next` forjados (otro dominio, `//host`, otro path, query extra, `accion` desconocido, mayúsculas) que deben caer siempre a `/`. El comando es `node --test tests/proxy.test.mjs` (desde `src/lab-dashboard/`). Esta corrida no tuvo shell disponible para ejecutarlas; el coordinador debe correrlas antes de aceptar el candidato. Tampoco hubo smoke test remoto ni despliegue.
