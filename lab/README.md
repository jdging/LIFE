# LIFE Lab — capa de datos conversacional (rama `lab/reinvencion`)

> Carpeta de laboratorio (DEC-LAB-001, ver `docs/DECISIONES.md`). No es parte del sistema
> de producción (Sheets/Apps Script/AppSheet) que usan JD y Pinki a diario — es la base para
> el bot conversacional Lasso y el dashboard de datos de ejemplo en `src/lab-dashboard/`.

## Qué hay acá
- `db.py`: capa de acceso a SQLite (WAL, un solo proceso escritor). Tablas: `gastos`,
  `estado_conversacional`, `tarjetas` (Fase 1 + extensión de reparto), `recetas`,
  `receta_ingredientes`, `inventario_bienes`, `inventario_cocina`, `lista_compras` (Fase 3).
  Principio no negociable: `insert_gasto()` rechaza cualquier insert sin `confirmado=True`.
- `models.py`: dataclasses de apoyo.
- `seed_and_export.py`: siembra 20 gastos de EJEMPLO y exporta a
  `../src/lab-dashboard/data/gastos.json` (fuente de datos del dashboard estático).
- `seed_tarjetas.py`: siembra 3 tarjetas de EJEMPLO, incluyendo `TC1` ("Visa", BNA,
  `titular='JD'`, `uso_compartido=True`, `es_default_dinamico=1`) — inspirada en la tarjeta
  real de Juan, que está a su nombre pero la usan los dos.
- `seed_recetas_inventario.py`: siembra recetas/inventario/lista de compras de EJEMPLO,
  imprime qué se puede cocinar con el stock cargado (`sugerir_receta_cocinable`). Idempotente:
  solo limpia sus propias tablas antes de sembrar, no toca `gastos`/`estado_conversacional`.
- `data/lasso.sqlite`: base SQLite (**no versionada, ver `.gitignore`** — contiene datos
  reales cargados conversacionalmente además de los de ejemplo, nunca debe subirse a GitHub).
- `tests/`: `unittest` puro, sin dependencias externas (incluye `tests/test_tarjetas.py`).

## Tarjetas y reparto de gastos (JD/Pinki)

### Tabla `tarjetas`
Portada de la hoja `Tarjetas` del sistema real (ver `AGENTS.md` del repo, sección "Módulo
Finanzas — Detalle técnico"), con dos columnas nuevas: `es_default_dinamico` y
`uso_compartido`.

**`titular` vs `uso_compartido` — no confundir:** `titular` es de quién es la tarjeta
legal/nominalmente (JD, Pinki, o Común si es de la cuenta conjunta — este último valor es
una extensión del laboratorio respecto del modelo real, que solo admite JD/Pinki).
`uso_compartido` es un concepto distinto: indica si ambos usan la tarjeta habitualmente en
la práctica, sin importar quién sea el titular. Caso real que motivó esta columna: la Visa
BNA de Juan está a su nombre (`titular='JD'`), pero la usan los dos — por eso queda
`titular='JD'` **y** `uso_compartido=True` a la vez, en vez de forzarla como `'Común'`.

`es_default_dinamico`: a lo sumo una tarjeta puede tener este flag en 1 (`insert_tarjeta` lo
valida). Responde al pedido de Juan de tener "la tarjeta de crédito por defecto cuando
pagamos dinámicamente" — el dato queda modelado y consultable vía
`get_tarjeta_default_dinamico`; usarlo automáticamente en el parser conversacional es tarea
aparte, no implementada todavía.

### Columnas nuevas en `gastos`: reparto dinámico/manual
`tarjeta_id` (FK opcional), `tipo_proporcion` (`'dinamico'` default o `'custom'`),
`proporcion_jd`/`proporcion_pinki` (solo si `custom`, deben sumar 100).

**No confundir con `pagado_por`** (ya existente): `pagado_por` es quién puso la plata/tarjeta
físicamente. El reparto es cómo se divide el costo entre JD y Pinki, independientemente de
quién pagó — son conceptos distintos y se combinan libremente (ej. pagó JD con su tarjeta,
el gasto se reparte 50/50).

`tipo_proporcion='dinamico'`: la proporción se calcula por fuera según ingresos del mes (ver
`AGENTS.md`, "Lógica de proporcionalidad") — esta capa no implementa ese cálculo, solo deja
el gasto marcado sin proporción explícita. `insert_gasto` valida y rechaza combinaciones
inválidas (custom sin proporciones o que no suman 100; dinámico con proporciones seteadas).
Retrocompatible: callers que no pasan estos campos siguen funcionando igual que antes.

### Primer gasto real cargado conversacionalmente (2026-09-24)
Juan: *"hoy gastamos 17mil en el cine con pinki, pasalo como gasto 50/50"*, pagado con la
Visa BNA (`tarjeta_id='TC1'`, `titular='JD'`, `uso_compartido=True`), confirmado
explícitamente por Juan antes de guardar. `gastos.id=21` en `data/lasso.sqlite` — primer
dato real (no de ejemplo) del laboratorio, cargado por Lasso interpretando el mensaje
directamente, sin bot standalone.

## Cómo correr
```bash
cd lab
python3 seed_and_export.py            # gastos de ejemplo + export a src/lab-dashboard/
python3 seed_tarjetas.py              # tarjetas de ejemplo
python3 seed_recetas_inventario.py    # recetas/inventario/compras de ejemplo
python3 -m unittest discover -s tests -v
```
Los scripts de seed pueden correrse en cualquier orden y varias veces sin duplicar datos ni
pisarse entre sí (cada uno limpia únicamente sus propias tablas).

## Qué falta (fuera de alcance de lo ya implementado)
- Conectar esta capa de datos al flujo conversacional completo del bot Lasso en un grupo de
  Telegram con JD y Pinki (hoy la carga conversacional real ya funciona 1:1 con Juan en este
  chat, invocando `db.py` directo — falta el grupo, pendiente de chat_id de Pinki).
- Implementar el cálculo real de `tipo_proporcion='dinamico'` (según ingresos del mes).
- Reemplazar los datos de ejemplo por una semilla real de recetas/inventario de Juan.
- `inventario_bienes` tiene CRUD básico pero ninguna lógica de negocio todavía (no forma
  parte del alcance de Fase 3).

## Origen
Código implementado y verificado (tests + ejecución real) por especialistas delegados por
Lasso en workdirs aislados, integrado a este repo por Lasso el 2026-09-24. Ver
`/home/ai-os/brain/plans/lasso/BITACORA.md` para el detalle de las corridas y verificaciones.
