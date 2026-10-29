# F4 — Supermercado: contrato y QA local

Estado: F4 integrado como candidato sobre la base con F3, sin aceptación de Juan. QA final v4 del coordinador (`f5d720a0-59de-4e96-9729-a5d2977b9a66`) registró Python **656 passed / 1 skipped** (`finanzas_raw.json` real ausente), Node **28/28** y Chromium 390×844 y 1280×900 sin errores, con observación P2: el banner global decía solo lectura mientras Supermercado permitía guardar. **Esa evidencia no valida la integración actual ni el lock de mutación. El implementador no ejecutó tests ni producto en esta corrida; el coordinador debe repetirlos, incluidos los tests F3.**

## Modelo y cálculo

Las tablas nuevas `supermercado_categorias`, `supermercado_productos` y `supermercado_auditoria` se crean en `init_db(conn)` de forma idempotente. No se cargan productos ni categorías por defecto. No se mezclan con `categorias` financieras, `inventario_bienes`, `inventario_cocina`, `lista_compras` ni recetas.

- `a_comprar = max(0, stock_deseado - stock_actual)`; `porcentaje_faltante = 100 * a_comprar / stock_deseado`. Si deseado es cero, el porcentaje es **0**. El estado prioriza `Vacío` si actual <= 0; después `Reponer` si actual < deseado; de lo contrario `OK`. Así, deseado=actual=0 queda `Vacío` pero no integra la lista de compra.
- Cantidades: hasta 1.000.000.000, máximo seis decimales, finitas, no negativas. La API no acepta cadenas ni booleanos como cantidades. Se guardan como texto decimal y se calculan con `Decimal`; la salida JSON usa números.
- Resumen global y por categoría: porcentajes **por conteo de productos**, sin sumar unidades incompatibles. `% vacío = vacíos/productos`; `% lleno = no vacíos/productos` (incluye `Reponer`). Para grupos sin productos ambos porcentajes son 0. `a_reponer` cuenta solo productos con faltante positivo. Se incluye grupo Sin categoría.
- Categorías por `orden` ascendente e `id` para desempate; productos por nombre sin acentos y sin distinción de mayúsculas (`NFD` + `casefold`), luego nombre original e `id`. Los productos sin categoría van al final. Bajar una categoría pasa sus productos a Sin categoría y audita ese cambio.
- Alta, edición, cambio explícito de stock y baja lógica de producto registran `antes_json`, `despues_json`, operación, UTC y actor fijo `sesion_compartida:no_verificado`. El historial sigue disponible tras baja. La identidad del navegador no se toma como actor.
- Cada producto tiene `version` persistida (alta=1). La migración agrega esa columna a tablas v1 sin cambiar sus filas ni auditorías previas y es idempotente; los snapshots históricos v1 pueden no tener `version` porque no existía al registrarlos. PATCH de producto/stock y DELETE exigen `expected_version` entero positivo en JSON; falta o formato inválido da 400, versión obsoleta da 409 con instrucción de recargar. Una operación rechazada no cambia stock, versión ni auditoría. Bajar una categoría incrementa la versión de cada producto reasignado y conserva snapshots antes/después en la auditoría. La UI encadena el refresh forzado detrás de un GET pendiente, invalida su respuesta anterior y espera el snapshot posterior a la escritura antes de confirmar; un conflicto requiere una nueva decisión manual, sin reintento automático de escritura.
- El banner snapshot global identifica Finanzas y otros módulos; Supermercado muestra «Supermercado en vivo» o «solo lectura/no disponible» según su propia API protegida. Antes de un GET válido, con respuesta de estructura inválida, tras recarga fallida o mutación 401/403, los controles de alta, edición, stock y baja se deshabilitan y `superMutate` no envía escrituras. Un GET viejo invalidado no puede reactivar el módulo después de una lectura nueva fallida. PDF e historial conservan sus controles de lectura; ninguno prueba que haya escritura disponible. La API autentica cada solicitud y conserva el control de origen del proxy.
- La pestaña toma un lock antes del primer `await` de una mutación y mantiene los controles de escritura inactivos hasta terminar escritura y refresh. Un segundo submit/clic durante ese intervalo no hace otro `fetch`; un GET válido concurrente tampoco reabre los controles. `finally` libera el lock tanto en éxito como en error; 401/403 o recarga fallida mantienen la indisponibilidad de escritura. Esto cubre el doble clic en una pestaña, no deduplicación entre navegadores ni idempotencia del backend.
- Protección técnica del lab: máximo **1000 productos y 100 categorías activos**. Un alta que supera el límite responde 409 sin alterar filas existentes ni auditar falsamente. No representa un catálogo real. El historial entrega 50 eventos por página, por id descendente, con `next_cursor` y `has_more`; cursor debe ser id válido de auditoría del mismo producto. Producto nunca existente: 404; dado de baja: historial disponible. La lectura de categorías, productos y resumen usa un snapshot SQLite común.

