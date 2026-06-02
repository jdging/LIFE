# Regla de Workflow: Consultar Antes de Ejecutar

## Protocolo obligatorio antes de cualquier cambio de código

Antes de escribir, editar o eliminar cualquier código, Claude DEBE:

1. **Resumir** lo que entendió del pedido (máximo 3 oraciones)
2. **Listar** los archivos que va a tocar
3. **Describir** el enfoque técnico en lenguaje simple
4. **Esperar confirmación** explícita del usuario ("dale", "ok", "hacelo", etc.)

### Excepciones
- Correcciones de typos obvios en documentación
- Actualización de archivos de contexto (`docs/*.md`, `tasks/*.md`)
- Cambios solicitados explícitamente con instrucción clara y sin ambigüedad

### Ante la duda
Si hay **cualquier** ambigüedad, preguntar. Es preferible una pregunta de más que un cambio incorrecto.
