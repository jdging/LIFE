---
name: auto-context
description: >
  Mantiene la documentación del proyecto actualizada automáticamente.
  Usar cuando se completa una tarea, se toma una decisión técnica,
  se agrega una herramienta al stack, o al inicio/fin de cada sesión de trabajo.
allowed-tools: Read, Write, Edit, Glob, Grep
---

# Skill: Auto-Context — Documentación viva del proyecto

## Trigger automático
Este skill se activa cuando:
- Se completa una funcionalidad nueva
- Se instala una dependencia o herramienta
- Se toma una decisión arquitectónica
- El usuario dice "actualizá el contexto", "cerremos sesión", o similar
- Han pasado varios cambios sin actualizar la documentación

## Acciones

### 1. Actualizar `docs/CONTEXTO.md`
Reescribir el resumen completo del proyecto con el estado actual:
- Qué es el proyecto
- Qué hace hasta ahora
- Stack actual
- Estado de las funcionalidades

### 2. Agregar entrada en `docs/BITACORA.md`
Entrada cronológica con formato estándar.

### 3. Actualizar `docs/STACK.md` si hubo cambios técnicos

### 4. Actualizar `docs/DECISIONES.md` si se tomó una decisión

### 5. Actualizar `tasks/todo.md` marcando tareas completadas

### 6. Actualizar `tasks/lessons.md` si hubo un aprendizaje

### 7. Actualizar `AGENTS.md` secciones de Arquitectura y Watch Out For si aplica

## Principio
La documentación debe ser suficiente para que alguien (o Codex en una sesión nueva) entienda el proyecto completo leyendo solo la carpeta `docs/`.
