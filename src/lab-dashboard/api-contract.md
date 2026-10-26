# Contrato API — `/api/*` consumido por el dashboard

> **Estado: NO desplegado.** Este documento describe el contrato ya
> implementado en `api.py` (ver `README-api.md`) y expuesto al navegador a
> través de `middleware.js` (ver `README-proxy.md`). Hoy no hay ningún VPS
> real detrás de `VPS_API_BASE_URL`, ni despliegue de Vercel, ni base
> `data/lasso.sqlite` productiva: `api.py` corre localmente contra una base
> SQLite efímera (archivo temporal o `:memory:`) para tests, y el proxy no
> tiene `VPS_API_BASE_URL`/`VPS_INTERNAL_SECRET` configurados en ningún
> entorno real. Este archivo NO inventa una URL de VPS ni un secreto: esos
> valores los define el operador en el entorno de Vercel al integrar.

## Dos capas de autenticación

1. **Navegador → proxy (`middleware.js`)**: cookie de sesión firmada
   `dashboard_session` (gate existente, `DASHBOARD_PASSWORD`). Sin cookie
   válida, `/api/*` responde `401` JSON antes de llegar al proxy. Para
   `POST`/`PATCH`/`DELETE` el header `Origin` es obligatorio y debe
   coincidir exactamente con el origen de la request.
2. **Proxy → API (`api.py`)**: el proxy agrega `X-Internal-Proxy-Secret`
   (desde `VPS_INTERNAL_SECRET`, solo variable de servidor) a cada request
   reenviada a `VPS_API_BASE_URL`. El navegador nunca ve ni envía este
   secreto. `api.py` compara ese header en tiempo constante; sin él, o
   incorrecto, responde `401` (incluso en `/api/health`).

El dashboard (`app.js`) solo conoce la primera capa: llama a rutas relativas
(`/api/expenses`, `/api/income`, `/api/fixed`, `/api/fixed/versions`,
`/api/summary`, `/api/health`) con `credentials: 'same-origin'`. No conoce
`VPS_API_BASE_URL` ni el secreto interno.

## Convenciones generales

- Todos los request/response bodies son JSON
  (`application/json; charset=utf-8`), con `Cache-Control: no-store`.
- Nombres de campo idénticos a las columnas expuestas por `db.py` (no se
  traducen ni se camelCasean).
- Claves JSON repetidas, campos/parámetros desconocidos, parámetros
  repetidos, `NaN`, infinito y booleanos en campos numéricos se rechazan
  con `400`.
- `actor`, `confirmado`, `origen` y otros campos de control no se aceptan
  del cliente: la API los fija internamente (`confirmado=True` en altas).
  Las escrituras auditadas quedan con actor `sesion_compartida:no_verificado`
  — la sesión del dashboard no identifica a JD ni a Pinki ante la API.
- Códigos: `400` entrada inválida, `401` autenticación (cookie o secreto
  interno ausente/incorrecto), `404` recurso inexistente, `405` método no
  admitido (con header `Allow`), `409` conflicto de estado/SQLite ocupado,
  `413` cuerpo de más de 64 KiB, `422` si datos legacy o acumulados impiden
  calcular una respuesta fiable, `500`/`502`/`504` errores de servidor o
  del proxy upstream (ver `README-proxy.md`).

## Rutas (contrato completo en `README-api.md`)

