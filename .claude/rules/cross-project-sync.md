# Regla: Sincronización entre proyectos y template

## Archivos que se propagan de vuelta al template

Algunos archivos de cada proyecto contienen aprendizajes que benefician a TODOS los proyectos futuros. Estos deben sincronizarse periódicamente al template maestro.

### Propagación automática (sugerir al cerrar sesión)
- **tasks/lessons.md** → Las lecciones marcadas como "universal" se copian al template
- **CLAUDE.local.md** → Preferencias nuevas que el usuario confirme como permanentes

### Propagación con autorización explícita
- **marca/jdg/** → Solo si el usuario dice "actualizá la marca en el template" o similar
- Nunca modificar logo, colores, o datos fiscales sin confirmación

## Cómo distinguir lecciones universales de específicas

**Universal** (va al template):
- "Siempre verificar formato de fecha en Apps Script antes de operar"
- "Los webhooks de Tally necesitan un delay de 2s para procesarse"
- "Usar IMPORTRANGE en vez de copiar datos entre sheets"

**Específica** (se queda solo en este proyecto):
- "El cliente prefiere los reportes en dólares"
- "La API de Mercado Pago tiene un bug con montos menores a $100"

## Comando disponible
Usar `/project:sync-to-template` para revisar qué sincronizar.

## Ruta del template maestro
El template vive en: `G:\Mi unidad\15 - Sistemas\XX - DESARROLLOS\00 - TEMPLATE PROYECTO\`
Claude Code debe preguntar la ruta si no la encuentra.
