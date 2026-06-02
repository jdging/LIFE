# Bóveda de Herramientas

> Catálogo de herramientas, skills, MCP servers, y agentes que Claude puede sugerir según la necesidad del proyecto. **Nada se instala sin aprobación.** Las herramientas se marcan como "sugerida", "aprobada", o "instalada".

## Cómo funciona
1. Claude detecta que una herramienta podría servir para la tarea actual
2. La sugiere con una oración explicando por qué
3. Si se aprueba, se instala y se registra en `docs/STACK.md`
4. Si se rechaza, queda registrada acá como "descartada" con la razón

---

## MCP Servers

### Gestión de proyectos y tareas
| Herramienta | Descripción | Gratuita | Estado |
|------------|-------------|----------|--------|
| Task Master AI | PRD → tareas estructuradas con dependencias | Sí | Probada (proyecto anterior) |
| Codebase Memory MCP | Grafo de conocimiento persistente del codebase | Sí | Probada (proyecto anterior) |

### Búsqueda y datos
| Herramienta | Descripción | Gratuita | Estado |
|------------|-------------|----------|--------|
| Context7 | Docs actualizados de librerías en el contexto | Sí | Sugerida |
| Tavily | Búsqueda web optimizada para IA | Freemium | Sugerida |

### Browser y testing
| Herramienta | Descripción | Gratuita | Estado |
|------------|-------------|----------|--------|
| Playwright MCP | Automatización de browser para testing | Sí | Sugerida |

### Productividad
| Herramienta | Descripción | Gratuita | Estado |
|------------|-------------|----------|--------|
| Slack MCP | Leer threads de bugs directo | Sí | Sugerida |

---

## Skills de Claude Code

### Desarrollo
| Skill | Descripción | Origen | Estado |
|-------|-------------|--------|--------|
| Superpowers (obra) | 20+ skills battle-tested: TDD, debugging, plan-to-execute | GitHub | Sugerida |
| Systematic Debugging | Root cause analysis en 4 fases | GitHub | Sugerida |
| Context Optimization | Reducir costos de tokens | GitHub | Sugerida |

### Documentos y diseño
| Skill | Descripción | Origen | Estado |
|-------|-------------|--------|--------|
| Frontend Design | Interfaces production-grade sin "AI slop" | Anthropic | Sugerida |
| Canvas Design | Gráficos sociales, posters, covers | Anthropic | Sugerida |

### Marketing y contenido
| Skill | Descripción | Origen | Estado |
|-------|-------------|--------|--------|
| Claude SEO | Auditorías de sitio y schema validation | GitHub | Sugerida |
| Brand Guidelines | Encodear tu marca en un skill | Anthropic | Sugerida |

---

## Herramientas CLI
| Herramienta | Descripción | Gratuita | Estado |
|------------|-------------|----------|--------|
| gh (GitHub CLI) | PRs, issues desde terminal | Sí | Sugerida |
| firebase-tools | Deploy y gestión Firebase | Sí | Sugerida |

---

## Repos de referencia
| Repo | Descripción | URL |
|------|-------------|-----|
| Everything Claude Code | Sistema de optimización completo | github.com/affaan-m/everything-claude-code |
| Awesome Claude Skills | Lista curada de skills | github.com/travisvn/awesome-claude-skills |
| FastMCP | Crear MCP servers en Python | github.com/jlowin/fastmcp |

---

## Descartadas
| Herramienta | Razón del descarte | Fecha |
|------------|-------------------|-------|
| [ninguna aún] | - | - |

---

> **Nota:** Este archivo crece orgánicamente. Claude agrega herramientas que descubre durante el trabajo. El usuario decide si se instalan o no.
