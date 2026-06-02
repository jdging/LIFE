# Template de Proyectos JDG — Guía de Setup

## Contenido de este paquete

### Archivos globales (instalar una sola vez)
Estos archivos van en tu carpeta de usuario de Windows:

| Archivo | Destino | Qué hace |
|---------|---------|----------|
| `GLOBAL-CLAUDE.md` | `C:\Users\TU-USUARIO\.claude\CLAUDE.md` | Preferencias que aplican a TODOS los proyectos |
| `GLOBAL-settings.json` | `C:\Users\TU-USUARIO\.claude\settings.json` | Configuración global (modelo, tokens, permisos) |

### Carpeta template (copiar por cada proyecto nuevo)
| Carpeta | Qué hacer |
|---------|----------|
| `00 - TEMPLATE PROYECTO/` | Copiar, renombrar a `XX - NOMBRE PROYECTO`, abrir Claude Code ahí |

---

## Setup inicial (una sola vez)

### Paso 1: Instalar archivos globales
```powershell
# Crear la carpeta si no existe
mkdir C:\Users\TU-USUARIO\.claude

# Copiar los archivos globales
copy "GLOBAL-CLAUDE.md" "C:\Users\TU-USUARIO\.claude\CLAUDE.md"
copy "GLOBAL-settings.json" "C:\Users\TU-USUARIO\.claude\settings.json"
```

### Paso 2: Completar datos personales
1. Abrir `00 - TEMPLATE PROYECTO/marca/jdg/datos.json` y completar tus datos
2. Reemplazar `marca/jdg/logo.svg` con tu logo real
3. Ajustar colores en `marca/jdg/colores.css` (consultar con R.P.)

### Paso 3: Subir a Google Drive
Subir la carpeta del template a tu Drive en la ubicación que prefieras.

---

## Crear un proyecto nuevo

1. **Copiar** la carpeta `00 - TEMPLATE PROYECTO`
2. **Renombrar** a `XX - NOMBRE DEL PROYECTO` (ej: `01 - Lavadero Web`)
3. **Abrir Claude Code** en esa carpeta: `cd "ruta/al/proyecto" && claude`
4. **Ejecutar** `/project:init` — Claude te pide nombre, descripción, y configura todo
5. **Empezar a trabajar**

### Flujo de trabajo diario
1. Abrir Claude Code en la carpeta del proyecto
2. `/project:status` para ver dónde quedaste
3. Trabajar normalmente (Claude actualiza docs automáticamente)
4. `/project:close-session` cuando termines

### Desde Claude.ai (online)
1. Crear un nuevo proyecto en Claude.ai
2. Subir `CLAUDE-AI.md` como archivo de conocimiento del proyecto
3. Cuando necesites contexto actualizado, pegá el contenido de `docs/CONTEXTO.md`

---

## Estructura de la carpeta template

```
00 - TEMPLATE PROYECTO/
│
├── CLAUDE.md                  ← Instrucciones principales para Claude Code
├── CLAUDE.local.md            ← Preferencias personales (no se comparte)
├── CLAUDE-AI.md               ← Referencia para subir a Claude.ai online
├── .gitignore                 ← Exclusiones de git
│
├── .claude/                   ← Centro de control de Claude Code
│   ├── settings.json          ← Permisos, hooks, config
│   │
│   ├── rules/                 ← Reglas modulares (se cargan automáticamente)
│   │   ├── workflow.md        ← "Consultá antes de codear"
│   │   ├── context-update.md  ← Cuándo actualizar cada doc
│   │   ├── tools-vault.md     ← Cómo sugerir herramientas
│   │   ├── code-style.md      ← Estilo de código + enseñanza
│   │   └── brand-docs.md      ← Reglas para documentos de marca
│   │
│   ├── commands/              ← Comandos slash personalizados
│   │   ├── init.md            ← /project:init — Inicializar proyecto nuevo
│   │   ├── status.md          ← /project:status — Resumen rápido
│   │   ├── update-context.md  ← /project:update-context — Actualizar docs
│   │   ├── close-session.md   ← /project:close-session — Cerrar sesión
│   │   └── suggest-tools.md   ← /project:suggest-tools — Sugerir herramientas
│   │
│   ├── skills/                ← Workflows automáticos
│   │   └── auto-context/
│   │       └── SKILL.md       ← Mantiene la documentación viva
│   │
│   └── agents/                ← Subagentes especializados
│       └── context-keeper.md  ← Audita consistencia de la documentación
│
├── docs/                      ← Documentación viva (fuente de verdad)
│   ├── CONTEXTO.md            ← Resumen actual del proyecto
│   ├── BITACORA.md            ← Log cronológico de sesiones
│   ├── DECISIONES.md          ← Registro de decisiones técnicas
│   ├── STACK.md               ← Tecnologías y herramientas en uso
│   └── VAULT.md               ← Bóveda de herramientas disponibles
│
├── tasks/                     ← Gestión de tareas
│   ├── todo.md                ← Tareas pendientes y completadas
│   └── lessons.md             ← Lecciones aprendidas
│
├── marca/                     ← Assets de marca
│   ├── jdg/                   ← Marca propia
│   │   ├── logo.svg           ← Logo (reemplazar con el real)
│   │   ├── colores.css        ← Variables CSS de marca
│   │   └── datos.json         ← Datos de contacto y fiscales
│   └── cliente/               ← Marca del cliente (si aplica)
│       └── README.md          ← Instrucciones para completar
│
├── presupuesto/               ← Templates de documentos comerciales
│   └── template.html          ← Presupuesto HTML exportable a PDF
│
└── src/                       ← Código fuente del proyecto
    └── README.md              ← Se completa según el stack
```

---

## Filosofía del sistema

**El chat es efímero, los archivos persisten.**

Todo el conocimiento del proyecto vive en la carpeta, no en el historial de conversación. Esto permite:
- Retomar un proyecto después de semanas sin perder contexto
- Sincronizar entre Claude Code (local) y Claude.ai (online)
- Tener un registro completo de decisiones y evolución
- Que cualquier instancia de Claude entienda el proyecto leyendo `docs/`
