# Stack Tecnológico

> Todo lo que está instalado, configurado o en uso en este proyecto.

## Herramientas de desarrollo
| Herramienta | Versión | Para qué se usa | Gratuita |
|------------|---------|-----------------|----------|
| Claude Code | — | Asistente de desarrollo | Sí (con plan) |
| Git | — | Control de versiones | Sí |

## Lenguajes y frameworks
| Tecnología | Versión | Rol |
|-----------|---------|-----|
| HTML/CSS/JS | Vanilla | Frontend de todos los módulos |
| Chart.js | 4.4.3 (CDN) | Visualizaciones en el dashboard Finanzas |
| Google Apps Script | — | API backend: Finanzas, Inventario, Compras |

## Servicios externos
| Servicio | Tier | Para qué se usa | Costo |
|---------|------|-----------------|-------|
| Google Drive | Gratuito | Almacenamiento del proyecto | $0 |
| Google Sheets | Gratuito | Base de datos del módulo Finanzas | $0 |
| Google Apps Script | Gratuito | API REST para el dashboard Finanzas | $0 |
| GitHub Pages | Gratuito | Hosting estático del frontend | $0 |
| AppSheet | Tier gratuito | Formulario de carga (Finanzas, Inventario, Compras) | $0 |
| MailApp (Apps Script) | Gratuito | Envío de lista de compras por email (100 emails/día cuenta personal) | $0 |

## URLs de producción
| Recurso | URL | Estado |
|---------|-----|--------|
| Apps Script API Finanzas | URL en src/finanzas/index.html → constante API_URL | activo (6 endpoints) |
| Google Sheet Finanzas | https://docs.google.com/spreadsheets/d/1CESc-ghrnUfz6lhwg4oJlcQ9RYOYUAE93zyQv3Dk2yg/edit | activo |
| Apps Script API Inventario | URL en src/inventario/index.html → constante API_URL | activo (2 endpoints) |
| Google Sheet Inventario | ID: 1q8yGt2Q0q966kK5_F6LO4jJKt8x3IK37WCwu0sl-BLw | activo |
| Apps Script API Compras | URL en src/compras/index.html → constante API_URL | activo (6 endpoints) |
| Google Sheet Compras+Recetario | ID en compras-setup.js y compras-api.js | activo |
| Apps Script API Recetario | URL en src/recetario/index.html → constante RECETARIO_API_URL | pendiente deploy |

## Skills de Claude Code instalados
| Skill | Para qué se usa |
|-------|-----------------|
| auto-context | Mantener docs actualizados |
| close-session | Cerrar sesión y documentar |
| status | Ver resumen del proyecto |
| update-context | Actualizar docs manualmente |

## Dependencias del proyecto
Sin package.json — proyecto HTML estático. Chart.js se carga desde CDN.
