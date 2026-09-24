# LIFE Lab — capa de datos conversacional (rama `lab/reinvencion`)

> Carpeta de laboratorio (DEC-LAB-001, ver `docs/DECISIONES.md`). No es parte del sistema
> de producción (Sheets/Apps Script/AppSheet) que usan JD y Pinki a diario — es la base para
> el bot conversacional Lasso y el dashboard en `src/lab-dashboard/`.

## Qué hay acá
- `db.py`: capa de acceso a SQLite (WAL, un solo proceso escritor). Tablas: `gastos`,
  `estado_conversacional`, `tarjetas`, `categorias`, `gastos_fijos`, `ingresos`,
  `inversiones`, `recetas`, `receta_ingredientes`, `inventario_bienes`, `inventario_cocina`,
  `lista_compras`. Principio no negociable: `insert_gasto()`/`insert_ingreso()`/
  `insert_inversion()` rechazan cualquier insert sin `confirmado=True`.
- `models.py`: dataclasses de apoyo.
- `seed_and_export.py`: siembra 20 gastos de EJEMPLO y exporta a
  `../src/lab-dashboard/data/gastos.json` (fuente de datos del dashboard estático).
- `seed_tarjetas.py`: siembra 3 tarjetas de EJEMPLO, incluyendo `TC1` ("Visa", BNA,
  `titular='JD'`, `uso_compartido=True`, `es_default_dinamico=1`) — inspirada en la tarjeta
  real de Juan, que está a su nombre pero la usan los dos.
- `seed_categorias.py`: siembra el catálogo real de categorías de LIFE (40 combinaciones
  tipo/categoría/subcategoría, portadas de `AGENTS.md` del repo real).
- `seed_recetas_reales.py`: siembra las **27 recetas REALES** de Juan (extraídas de su
  Notion) — Salmorejo cordobés, Salsa Pinki, Kebab, Pastichio, Pho Bo, Limoncello, etc.
  **Correr SIEMPRE al final** si también corriste `seed_recetas_inventario.py`, porque ese
  script siembra recetas de EJEMPLO en las mismas tablas y las pisaría.
- `seed_recetas_inventario.py`: siembra inventario de cocina + lista de compras de EJEMPLO
  (más 8 recetas de ejemplo que quedan obsoletas si después corrés `seed_recetas_reales.py`
  — ver orden recomendado abajo). Imprime qué se puede cocinar con el stock cargado
  (`sugerir_receta_cocinable`). Idempotente: solo limpia sus propias tablas.
- `data/lasso.sqlite`: base SQLite (**no versionada, ver `.gitignore`** — contiene datos
  reales cargados conversacionalmente además de los de ejemplo, nunca debe subirse a GitHub).
- `tests/`: `unittest` puro, sin dependencias externas. 56 tests en verde.

## Módulo Finanzas completo (replicado del sistema real de LIFE)

### Categorías dinámicas
Tabla `categorias`, sembrada con el catálogo real de LIFE (Hogar, Comida, Entretenimiento,
Transporte, Salud, Personal, Mascotas + subcategorías; Inversión: Plazo fijo/FCI/Dólar-MEP/
Crypto/Otro; Ingreso: Salario/Extra/Freelance/Otro). Función
`crear_categoria_si_no_existe(conn, tipo, categoria, subcategoria, creada_por)`: idempotente,
pensada para que el sistema pueda crear categorías nuevas sobre la marcha si aparece algo no
catalogado en una conversación real (pedido explícito de Juan).

### Tarjetas y reparto de gastos (JD/Pinki)
Tabla `tarjetas`: portada de la hoja `Tarjetas` real, con dos columnas nuevas:
- `es_default_dinamico`: a lo sumo una tarjeta puede tenerlo en 1 — la tarjeta a usar por
  defecto cuando el reparto es dinámico y no se aclaró medio de pago.
- `uso_compartido`: distinto de `titular` (dueño legal/nominal). Caso real: la Visa BNA de
  Juan está a su nombre (`titular='JD'`) pero la usan los dos (`uso_compartido=True`).

Columnas nuevas en `gastos`: `tarjeta_id` (FK opcional), `tipo_proporcion` (`'dinamico'`
default o `'custom'`), `proporcion_jd`/`proporcion_pinki` (solo si `custom`, deben sumar
100). No confundir con `pagado_por` (quién puso la plata físicamente) — son conceptos
independientes y se combinan libremente.

### Cuotas
`insert_gasto_con_cuotas(conn, gasto, cuotas_total)`: si `cuotas_total <= 1`, se comporta
como `insert_gasto` normal. Si es mayor, genera N filas mensuales consecutivas, cada una con
`monto = total/cuotas_total`, `cuota_nro` incremental, y `cuota_ref` apuntando al id de la
primera cuota (que vincula a todas). Agrega a `gastos`: `cuotas_total`, `cuota_nro`,
`cuota_ref`.