## API y PDF

Todas las rutas exigen el secreto interno del servidor; el proxy exige sesión de dashboard, `Origin` exacto en escrituras y allowlist explícita. `GET /api/supermercado` entrega categorías, productos calculados y resumen. `POST /api/supermercado/categorias` crea `{nombre,orden}`; `PATCH` y `DELETE /api/supermercado/categorias/:id` editan o dan de baja. Para productos, `POST /api/supermercado/productos` crea `{producto,unidad,stock_deseado,stock_actual,categoria_id?}` y devuelve `registro.version`. `PATCH /api/supermercado/productos/:id` requiere `expected_version` junto a los campos cambiados; `DELETE` requiere cuerpo `{ "expected_version": 1 }`. `PATCH /api/supermercado/productos/:id/stock` requiere `{ "stock_actual": 2, "expected_version": 1 }`. `GET /api/supermercado/productos/:id/historial?cursor=ID` entrega una página; omitir cursor obtiene la más reciente. Query desconocida se rechaza.

`GET /api/supermercado/lista.pdf` devuelve PDF binario A4 (`application/pdf`, descarga), generado en servidor con ReportLab 4. Solo incluye faltantes positivos. Cada sección muestra categoría en mayúsculas, y cada fila casilla vacía dibujada, producto, cantidad y unidad. Título, fecha UTC y conteo se repiten en nuevas páginas. Texto largo se envuelve; caracteres no representables por WinAnsi se reemplazan por `?` en el PDF. Si no hay faltantes, responde `409 {"error":"No falta nada"}` sin PDF. El proxy valida tipo y cabecera PDF, limita a 8 MiB y no reenvía headers upstream. Dependencia: `lab/requirements-supermercado.txt` (`reportlab>=4.0,<5`).

## QA offline con base sintética

Estos comandos son para el **coordinador**, desde el workdir y en su corrida de QA. `TMPDIR` y `--basetemp` apuntan a un directorio temporal **fuera del repo/candidato**: la suite completa de retención Telegram exige esa separación. No usar `evidencia/tmp` ni otro temporal bajo el candidato. Los datos de las pruebas y de los PDF son sintéticos. El implementador no ejecutó estos comandos:

```sh
QA_SCRATCH=/tmp/life-f4-qa
mkdir -p "$QA_SCRATCH/tmp"
export TMPDIR="$QA_SCRATCH/tmp"
python -m venv "$QA_SCRATCH/venv"
"$QA_SCRATCH/venv/bin/python" -m pip install -r lab/requirements-supermercado.txt pytest
PYTHONPATH=lab PYTHONDONTWRITEBYTECODE=1 "$QA_SCRATCH/venv/bin/python" -m unittest lab.tests.test_supermercado
PYTHONPATH=lab PYTHONDONTWRITEBYTECODE=1 "$QA_SCRATCH/venv/bin/python" -m unittest lab.tests.test_qa_supermercado
PYTHONPATH=lab PYTHONDONTWRITEBYTECODE=1 "$QA_SCRATCH/venv/bin/python" -m pytest lab/tests --basetemp "$QA_SCRATCH/pytest" -p no:cacheprovider
node --test src/lab-dashboard/tests/*.test.mjs
PYTHONDONTWRITEBYTECODE=1 "$QA_SCRATCH/venv/bin/python" lab/generar_demo_supermercado.py
```

