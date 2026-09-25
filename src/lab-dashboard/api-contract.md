# Contrato API — Finanzas write endpoints (`/api/expenses`, `/api/fixed/:id`)

> **Estado: NO desplegado.** Este documento es un contrato de diseño para
> cuando exista infraestructura VPS aprobada (Opción A: puerto HTTPS propio
> en el VPS, u Opción B: poller que consuma una cola). Hoy no hay ningún
> proceso escuchando estas rutas ni ningún request real llega a
> `data/lasso.sqlite`. `middleware.js` ya protege el prefijo `/api/` con
> 401 JSON si falta/venció la sesión, pero eso es autenticación de borde —
> no implica que el backend exista.

## Convenciones generales

- Todos los request/response bodies son JSON (`content-type:
  application/json; charset=utf-8`).
- Autenticación: cookie `dashboard_session` (ver `middleware.js`). Sin
  sesión válida → `401 {"error":"unauthorized"}` antes de llegar al
  handler.
- Nombres de campo idénticos a las columnas expuestas por `db.py` (no se
  traducen ni se camelCasean).
- Los errores de validación devuelven `400` con
  `{"error": "validation_failed", "details": ["mensaje 1", "mensaje 2"]}`
  — `details` es la lista tal cual la devuelven `validar_expense` /
  `validar_fixed_update` en `validaciones.py`.

## `POST /api/expenses` — alta de gasto

Inserta un gasto (equivalente a `db.insert_gasto` / `insert_gasto_con_cuotas`
si `cuotas_total > 1`).

### Request body

```json
{
  "fecha": "2026-09-25",
  "monto": 15000.5,
  "moneda": "ARS",
  "categoria": "Comida",
  "subcategoria": "Supermercado",
  "medio_pago": "Crédito",
  "pagado_por": "JD",
  "descripcion_original": "Coto del mes",
  "tarjeta_id": "TC1",
  "tipo_proporcion": "dinamico",
  "proporcion_jd": null,
  "proporcion_pinki": null,
  "cuotas_total": 1,
  "cuota_nro": 1
}
```

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `fecha` | string `YYYY-MM-DD` | No | Default: hoy (UTC) si se omite. |
| `monto` | number | Sí | Debe ser `> 0`. |
| `moneda` | string | No | Default `"ARS"`. |
| `categoria` | string | Sí | — |
| `subcategoria` | string \| null | No | — |
| `medio_pago` | string | No | — |
| `pagado_por` | string | No | `"Común"` \| `"JD"` \| `"Pinki"`. Default `"Común"`. |
| `descripcion_original` | string \| null | No | — |
| `tarjeta_id` | string \| null | No | FK a `tarjetas.id`. |
| `tipo_proporcion` | string | No | `"dinamico"` (default) \| `"custom"`. |
| `proporcion_jd` | number \| null | Condicional | Obligatorio si `tipo_proporcion="custom"`; debe venir `null`/ausente si `"dinamico"`. |
| `proporcion_pinki` | number \| null | Condicional | Igual regla que `proporcion_jd`. |
| `cuotas_total` | integer | No | Default `1`. Debe ser `>= 1`. |
| `cuota_nro` | integer | No | Default `1`. Debe ser `>= 1` y `<= cuotas_total`. |

### Validaciones (ver `validaciones.py::validar_expense`)

- `monto > 0` (rechaza `0`, negativos, no-numérico).
- `categoria` no vacía.
- `pagado_por` ∈ `{Común, JD, Pinki}` si viene informado.
- `tipo_proporcion` ∈ `{dinamico, custom}`.
- Si `tipo_proporcion = "custom"`: `proporcion_jd` y `proporcion_pinki`
  son obligatorias, numéricas, y `abs((proporcion_jd + proporcion_pinki)
  - 100) <= 0.01`.
- Si `tipo_proporcion = "dinamico"`: `proporcion_jd` y `proporcion_pinki`
  deben venir `null`/ausentes (mismo criterio que `db.insert_gasto`).
- `cuotas_total >= 1`.
- `cuota_nro >= 1` y `cuota_nro <= cuotas_total`.

### Response

**201 Created**

```json
{ "id": 42 }
```

Si `cuotas_total > 1`, el servidor expande las cuotas internamente
(equivalente a `insert_gasto_con_cuotas`) y responde con la lista de ids
generados:

```json
{ "ids": [42, 43, 44] }
```

**400 Bad Request** — validación falló (ver formato general arriba).

**401 Unauthorized** — sin cookie de sesión válida.

## `DELETE /api/expenses/:id` — baja lógica

Marca un gasto como borrado (soft delete). Requiere la migración descripta
en `migracion_soft_delete.sql` (columnas `deleted_at`/`deleted_by` en
`gastos`) — **no aplicada todavía**, ver ese archivo.

### Request

- `:id` — entero, id de `gastos.id`.
- Body opcional:

```json
{ "actor": "JD" }
```

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `actor` | string | No | Quién ejecuta el borrado, para `deleted_by` / `auditoria.actor`. Default `"desconocido"` si se omite. |

### Response

**200 OK**

```json
{ "id": 42, "deleted_at": "2026-09-25T14:30:00+00:00" }
```

**404 Not Found** — `{"error": "not_found"}` si el id no existe o ya
estaba borrado.

**401 Unauthorized** — sin cookie de sesión válida.

## `PATCH /api/fixed/:id` — actualizar monto de un gasto fijo

Equivalente a `db.actualizar_monto_fijo(conn, id, monto_nuevo)`.

### Request body

```json
{ "monto_estimado": 85000.0 }
```

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `monto_estimado` | number | Sí | Debe ser `> 0`. |

Nota: el contrato solo cubre actualización de monto (alcance del brief).
No cubre cambios de `responsable`, `periodicidad` ni otros campos de
`gastos_fijos` — eso queda fuera de esta iteración.

### Validaciones (ver `validaciones.py::validar_fixed_update`)

- `monto_estimado` presente, numérico y `> 0`.

### Response

**200 OK**

```json
{ "id": 7, "monto_estimado": 85000.0 }
```

**404 Not Found** — `{"error": "not_found"}` si el id de `gastos_fijos` no
existe.

**400 Bad Request** — validación falló.

**401 Unauthorized** — sin cookie de sesión válida.

## Códigos de error — resumen

| Código | `error` | Cuándo |
|---|---|---|
| 400 | `validation_failed` | Payload no cumple las reglas de `validaciones.py`. Incluye `details: string[]`. |
| 401 | `unauthorized` | Cookie de sesión ausente o vencida (emitido por `middleware.js`, ver punto 1 del brief). |
| 404 | `not_found` | El recurso (`gastos.id` / `gastos_fijos.id`) no existe. |
| 500 | `internal_error` | Falla no esperada del servidor. |

## Fuera de alcance de este contrato

- Autenticación distinta a la cookie de sesión ya existente.
- Endpoints de lectura (`GET /api/expenses`, `GET /api/fixed`) — no
  pedidos en el brief, se pueden derivar de `db.get_gastos` /
  `db.get_gastos_fijos` cuando se implementen.
- Cualquier infraestructura de despliegue (Opción A/B), rate limiting,
  CORS, o manejo de conexión a SQLite concurrente — todo eso depende de
  la arquitectura de VPS que todavía no está aprobada.
