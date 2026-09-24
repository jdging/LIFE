# LIFE Lab — capa de datos conversacional (rama `lab/reinvencion`)

> Carpeta de laboratorio (DEC-LAB-001, ver `docs/DECISIONES.md`). No es parte del sistema
> de producción (Sheets/Apps Script/AppSheet) que usan JD y Pinki a diario — es la base para
> el bot conversacional Lasso y el dashboard de datos de ejemplo en `src/lab-dashboard/`.

## Qué hay acá
- `db.py`: capa de acceso a SQLite (WAL, un solo proceso escritor). Tablas: `gastos`,
  `estado_conversacional` (Fase 1), `recetas`, `receta_ingredientes`, `inventario_bienes`,
  `inventario_cocina`, `lista_compras` (Fase 3). Principio no negociable: `insert_gasto()`
  rechaza cualquier insert sin `confirmado=True`.
- `models.py`: dataclasses de apoyo.
- `seed_and_export.py`: siembra 20 gastos de EJEMPLO y exporta a
  `../src/lab-dashboard/data/gastos.json` (fuente de datos del dashboard estático).
- `seed_recetas_inventario.py`: siembra recetas/inventario/lista de compras de EJEMPLO,
  imprime qué se puede cocinar con el stock cargado (`sugerir_receta_cocinable`). Idempotente:
  solo limpia sus propias tablas antes de sembrar, no toca `gastos`/`estado_conversacional`.
- `data/lasso.sqlite`: base SQLite generada por los scripts de arriba (no versionar el
  contenido real cuando haya datos reales — ver `.gitignore` si se agrega más adelante).
- `tests/`: `unittest` puro, sin dependencias externas.

## Cómo correr
```bash
cd lab
python3 seed_and_export.py            # gastos de ejemplo + export a src/lab-dashboard/
python3 seed_recetas_inventario.py    # recetas/inventario/compras de ejemplo
python3 -m unittest discover -s tests -v
```
Los dos scripts de seed pueden correrse en cualquier orden y varias veces sin duplicar datos
ni pisarse entre sí (cada uno limpia únicamente sus propias tablas).

## Qué falta (fuera de alcance de lo ya implementado)
- Conectar esta capa de datos al flujo conversacional real del bot Lasso (perfil de Hermes,
  ver apéndice de arquitectura en el documento de propuesta original) — hoy solo hay datos
  de ejemplo generados por script, no carga conversacional real.
- Reemplazar los datos de ejemplo por una semilla real de recetas/inventario de Juan.
- `inventario_bienes` tiene CRUD básico pero ninguna lógica de negocio todavía (no forma
  parte del alcance de Fase 3).

## Origen
Código implementado y verificado (tests + ejecución real) por especialistas delegados por
Lasso en workdirs aislados, integrado a este repo por Lasso el 2026-09-24. Ver
`/home/ai-os/brain/plans/lasso/BITACORA.md` para el detalle de las corridas y verificaciones.
