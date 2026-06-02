---
paths:
  - "presupuesto/**/*"
  - "marca/**/*"
  - "*.html"
---

# Regla: Documentos de Marca

## Estructura de documentos HTML

Todo documento comercial (presupuesto, propuesta, informe) debe:

1. **Usar el template base** de `presupuesto/template.html`
2. **Cargar assets de marca** desde `marca/jdg/` (proyectos propios) o `marca/cliente/` (proyectos de terceros)
3. **Ser imprimible a PDF** sin problemas de layout (usar `@media print`)
4. **Incluir acotaciones** como comentarios HTML visibles tipo:
   ```html
   <!-- ACOTACIÓN PARA R.P.: Este bloque es el header. Modificar colores aquí. -->
   ```

## Assets de marca JDG
- `marca/jdg/logo.svg` → logo principal
- `marca/jdg/colores.css` → variables CSS de marca (crear si no existe)
- `marca/jdg/datos.json` → datos de contacto, CUIT, etc. (crear si no existe)

## Para documentos de cliente
- Copiar la estructura de `marca/jdg/` en `marca/cliente/`
- Reemplazar assets con los del cliente
- El template HTML detecta automáticamente según una variable `data-marca`
