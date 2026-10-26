## Resumen

Implementé los dos puntos del brief dentro del workdir aislado (`lab/reinvencion`, sin tocar `main` ni el legacy):

1. **Card de Deuda**: `renderDeudaDetail()` ahora muestra el desglose gasto a gasto (mes, quién pagó, % y $ de reparto) en vez de solo el agregado, y agrega un botón **Saldar** por fila. Como no existía backend para marcar un gasto como saldado, agregué el mínimo necesario (`db.saldar_gasto` + `POST /api/expenses/:id/saldar` en `api.py`, whitelisteado en `middleware.js`, documentado en ambos READMEs/contratos). El botón respeta `liveMode`: en modo snapshot queda deshabilitado con una nota explícita, sin simular ninguna escritura falsa.

2. **Acordeón exclusivo**: `toggleDetail()` ya era una sola función compartida por las 4 cards (mejor que el legacy); le agregué `closeDetail()`/`DETAIL_KINDS` para que abrir un panel cierre cualquier otro abierto, sin tocar los filtros de persona existentes de cada panel.

Agregué tests nuevos en `lab/tests/test_api.py` y `src/lab-dashboard/tests/proxy.test.mjs`, pero **no pude ejecutar ningún test suite**: este wrapper solo me dio herramientas de archivo (Read/Edit/Write/Glob/Grep), sin shell. Hice una revisión estática exhaustiva en su lugar (detallada en `report.md`) y dejé los comandos exactos para que el coordinador los corra antes de aceptar el candidato.

Todo el detalle (archivos tocados, decisiones de backend, limitaciones y QA pendiente) está en `report.md` en la raíz del workdir.