| Método y ruta | Entrada | Respuesta exitosa |
| --- | --- | --- |
| `GET /api/health` | Sin parámetros | `{"ok":true,"capabilities":["expenses","income","fixed"],"mode":"live"}` |
| `GET /api/expenses?month=YYYY-MM` | `month` opcional | `{"expenses":[...]}`; excluye bajas lógicas |
| `POST /api/expenses` | `fecha`, `monto`, `moneda`, `categoria`, `subcategoria`, `medio_pago`, `pagado_por`, `descripcion_original`, `tarjeta_id`, `tipo_proporcion`, `proporcion_jd`, `proporcion_pinki`, `cuotas_total` | `201 {"expenses":[...]}`; una fila por cuota |
| `DELETE /api/expenses/:id` | Sin cuerpo | `{"deleted":true,"id":N}` |
| `POST /api/expenses/:id/saldar` | Sin cuerpo | `{"expense":{...}}`; `404` si no existe, `409` si ya está borrado, ya saldado, o `pagado_por='Común'` |
| `GET /api/income` | Sin parámetros | `{"income":[...]}` |
| `POST /api/income` | `fecha`, `monto`, `moneda`, `categoria`, `persona`, `descripcion_original` | `201 {"income":{...}}` |
| `PATCH /api/income/:id` | Subconjunto no vacío de los campos del alta | `{"income":{...}}` |
| `GET /api/fixed?dateISO=YYYY-MM-DD` | `dateISO` opcional | `{"fixed":[...]}`; una versión activa por serie |
| `GET /api/fixed/versions` | Sin parámetros | `{"versions":[...]}`; todas las versiones |
| `GET /api/fixed/range?fromISO=...&toISO=...` | Dos fechas obligatorias | `{"range":[{"fijo_grupo_id":N,"tramos":[...]}]}` |
| `GET /api/fixed/:id/historial` | `id` de cualquier versión | `{"historial":[...]}` |
| `POST /api/fixed` | `nombre`, `monto_estimado`, `periodicidad`, `responsable`, `vigente_desde` obligatorios; `tipo_proporcion`/`proporcion_jd` según tabla de reparto | `201 {"fixed":{...}}` |
| `PATCH /api/fixed/:id` | `vigente_desde` obligatorio + cambios | `{"fixed":{...}}` con id de la nueva versión |
| `DELETE /api/fixed/:id` | `{"fecha_baja":"YYYY-MM-DD"}` | `{"fixed":{...}}` con versión inactiva nueva |
| `GET /api/summary?month=YYYY-MM` | `month` opcional | Con mes: objeto resumen; sin mes: `{"months":[...]}` |

No existe `DELETE /api/income/:id`. `:id` es un entero decimal positivo (no
se admiten ids tipo `F-1`).

### Reparto de gastos fijos (regla vigente, ver `db.resolve_fixed_split`)

| Responsable | Entrada admitida | Valores guardados y devueltos |
| --- | --- | --- |
| `Común`, dinámico | Omitir ambos campos, o `"tipo_proporcion":"dinamica"` sin `proporcion_jd` (o `null`) | `"tipo_proporcion":"dinamica","proporcion_jd":null` |
| `Común`, manual | `"tipo_proporcion":"custom","proporcion_jd":N` (`0..100`) | `"tipo_proporcion":"custom","proporcion_jd":N` |
| `JD` | Omitir los campos de reparto o enviarlos como `null` | `"tipo_proporcion":null,"proporcion_jd":100` |
| `Pinki` | Omitir los campos de reparto o enviarlos como `null` | `"tipo_proporcion":null,"proporcion_jd":0` |

**No se aceptan valores de reparto explícitos para un responsable
personal** (`JD`/`Pinki`): es redundante con el 100/0 implícito y la API
responde `400` si se envían. Ver punto 2 de `INTEGRACION.md` para el
ajuste equivalente en `migrar_datos_reales.py`.

## Query permitida y rutas vía proxy

El proxy (`middleware.js`) solo reenvía la query documentada en
`README-proxy.md` por ruta (p.ej. `month` solo en `GET /api/expenses` y
`GET /api/summary`, `dateISO` solo en `GET /api/fixed`, `fromISO`/`toISO`
obligatorias en `GET /api/fixed/range`). Una query no listada devuelve
`400` antes de llegar a `api.py`.

## Fuera de alcance de este contrato

- El valor real de `VPS_API_BASE_URL` / `VPS_INTERNAL_SECRET` — los define
  el operador en Vercel, nunca este repositorio.
- Activación de infraestructura (VPS, deploy de Vercel) y el smoke test
  remoto de login/cookie/logout/`next()`/endpoints — pendientes, ver
  `INTEGRACION.md`.
- Endpoints no listados en la tabla de rutas (no hay más superficie que la
  que exponen `api.py` y `middleware.js` hoy).
