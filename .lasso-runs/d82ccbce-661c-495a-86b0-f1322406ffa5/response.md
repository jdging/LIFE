Implementación completa de los 4 puntos del brief (t_b5c6e680). Resumen:

1. **Botón "Editar" en tabla de Gastos**: nuevo `kind` `expense-edit` integrado en el sistema genérico de formularios (`app.js`), reutilizando el patrón de `income-edit`/`inventory-edit`, con el campo "cuotas" oculto (no editable) y aviso explícito al usuario.
2. **Columna Monto**: no tocada, según confirmación de Juan.
3. **`PATCH /api/expenses/:id`**: agregado en `api.py`/`db.py` siguiendo el patrón de `income`, excluyendo `cuotas_total` deliberadamente (documentado el por qué); whitelisteado en `middleware.js`; documentado en ambos README/contract; tests nuevos en Python y JS.
4. **Fix Telegram**: `_resumen_borrador()` ahora incluye la descripción cuando está presente; verifiqué que los snapshots existentes en `test_telegram_ingesta.py` no se ven afectados (no está en mis rutas habilitadas de escritura) y agregué un test de regresión en `test_telegram_api.py`.

No tengo herramienta de shell en este entorno, así que no pude correr los tests — queda explícito en `report.md`, junto con el pendiente del dato real id=856 (no corregido, como pidió el brief).