# Dashboard de Finanzas — LIFE (lab, datos reales)

Dashboard estático (HTML/CSS/JS vanilla + Chart.js) para visualizar las finanzas reales de
JD/Pinki: gastos, ingresos, deudas mes a mes, proporcionalidad JD/Pinki y gastos fijos.

Vive en `/home/ai-os/hermes/workspaces/lasso/candidates/dashboard-lab`, aislado del repo
real de LIFE (`/home/ai-os/projects/LIFE`). No toca ese repo.

## De datos de ejemplo a datos reales

Esta versión reemplaza los ~20 gastos ficticios de la iteración anterior por una migración
real exportada del sistema de producción de Juan (`export_dashboard_real.py`, corrida por el
coordinador antes de esta tarea):

- `data/gastos.json` — 190 gastos reales desde febrero 2026, incluyendo cuotas que se
  extienden hasta 2027.
- `data/ingresos.json` — 26 ingresos reales (Salario, Extra, Freelance) por persona.
- `data/gastos_fijos.json` — 13 gastos fijos activos (alquiler, expensas, seguros,
  suscripciones, etc.).
- `data/resumen_meses.json` — 20 meses (2026-02 a 2027-09) con totales, proporción JD/Pinki
  y deuda **ya pre-calculados** por el exportador (no se recalculan en el frontend).

El badge del masthead pasó de "🌱 Datos de ejemplo, no reales" a
"📂 Datos reales migrados — Finanzas LIFE".

## Qué cambió respecto a la v1 (datos de ejemplo)

El sistema de diseño (papel/verde salvia/terracota, Fraunces + Work Sans, masthead
editorial) **no se tocó** — Juan ya lo había aprobado. Lo que cambió es el contenido:

1. **Cards de resumen**: antes eran "total / cantidad / promedio / categoría top" sobre
   gastos únicamente. Ahora son **total gastado, total de ingresos, balance neto e ingresos
   − gastos, y proporción JD/Pinki del mes más reciente con datos reales**.
2. **Sección nueva "Deudas"**: card destacada con quién le debe a quién en el mes más
   reciente (tomado de `resumen_meses.json`), más un listado breve de los últimos 5 meses
   anteriores con deuda pendiente, para dar contexto sin saturar la sección.
3. **Gráfico nuevo "Evolución mensual"**: barras de gastos vs. ingresos por mes, para los 20
   meses del export — es el gráfico más importante del dashboard real, muestra la tendencia
   real de las finanzas.
4. **Gráfico nuevo "Proporción en el tiempo"**: línea con `proporcion_jd` / `proporcion_pinki`
   mes a mes, para ver si la proporción es estable o varía. Sólo grafica meses con
   `total_ingresos > 0` (ver "Supuestos" abajo).
5. **Donut "Por categoría"**: mismo gráfico de antes, ahora con los 190 gastos reales.
   Aparecen las mismas 7 categorías de nivel superior que ya existían (Comida, Transporte,
   Hogar, Salud, Entretenimiento, Personal, Mascotas); las categorías nuevas del brief
   (Ferretería, Kiosko, Dietética, etc.) son **subcategorías** dentro de esas 7, visibles en
   la tabla de gastos fijos y no en el donut (que sigue agrupando por categoría, no
   subcategoría, para no romper la iconografía existente).
6. **Sección nueva "Gastos fijos"**: tabla con los 13 fijos activos (nombre, categoría,
   monto estimado, periodicidad) y un total mensual estimado abajo (los bimestrales se
   prorratean a la mitad para que el total sea comparable a un mes típico).
7. **Tabla de detalle de gastos**: mismas columnas que antes (fecha, categoría, monto,
   medio de pago, pagado por), ahora con los 190 gastos reales. Se agregó un **filtro por
   mes** (dropdown) porque 190 filas sin filtrar hacían el scroll incómodo — se mantuvo
   simple, sin paginación. Los gastos en cuotas muestran un tag "N/total" junto al monto.
8. Se mantuvo el gráfico "Quién pagó" (barras JD/Pinki/Común) de la v1 porque ya usaba
   `pagado_por`, que también está presente en los datos reales, y aporta valor real.
9. Las cards "cantidad de gastos", "promedio por gasto" y "categoría con más peso" de la v1
   se retiraron — el brief pedía específicamente 4 cards (total gastos, total ingresos,
   balance, proporción) y esa info ahora vive en otras secciones (conteo implícito en la
   tabla filtrada, categoría top visible en el donut).

## Manejo de errores

Se generalizó el patrón `renderChartSafe` que ya existía para los gráficos a un patrón
equivalente para secciones no-chart (`renderSafe` / `showSectionError`): cada sección
(cards, deudas, tabla de fijos, tabla de detalle) se renderiza en un bloque aislado. Si el
`fetch` de alguno de los 4 JSON falla, sólo las secciones que dependen de ese dataset
muestran un mensaje de error contenido (con detalle técnico), sin romper el resto de la
página. Los 4 JSON se cargan en paralelo con `Promise.allSettled` para que una falla en uno
no bloquee a los demás.

