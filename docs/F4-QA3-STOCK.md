# F4 QA3 — controles de stock de a una unidad

**Candidato:** `lab/f4-qa3-stock`, sobre `85a08183e908c8c4826006d2215a2a425e62707f`. Story `F4t_d402c31f`, task `t_ec6b1b10`. Juan confirmó que las flechas deben sumar/restar 1 y que las fracciones manuales de kg/L deben seguir válidas. Esta versión requiere QA del coordinador y una nueva revisión de Juan.

## Implementación

- Cada stock actual del listado tiene botones visibles `−` y `+` con nombre accesible. Las teclas Arriba/Abajo del input usan la misma función. Ambos caminos modifican exactamente una unidad y mantienen los decimales existentes: `0.5 → 1.5 → 2.5`; `1.25 → 2.25 → 1.25`. La función opera con enteros escalados a seis decimales, evitando errores de coma flotante en el límite. Si el campo está vacío, incompleto, inválido, en cero al restar o fuera de `1.000.000.000` al sumar, la acción no cambia nada.
- Los dos campos de stock del formulario de producto, incluido **Deseado**, reciben los mismos controles y comportamiento de teclado al inicializar la página. `app.js` cambia sus atributos `step` a `any`; el HTML estático original conserva `0.000001` porque `index.html` quedó fuera de las rutas autorizadas. El control nativo se oculta solo para estos stocks. La validación existente de hasta seis decimales y el `reportValidity()` del formulario siguen aplicando; una entrada manual decimal no produce `stepMismatch`.
- Los botones del listado recorren `handleSuperStockInput()` y el autosave QA2 existente. Un clic en el botón del mismo producto no fuerza un guardado previo por blur; la edición se guarda una vez, tras 900 ms, blur hacia otro control o Enter, y se anuncia verificada solo después del GET. Los botones se deshabilitan por límite, entrada inválida o gate de escritura cerrado. La reconciliación conserva el nodo del input y de los botones entre lecturas; si cambia el nombre del producto, actualiza su nombre accesible.
- No cambia el contrato de API, el esquema, los valores existentes, precios, finanzas, inventario, recetas ni el PDF. El trabajo de PDF QA3 corresponde a otro candidato pendiente.

## Pruebas para el coordinador

Este implementador **no ejecutó producto ni tests en el wrapper**. Las regresiones Node nuevas usan las funciones reales de `app.js` para pasos enteros/fraccionarios y límites, teclado y acción visible, borradores/ausencia de PATCH inválido, POST decimal en el formulario y preservación de identidad/foco entre productos. La suite anterior de QA2 sigue siendo necesaria para cola global PATCH + GET, refresco diferido, `409`, `401`, GET tardío, snapshots y blur limpio.

```sh
node --test --test-isolation=none src/lab-dashboard/tests/*.test.mjs
```

En Chromium real, con la API/harness aislado y sin datos productivos:

1. Probar en 320, 390, 768 y 1280 px. Desde `0`, `1`, `0.5` y `1.25`, pulsar varias veces `+`, `−`, Arriba y Abajo. Cada pulsación debe cambiar 1, sin perder la fracción ni el foco; `0 − 1` y `1.000.000.000 + 1` no deben cambiar. Inspeccionar visualmente estilo, foco, contraste y espacio con R.P.
2. Escribir `0.5` y `1.25` a mano en el listado; comprobar que el texto siga legible, que una edición válida se guarde una sola vez y que «Guardado y verificado» aparezca después del GET. Dejar vacío, `1.`, negativo, más de seis decimales y un valor mayor al máximo: no debe haber PATCH ni auditoría; las flechas no deben transformar el inválido en cero.
3. En alta y edición de producto, probar `Deseado` y `Actual` con `0.5`/`1.25`, botones y teclado. Confirmar que el formulario no marque `stepMismatch`, que conserve fracciones, y que el payload POST/PATCH use esos valores sin redondear.
4. Editar producto A y pasar a B o a Historial/Editar. Verificar identidad de nodos, foco y valor de B. Repetir con GET tardío, cambios externos, polling y cambio de categoría. Un clic en `+` desde un input editado no debe publicar primero el valor anterior.
5. Repetir los escenarios QA2 de cola global, `409`, `401/403`, reintento explícito, lectura inválida, reconexión sin autopublicación y ausencia de sobrescritura por GET viejo. Correr también las suites Python/F3 habituales del coordinador antes de integrar. Registrar resultado y nueva aceptación de Juan; no hay aprobación ni publicación por este candidato.