### Ingresos e inversiones
Tablas `ingresos` (`persona` JD/Pinki, `categoria` Salario/Extra/Freelance/Otro) e
`inversiones` (`categoria` Plazo fijo/FCI/Dólar-MEP/Crypto/Otro), con el mismo principio de
`confirmado=True` obligatorio que `gastos`.

### Gastos fijos
Tabla `gastos_fijos` (nombre, monto_estimado, periodicidad, día de vencimiento, categoría,
activo). CRUD básico + `actualizar_monto_fijo`.

### Proporción dinámica y deudas (el corazón del modelo real)
- `calcular_proporcion_mes(conn, mes)` ('YYYY-MM'): suma `ingresos` con
  `categoria='Salario'` del mes agrupados por persona, devuelve `{'JD': pct, 'Pinki': pct}`.
  Si el mes no tiene salarios cargados, usa el fallback del último mes anterior que sí
  tenga. Si nunca hubo ninguno, default 50/50.
- `calcular_deudas_mes(conn, mes)`: para los gastos del mes con `pagado_por` en JD/Pinki y
  `tipo_proporcion='dinamico'` (los `custom` usan su proporción explícita propia, no la del
  mes), calcula el saldo neto: quién le debe a quién y cuánto.

**Verificado con un caso real** (no solo tests unitarios): ingresos JD $700.000 + Pinki
$300.000 en un mes → proporción 70/30 calculada correctamente. JD paga $100.000 de un gasto
común dinámico → el sistema calcula que Pinki le debe $30.000 a JD. Exacto.

## Recetario e inventario (Fase 3)
- **27 recetas reales de Juan** cargadas desde su Notion (ver `seed_recetas_reales.py`):
  Salmorejo cordobés, Salsa Pinki, Salsita de hojas de apio, Sopa de calabaza, Tutancamón,
  Corazones de alcaucil, Crema de alcaparras, Ensalada Pinki, Espárragos limón, Hamburguesa,
  Kebab con acompañamientos, Zanahoria glaseada, Yogurt casero, Coliflor (4 variantes),
  Caldo de huesos, Caldo con fideos, Puré de raíces con ajo asado, Ojo de bife, Panchitos,
  Pastichio, Pho Bo, Puré de vegetales, Limoncello (clásico y cremoso). Ingredientes sin
  cantidad clara en el texto original quedan con `cantidad=NULL`, documentado, no inventado.
- `inventario_cocina`, `inventario_bienes`, `lista_compras`: siguen con datos de EJEMPLO
  (no reales todavía) — `sugerir_receta_cocinable`/`descontar_stock_por_receta` funcionan
  sobre esos datos de ejemplo. Pendiente: inventario real de Juan.

### Primer gasto real cargado conversacionalmente (2026-09-24)
Juan: *"hoy gastamos 17mil en el cine con pinki, pasalo como gasto 50/50"*, pagado con la
Visa BNA (`tarjeta_id='TC1'`), confirmado explícitamente antes de guardar. `gastos.id=21` en
`data/lasso.sqlite` — primer dato real del laboratorio, cargado por Lasso interpretando el
mensaje directamente, sin bot standalone ni parser de reglas.

## Cómo correr
```bash
cd lab
python3 seed_and_export.py            # gastos de ejemplo + export a src/lab-dashboard/
python3 seed_tarjetas.py              # tarjetas de ejemplo
python3 seed_categorias.py            # catálogo real de categorías
python3 seed_recetas_inventario.py    # inventario/compras de ejemplo (+ recetas de ejemplo)
python3 seed_recetas_reales.py        # SIEMPRE AL FINAL: pisa las recetas de ejemplo con las 27 reales
python3 -m unittest discover -s tests -v
```
Todos los scripts de seed son idempotentes entre sí para SUS PROPIAS tablas (correrlos de
nuevo no duplica), pero el orden importa entre `seed_recetas_inventario.py` y
`seed_recetas_reales.py` porque ambos siembran en `recetas`/`receta_ingredientes` — el que
corre último gana. Correr `seed_recetas_reales.py` al final siempre.

## Qué falta
- Conectar esta capa de datos al flujo conversacional completo del bot Lasso en un grupo de
  Telegram con JD y Pinki (hoy la carga conversacional real ya funciona 1:1 con Juan en este
  chat, invocando `db.py` directo — falta el grupo, pendiente de chat_id de Pinki).
- Inventario de cocina real (hoy es de ejemplo).
- Usar `get_tarjeta_default_dinamico` automáticamente en el parser conversacional cuando no
  se aclara medio de pago.
- Dashboard (`src/lab-dashboard/`) todavía muestra datos de ejemplo, no el módulo de
  Finanzas completo ni las recetas reales — pendiente de decisión de Juan sobre cómo/si
  mostrar datos reales ahí.

## Origen
Código implementado y verificado (tests + ejecución real, incluyendo cálculos de
proporción/deudas hechos a mano) por especialistas delegados por Lasso en workdirs
aislados, integrado a este repo por Lasso. Ver `/home/ai-os/brain/plans/lasso/BITACORA.md`
para el detalle de las corridas y verificaciones.
