# Tareas del Proyecto LIFE

> Actualizado: 2026-04-12. Sesión 27..

---

## Estado de módulos (todos en producción)

| Módulo | Ruta | Estado |
|--------|------|--------|
| Hub | src/index.html | ✅ producción |
| Jardín | src/jardin/index.html | ✅ producción |
| Finanzas | src/finanzas/index.html | ✅ producción |
| Inventario | src/inventario/index.html | ✅ producción |
| Compras | src/compras/index.html | ✅ producción |
| Recetario | src/recetario/index.html | ✅ producción |

---

## Pendientes activos

### Sin pendientes activos
- Todos los módulos en producción y operativos.


## Backlog (ideas registradas, no urgentes)

### Finanzas
- Endpoint `?action=log` con paginación (para cuando el Log crezca mucho).
- Página de configuración in-app para cambiar `APPSHEET_URL` sin editar el HTML.
- H7: Card de proporción — si el rango abarca varios meses, mostrar "Proporción no disponible — seleccioná un mes único" en lugar de la proporción del mes actual.

### Jardín
- (Sin pendientes activos.)

---

## Bugs menores abiertos (bajo impacto, uso personal)

| Severidad | Archivo | Descripción |
|-----------|---------|-------------|
| 🟡 Menor | `apps-script/finanzas-api.js` | `softDelete()` no usa LockService (inconsistente pero aceptable) |
| 🟡 Menor | `apps-script/inventario-setup.js` | `onInventarioChange()` sin LockService — riesgo de IDs duplicados en importación masiva |
| 🟡 Menor | `apps-script/finanzas-setup-gastosfijos.js` | Validación tarjeta guarda nombre en lugar de ID |
| 🟡 Menor | `apps-script/finanzas-seed.js` | Seed sin columna `corresponde_a` — datos de prueba usan fallback 'Común' |
| 🔵 Mejora | `src/finanzas/index.html` | Varios `innerHTML` con datos de usuario sin escapar — riesgo XSS mínimo |
| 🟡 Menor | `src/inventario/index.html` | `renderCards()` cuenta filteredItems en lugar del total global |
| 🔵 Mejora | `src/inventario/index.html` | `escAttr()` no escapa `<` ni `>` |

---

## Historial resumido

### Sesión 30 (2026-06-02) — Auditoría completa módulo Finanzas
- ✅ Fase 0: diagnóstico estático del módulo.
- ✅ F-A: getFixedKind() + visibilidad fijos shared/personal (card común === detalle).
- ✅ F-A.1: sub-línea card Total (shared × meses) + computeFixedForPersona('comun') multi-mes + limpieza.
- ✅ F-B: bimestrales /2 en multi-mes (computeFixedTotalForPeriod + computePresupuestoParts).
- ✅ F-C: getFixedKind + ×meses propagados a renderCreditoCard + toggleCreditoDetail.
- ✅ F-D: sorts null-safe (Inversiones/Ingresos) + eliminado console.log [CUOTAS DEBUG].
- ✅ Decisiones cerradas: D1 (ingreso Común → sin cambios, DEC-029), D2 (variable 100/0 → sin cambios, DEC-030).
- ℹ Aceptados sin urgencia: H1 (API pública), H8 (lógica de fijos duplicada en 4+ lugares — candidata a unificar en helper).
