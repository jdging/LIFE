---
paths:
  - "src/**/*"
  - "*.html"
  - "*.js"
  - "*.css"
  - "*.ts"
  - "*.py"
---

# Regla: Estilo de Código y Enseñanza

## Al escribir código, Claude DEBE:

1. **Explicar la dinámica** del código en comentarios o en la respuesta
   - Qué hace cada bloque principal
   - Por qué se eligió ese enfoque
   - Cómo interactúa con el resto del sistema

2. **Usar nombres descriptivos** en inglés para variables y funciones

3. **Comentar en español** las secciones que sean conceptualmente nuevas para el usuario

4. **Documentos HTML** deben:
   - Ser autocontenidos (CSS inline o en `<style>`)
   - Referenciar assets de `marca/` con rutas relativas
   - Ser exportables a PDF sin pérdida de formato
   - Incluir acotaciones legibles para facilitar edición con R.P.

## Estructura de comentarios para enseñanza
```javascript
// === SECCIÓN: [nombre descriptivo] ===
// Qué hace: [explicación simple]
// Por qué: [razón de la decisión]
// Cómo funciona: [mecánica básica]
```