## QA web manual para Juan

Ejecutar **en una terminal interactiva** desde este workdir, después de instalar las dependencias indicadas arriba. El directorio elegido debe existir. El script crea una DB SQLite sintética **nueva** con nombre aleatorio y permisos de usuario; nunca abre una existente ni usa `DEFAULT_DB_PATH`. No iniciar desde esta corrida de implementación.

```sh
QA_SCRATCH=/tmp/life-f4-qa
mkdir -p "$QA_SCRATCH/browser"
PYTHONPATH=lab PYTHONDONTWRITEBYTECODE=1 "$QA_SCRATCH/venv/bin/python" lab/qa_supermercado.py --qa-dir "$QA_SCRATCH/browser" --port 8877
```

Ingresar una **contraseña de prueba nueva** cuando `getpass` la pida; no usar credenciales reales. Abrir `http://127.0.0.1:8877/`, usuario Basic `qa`, esa contraseña. El servidor solo escucha en IPv4 loopback, rechaza puerto 8765, valida Host exacto y `Origin` en escrituras; no ofrece CORS. No guarda ni imprime contraseñas o el secreto interno. Control-C cierra el servidor. Para otra sesión, reiniciar y se crea otra DB nueva; los archivos QA previos permanecen en el directorio hasta que Juan los elimine manualmente.

Si Juan navega desde otra computadora, puede abrir un **túnel SSH local desde su propia terminal** hacia la máquina que ejecuta QA, por ejemplo `ssh -N -L 8877:127.0.0.1:8877 usuario@maquina`, y usar `http://127.0.0.1:8877/` allí. Ajustar `usuario@maquina` a su acceso existente; este proyecto no configura SSH. **Basic viaja en HTTP y es aceptable solo sobre loopback o ese túnel local**. No publicar ni exponer el puerto. Este gate descartable **no replica la autenticación productiva ni la cookie de Vercel**.

El harness sirve solo `index.html`, `app.js`, `style.css` y la API de Supermercado. No sirve `/api/health` ni habilita módulos financieros: el banner global queda en snapshot para Finanzas y otros módulos, mientras Supermercado informa su estado propio tras su GET. Quita fuentes y Chart.js remotos del HTML servido y aplica CSP sin conexión externa; los demás módulos del dashboard mostrarán estados de error de API y los gráficos no estarán disponibles. Es una prueba de navegador de Supermercado, no de Finanzas, Recetas ni de la integración Vercel. Juan todavía debe revisar móvil, impresión/descarga, foco, decimales y dos sesiones reales de navegador. La ponderación agregada continúa pendiente de Juan.

Esperado en pruebas offline de la integración: F3 conserva gráficos, filtros, historia mensual, meses e ingresos; F4 parte de catálogo vacío, permite alta de categoría y producto, edición general con versión y auditoría, cambio de stock y baja lógica; porcentaje y estado correctos en cero/decimal/overstock; historial con snapshots UTC; carrera GET viejo/PATCH/GET nuevo sin cache viejo; doble submit emite un solo POST en la pestaña y se recupera después de un error; GET válido durante escritura no habilita controles; antes de GET, recarga fallida y 401/403 niegan escritura; banner global y estado propio no se contradicen; PDF demo de una página y demo larga de varias páginas en `evidencia/`; sin faltantes devuelve «No falta nada». Juan todavía debe hacer su QA web y revisión visual/UX con R.P.

## Límites

Los originales `Stock_Hogar.xlsx` y `ListaSuper.bas` se analizaron antes, pero no están disponibles ahora: **no se leyeron en esta implementación**. La paridad visual exacta, la ponderación agregada de la macro y los catálogos reales requieren recuperar los originales y revisión de Juan/R.P. No se leyó ni modificó una planilla real, DB cotidiana o módulo productivo. El snapshot de revisión v3 omitió `marca/jdg/` por el filtro del coordinador; esos assets no se eliminaron del candidato. `.lasso-runs` es evidencia operativa del wrapper y no forma parte del diff integrable. El empaquetado de v5 queda a cargo del coordinador. No hay aceptación QA de Juan.
