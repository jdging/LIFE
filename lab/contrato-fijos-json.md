# Contrato `data/gastos_fijos.json` v2 — pestaña Gastos fijos (Story t_ce790609)

Fuente: `lab/export_dashboard_real.py` (backend). Consumidor: `src/lab-dashboard/app.js` (frontend). Ambos lados se integran en el MISMO commit.

## Forma
Array JSON con **todas las versiones** de todos los fijos (activas, históricas y bajas), ordenado por `fijo_grupo_id`, `vigente_desde`, `id`. Cada elemento:

| campo | tipo | notas |
|---|---|---|
| `id` | int | id de la versión (fila) |
| `fijo_grupo_id` | int | identidad estable de la serie; NUNCA usar `nombre` como identidad |
| `nombre` | string | descripción de ESTA versión (puede cambiar entre versiones) |
| `monto_estimado` | number | monto bruto según periodicidad |
| `monto_mensual` | number | mensual equivalente (bimestral = monto/2, redondeado a 2 decimales) |
| `periodicidad` | `"mensual"` \| `"bimestral"` | |
| `vigente_desde` | `"YYYY-MM-DD"` | |
| `activo` | 0 \| 1 | 0 en la versión más reciente de una serie = serie dada de baja desde `vigente_desde` |
| `responsable` | `"Común"` \| `"JD"` \| `"Pinki"` \| null | pertenencia, NO pagador |
| `tipo_proporcion`, `proporcion_jd`, `medio_pago`, `categoria`, `subcategoria`, `dia_vencimiento`, `ultima_actualizacion` | como hoy | `medio_pago` es informativo |

## Semántica (idéntica en Python y JS)
- Versión vigente de una serie en la fecha D: la de mayor `(vigente_desde, id)` con `vigente_desde <= D`. Si no hay ninguna, la serie no existía en D.
- La serie está vigente en D si esa versión tiene `activo = 1`. Si tiene `activo = 0`, está dada de baja desde su `vigente_desde`.
- `vigente_hasta` de una versión (derivado, no viene en el JSON): el `vigente_desde` de la siguiente versión de la misma serie menos un día, o abierto si es la última.
- Rango [desde, hasta]: por serie, lista de tramos = versiones cuyo intervalo interseca el rango, recortadas al rango, en orden. Una serie con 2 versiones en el rango produce 2 tramos (nunca se colapsa a un monto).
- Total de fijos de un mes M (card de Gastos): suma de `monto_mensual` de las series vigentes el ÚLTIMO día de M (mismo criterio `vigente_desde <= lastDay` de `getFixed()` legacy).

## Fixture sintético para el frontend
El frontend trabaja con datos INVENTADOS que respetan esta forma (series con renombrado, cambio de monto, versión del mismo día, bajas, bimestral, responsable null). Nunca copiar datos reales al candidato frontend.
