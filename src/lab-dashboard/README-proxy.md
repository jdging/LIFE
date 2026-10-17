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
| `/api/income/:id` | `PATCH` | Ninguna |
| `/api/fixed` | `GET`, `POST` | `dateISO=YYYY-MM-DD` opcional sólo en `GET` |
| `/api/fixed/versions` | `GET` | Ninguna |
| `/api/fixed/range` | `GET` | `fromISO` y `toISO` obligatorias, fechas `YYYY-MM-DD` |
| `/api/fixed/:id/historial` | `GET` | Ninguna |
| `/api/fixed/:id` | `PATCH`, `DELETE` | Ninguna |
| `/api/summary` | `GET` | `month=YYYY-MM` opcional |

`:id` es un entero decimal positivo. No se admiten IDs de texto como `F-1`, aliases en español, parámetros desconocidos ni parámetros repetidos. La query permitida se conserva en la URL upstream sin traducir nombres. Una ruta desconocida devuelve `404`; un método no admitido sobre una ruta conocida devuelve `405` con `Allow`; una query inválida devuelve `400`. La API real valida el contenido de los JSON y los campos de dominio.

La cookie firmada y vigente se exige tanto para lecturas como para escrituras. Sin sesión válida, `/api/*` responde `401` JSON. Si una lectura trae `Origin`, debe coincidir exactamente con el origen de `request.url`. Para `POST`, `PATCH` y `DELETE`, ese `Origin` es obligatorio. `Referer`, `Host` y headers forwarded no sustituyen esa comprobación.

El proxy construye los headers salientes desde cero: `Content-Type: application/json` cuando hay cuerpo y `X-Internal-Proxy-Secret` desde el entorno del servidor. Nunca reenvía `Authorization`, cookies, secretos o identidad aportados por el cliente. La sesión compartida no identifica a JD ni a Pinki ante la API; ésta usa un actor fijo no verificado.

## Límites y seguridad

- El body entrante tiene un máximo de **64 KiB**, medido en bytes del stream aunque `Content-Length` falte o mienta. Un exceso devuelve `413`; JSON o UTF-8 inválido devuelve `400`.
- La respuesta upstream tiene un máximo de **1 MiB** y debe ser JSON válido, salvo `204` sin cuerpo. Se recorren las claves y strings del JSON **decodificado**, incluso en objetos y arrays anidados, antes de serializar la respuesta. Cualquier reflejo del secreto interno, URL base u origen upstream devuelve `502` constante.
- La lectura del body entrante, el fetch y la lectura de respuesta comparten un solo timeout. Al vencer, se aborta el fetch, se cancela el reader activo y se devuelve `504`. Los bodies upstream rechazados por redirect, status o tipo de contenido, y los que quedan pendientes tras un error, se cancelan sin esperar una promesa de cancelación que pueda quedar colgada o rechazar. La cancelación se intenta sin bloquear la respuesta; su finalización depende del stream/runtime.
- El fetch usa `redirect: 'manual'`; cualquier `3xx` devuelve `502`. No se copian headers upstream, incluidos `Set-Cookie` y `Location`. Todas las respuestas API usan `Cache-Control: no-store`.
- El destino se arma exclusivamente con la URL de servidor validada y la ruta permitida. Se exige que el hostname final sea exactamente el hostname configurado. Se rechazan IP literales, localhost y nombres internos conocidos. Un hostname DNS público puede resolver o cambiar a una dirección privada: este runtime no demuestra ni bloquea esa resolución. La selección de un destino real confiable y los controles DNS/egress contra redes privadas son tareas de integración e infraestructura pendientes; no se afirma seguridad remota sin ellos.

Las pruebas en `tests/proxy.test.mjs` usan `node:test`, Web APIs de Node y `fetch` simulado, sin llamadas a red. Se agregaron casos para bodies abiertos rechazados y cancelaciones que rechazan o no terminan. **No se ejecutaron en esta corrida por instrucción expresa**; los 14 casos anteriores también quedaron sin reejecutar aquí. Tampoco hubo smoke test remoto ni despliegue.