## Supuestos tomados

- **"Mes más reciente con datos"** (usado en la card de proporción y en la deuda destacada)
  se define como el último mes de `resumen_meses.json` con `total_ingresos > 0`. Los meses
  posteriores del export (2026-10 en adelante) tienen `total_ingresos: 0` y sólo repiten el
  total de gastos fijos/cuotas proyectadas — son estimaciones a futuro, no meses cerrados
  con datos reales cargados.
- El gráfico de **proporción en el tiempo** sólo grafica meses con `total_ingresos > 0` por
  el mismo motivo: graficar la proporción "congelada" repetida en meses futuros sin salario
  cargado habría sido ruido, no tendencia real.
- El gráfico de **evolución mensual** (gastos vs. ingresos) sí grafica los 20 meses
  completos del export, tal como pide el brief — incluye los meses futuros con ingreso en
  $0 porque eso también es información real (compromisos fijos ya comprometidos a futuro).
- El **donut por categoría** sigue agrupando por `categoria` (nivel superior), no por
  `subcategoria`, para mantener la iconografía por categoría ya aprobada. Las subcategorías
  nuevas (Ferretería, Kiosko, Dietética, Almacén, etc.) son reales pero se ven en la tabla
  de gastos fijos y en el detalle, no fragmentando el donut.
- El **total de gastos fijos mensual** prorratea los `periodicidad: "bimestral"` a la mitad
  del monto estimado, siguiendo el mismo criterio que ya usa el repo real de LIFE
  (`monto_mensual` vs `monto` en `S.fixed.data`, documentado en las reglas del proyecto).
- Los datos son reales y no se inventó ni completó ningún campo faltante — todo sale
  directamente de los 4 JSON provistos en `data/`.

## Ver el dashboard

Abrí `index.html` directamente en el navegador. Si el navegador bloquea la lectura de los
JSON por política de CORS al usar `file://` (pasa en Chrome, no siempre en Firefox), serví
la carpeta con un servidor estático simple:

```bash
python3 -m http.server 8000
# abrir http://localhost:8000/index.html
```

En GitHub Pages esto no es un problema — el `fetch` funciona normal al ser servido por HTTP.

## Qué falta para producción

- Este dashboard sigue siendo un snapshot estático de los 4 JSON en `data/`, no una
  conexión en vivo a Google Sheets / Apps Script. Si se quiere refrescar, hay que volver a
  correr el exportador real y reemplazar los 4 archivos.
- No se hizo deploy a GitHub Pages ni se tocó `main`; la integración a este repo (rama
  `lab/reinvencion`) la hizo Lasso.

## Protección con contraseña (Vercel Edge Middleware)

Este dashboard tiene datos financieros reales (sueldos, gastos detallados, deudas entre JD
y Pinki). Antes de deployarlo en un link público, se agregó una capa de autenticación con
"recordarme" (90 días) usando **Vercel Edge Middleware** — no la protección nativa de
Vercel porque esa es una feature paga (planes Pro+), esto funciona en el plan gratuito.

Archivos: `middleware.js`, `login.html`, `vercel.json`.

### Configuración requerida en Vercel (hacerlo ANTES de compartir el link)
1. Proyecto en Vercel → **Settings → Environment Variables**.
2. Crear una variable llamada exactamente `DASHBOARD_PASSWORD` con la contraseña elegida
   (nunca se escribe en el código ni en este repo).
3. Marcarla para **Production** (y Preview si se quiere).
4. Confirmar que el **Root Directory** del proyecto en Vercel apunta a esta carpeta
   (`src/lab-dashboard`), porque Vercel busca `middleware.js` en la raíz del Root Directory.

### Cómo funciona
Primera visita sin cookie válida → redirige a `/login` → contraseña correcta → cookie
`dashboard_session` (HttpOnly, Secure, SameSite=Lax, 90 días, firmada con HMAC-SHA256 usando
`DASHBOARD_PASSWORD` como clave) → visitas siguientes no piden contraseña de nuevo hasta que
expire o cambie la contraseña en Vercel.

### ⚠️ No verificado en runtime real
Este código se escribió siguiendo la documentación oficial de Vercel Edge Middleware, pero
**no hay forma de correr Vercel real desde este entorno** (sin `vercel dev`, sin acceso a su
infraestructura). Juan tiene que probar el flujo completo después de deployar: primera
visita → login → cookie → recargar sin que vuelva a pedir contraseña, y que `/style.css`,
`/app.js`, `/data/*.json` pedidos directamente también quedan protegidos. Si algo no anda
como se describe, reportarlo para iterar — el punto con más chance de necesitar ajuste es la
sintaxis exacta de `config.matcher` una vez corra contra la infraestructura real.
