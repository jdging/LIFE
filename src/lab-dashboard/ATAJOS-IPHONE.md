# Atajos de iPhone para LIFE · Finanzas

Esta guía es para que armes tus propios Atajos de iOS que te lleven directo a "agregar gasto", "agregar ingreso" o "editar fijos" sin tener que entrar a la app y navegar manualmente. **No inventes el dominio**: reemplazá `<dominio-vercel>` por la URL real que te pase el coordinador cuando esté desplegado (ejemplo de forma: `life-tu-proyecto.vercel.app`, nunca `.vercel.app` solo ni un dominio de prueba).

## Paso 1 — Instalar LIFE como app en tu iPhone

1. Abrí Safari (tiene que ser Safari, no Chrome ni otro navegador) y entrá a `https://<dominio-vercel>/`.
2. Si no estabas logueado, te va a pedir la contraseña del dashboard. Entrala una vez.
3. Apretá el botón de compartir (el cuadradito con la flecha para arriba, abajo al centro).
4. Elegí **"Agregar a la pantalla de inicio"**.
5. Confirmá el nombre ("LIFE" ya viene puesto) y tocá **Agregar**.

Ahora tenés un ícono de LIFE en tu pantalla de inicio que abre la app a pantalla completa, sin la barra de direcciones de Safari.

**Importante:** la app instalada (el ícono) y Safari tienen cookies y sesión separadas, aunque abran la misma web. Vas a necesitar iniciar sesión **dos veces, cada una por separado**:

1. Una vez en **Safari** — es la que usan los Atajos, porque "Abrir URL" siempre abre en Safari aunque tengas LIFE instalada (ver Paso 3).
2. Una vez dentro de la **app instalada**, si también la vas a usar desde el ícono en tu pantalla de inicio.

Cada sesión dura 90 días con "recordarme", así que después de iniciar sesión en ambos lados no vas a tener que repetirlo seguido.

## Paso 2 — Armar los 3 Atajos

La app de **Atajos** (Shortcuts) ya viene instalada en el iPhone. Vas a crear tres atajos, uno por cada acción. Son todos iguales salvo la URL.

Para cada uno:

1. Abrí la app **Atajos**.
2. Tocá **+** (arriba a la derecha) para crear un atajo nuevo.
3. Tocá **Agregar acción**, buscá **"Abrir URL"** (o "Open URLs") y agregala.
4. En el campo de la URL, pegá una de estas tres (reemplazando `<dominio-vercel>`):

| Atajo | URL |
| --- | --- |
| Nuevo gasto | `https://<dominio-vercel>/?accion=gasto` |
| Nuevo ingreso | `https://<dominio-vercel>/?accion=ingreso` |
| Editar fijos | `https://<dominio-vercel>/?accion=fijos` |

5. Tocá el nombre del atajo (arriba) y poné **"Nuevo gasto"**, **"Nuevo ingreso"** o **"Editar fijos"** según corresponda.
6. Guardá.

Repetí para los tres. Opcional: si en vez de ir a la pestaña Fijos preferís abrir directo el alta de un fijo nuevo, armá un cuarto atajo con `?accion=fijo` ("Nuevo fijo") en lugar de `?accion=fijos`.

## Paso 3 — Agregarlos a tu pantalla de inicio o a Siri

Para cada atajo, desde la app Atajos:

- **A la pantalla de inicio:** tocá los **•••** del atajo → **Agregar a pantalla de inicio** → elegí un ícono y nombre → **Agregar**. Así te queda un botón más, al lado del de LIFE, que va directo al formulario.
- **A Siri:** un atajo con nombre ya lo podés ejecutar diciendo "Oye Siri, [nombre del atajo]" (por ejemplo, "Oye Siri, Nuevo gasto"). No hace falta grabar ninguna frase aparte: alcanza con el nombre que le pusiste en el paso anterior.

## Cómo funciona por dentro (para que sepas qué esperar)

- La acción "Abrir URL" de Atajos abre el link en **Safari**, no en la app instalada — aunque tengas el ícono de LIFE agregado a la pantalla de inicio. Por eso la sesión que importa para los Atajos es la de Safari (ver "Importante" en el Paso 1), no la de la app instalada.
- Si tenés la sesión iniciada en Safari, el atajo abre directamente el formulario de alta correspondiente (o te lleva a la pestaña Fijos). No hace falta tocar nada más en el dashboard.
- Si todavía no iniciaste sesión en Safari (o la sesión venció — dura 90 días), el atajo te lleva al login y, apenas entrás la contraseña, te devuelve exactamente a donde ibas — no hace falta repetir el `?accion=...` a mano.
- Si la app está en modo de solo lectura (sin conexión en vivo al momento), te va a avisar en pantalla en vez de abrir el formulario a medias.
- Un atajo mal escrito o con un valor que la app no reconoce simplemente no hace nada — no rompe ni muestra un error raro.
