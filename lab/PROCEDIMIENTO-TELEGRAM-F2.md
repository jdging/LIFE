# Procedimiento Telegram — F2 punto 8 (candidato)

Estado: preparado en `lab/reinvencion`. El procedimiento externo (`brain/plans/lasso/PROCEDIMIENTO-TELEGRAM-GASTOS.md`) ya fue actualizado: no usaba `/api/tarjetas` y solo mencionaba tarjeta en la línea del subcomando `normalizar`.

## Flujo vigente en este candidato

1. Extraer del mensaje o comprobante monto, fecha, categoría, descripción, medio de pago, pagador, reparto y cuotas cuando estén presentes. Crédito y Débito son valores de `medio_pago`; `cuotas_total` es el número de pagos. No pedir, inferir ni transmitir identificación de tarjeta o banco.
2. Pasar los datos a `telegram_ingesta.py normalizar`. Si devuelve `campos_faltantes`, invocar `pregunta` una vez y pedir **todos** los faltantes en una sola lista. El nombre del banco en un comprobante puede formar parte del texto del comprobante, pero no es un campo financiero a completar ni se usa para identificar una tarjeta.
3. Repetir normalización con las respuestas hasta completar los campos. Mostrar el resumen de `pregunta` y esperar la confirmación explícita del usuario. Solo después invocar `guardar --confirmado`.
4. Para un gasto con Crédito o Débito, no agregar `tarjeta`, `tarjeta_id` ni `banco` al borrador ni al payload. Las cuotas se siguen enviando con `cuotas_total`.

## Aplicación al procedimiento externo

Procedimiento activo: `/home/ai-os/brain/plans/lasso/PROCEDIMIENTO-TELEGRAM-GASTOS.md`. Hay que mantener allí la lista de campos, el esquema de salida estructurada y los ejemplos de conversación según los cuatro pasos anteriores. Debe retirar cualquier instrucción que consulte `GET /api/tarjetas`, pida banco/tarjeta, resuelva coincidencias o insista en completar ese dato antes de confirmar. Verificar que la pregunta sea única para todos los faltantes y que `guardar` solo se llame tras una respuesta afirmativa explícita. Esta tarea no edita ni ejecuta el procedimiento externo.

## Compatibilidad y publicación

La columna histórica `gastos.tarjeta_id` y la tabla `tarjetas` se conservan sin migración destructiva. La API nueva omite `tarjeta_id` en respuestas de gastos y retira `GET /api/tarjetas`; los clientes antiguos que dependan de ese endpoint deberán actualizarse junto con el procedimiento. El export estático `src/lab-dashboard/data/gastos.json` se regeneró sin `tarjeta_id` (189 filas; el resto de los datos queda idéntico y la base SQLite no se modificó). Este candidato no se publicó.
