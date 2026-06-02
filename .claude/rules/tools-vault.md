# Regla: Bóveda de Herramientas y Sugerencias

## Filosofía
Claude mantiene una "bóveda" de herramientas posibles en `docs/VAULT.md`. Ante cualquier tarea donde una herramienta, skill, MCP server, o agente pueda acelerar el trabajo, Claude DEBE:

1. **Sugerir** la herramienta con una oración explicando por qué sirve
2. **No instalar** nada sin aprobación explícita
3. **Priorizar** herramientas gratuitas y de código abierto
4. **Registrar** en VAULT.md cualquier herramienta nueva que se descubra

## Prioridad de herramientas
1. Herramientas nativas del sistema (bash, git, etc.)
2. Google Workspace (Sheets, Apps Script, Firebase, etc.)
3. Herramientas gratuitas open-source
4. Herramientas con tier gratuito suficiente
5. Herramientas pagas (solo como alternativa mencionada)

## Colaboración con R.P. (diseñadora gráfica)
Cuando la tarea involucre:
- Diseño de UI/UX más allá de lo funcional
- Decisiones de branding o identidad visual
- Paleta de colores o tipografía definitiva
- Material gráfico para cliente

Claude debe sugerir: "Esto sería bueno consultarlo con R.P. para [razón específica]."
