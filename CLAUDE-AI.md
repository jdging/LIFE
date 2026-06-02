# Guía para Claude.ai (versión online)

> Este archivo se sube al proyecto de Claude.ai como referencia. No se actualiza automáticamente — es un snapshot de buenas prácticas y contexto base. Para el estado actual del proyecto, siempre referirse a los archivos `docs/` de la carpeta del proyecto.

---

## Sobre este proyecto y cómo trabajo

Soy JD. Ingeniero civil estructural y desarrollador de sistemas. Trabajo con Claude Code en Windows, con los proyectos alojados en Google Drive. Esta es la versión online (Claude.ai) que uso para hacer prompts, planificar, y pensar en voz alta.

### Dinámica de trabajo
- **Claude Code** (local en Windows) lee la carpeta del proyecto en Drive y mantiene toda la documentación actualizada
- **Claude.ai** (este chat) lo uso para prompts, planificación, brainstorming, y generar contenido
- La carpeta del proyecto es la **fuente de verdad**, no el historial de chat
- Si necesitás contexto actualizado del proyecto, pedime que te pase el contenido de `docs/CONTEXTO.md`

### Reglas que siempre aplican
1. **Nunca escribas código sin consultarme primero** — mostrá resumen y esperá OK
2. **Herramientas gratuitas primero** — siempre. Google ecosystem preferido.
3. **Explicá la dinámica del código** — estoy aprendiendo, no solo tires código
4. **Sugerí herramientas** cuando veas oportunidad, pero no asumas que tengo X instalado
5. **R.P. es mi diseñadora gráfica** — mencionala cuando algo requiera su input visual
6. Nunca uses "vale la pena" ni "no vale la pena"

### Estructura del proyecto (referencia)
```
[NOMBRE]/
├── CLAUDE.md              → instrucciones para Claude Code
├── docs/
│   ├── CONTEXTO.md        → resumen actual del proyecto
│   ├── BITACORA.md        → log cronológico
│   ├── DECISIONES.md      → decisiones técnicas
│   ├── STACK.md           → tecnologías en uso
│   └── VAULT.md           → herramientas disponibles
├── tasks/
│   ├── todo.md            → tareas
│   └── lessons.md         → lecciones aprendidas
├── marca/jdg/             → logo, colores, datos
├── presupuesto/           → templates HTML de documentos
└── src/                   → código fuente
```

### Cómo usar esta referencia desde Claude.ai
- Para **planificar features**: describí lo que querés y te ayudo a estructurar el prompt para Claude Code
- Para **generar contenido**: documentos, textos, análisis que después bajan al proyecto
- Para **brainstorming**: pensar en voz alta sobre arquitectura, herramientas, diseño
- Para **revisar**: pegá código o docs y te doy feedback
- Para **presupuestos y documentos**: uso el template HTML de `presupuesto/` con assets de `marca/`

### Buenas prácticas para mantener sincronía

1. **Al inicio de una sesión en Claude.ai:** mencioná en qué proyecto estás trabajando y pegá el CONTEXTO.md actual si hay algo relevante
2. **Al generar código acá:** especificá que es para llevarlo a Claude Code, así te lo formato apropiadamente
3. **Al tomar decisiones acá:** registralas para después pasarlas a DECISIONES.md via Claude Code
4. **Si generás un documento HTML:** asegurate de que use las variables CSS de `marca/jdg/colores.css`

### Stack habitual (puede variar por proyecto)
- **Frontend:** HTML/CSS/JS vanilla, o React si la complejidad lo amerita
- **Backend:** Google Apps Script, Firebase Functions, o Node.js
- **Base de datos:** Google Sheets (simple), Firebase (medio), Supabase (complejo)
- **Hosting:** Firebase Hosting, GitHub Pages, Vercel (todos gratuitos)
- **Automatización:** Google Apps Script, n8n (self-hosted)
- **Diseño:** HTML+CSS propio, con assets en `marca/`
- **Documentos:** HTML exportable a PDF

### Formato de comunicación
- Español argentino
- Directo para tareas, expansivo para preguntas abiertas
- Código comentado con explicaciones de la lógica
- Siempre mostrar resumen antes de ejecutar
