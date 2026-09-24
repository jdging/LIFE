# Dashboard LIFE Lab — gastos (datos de ejemplo)

Dashboard 100% estático (HTML/CSS/JS vanilla, sin build) para visualizar gastos cargados
desde `data/gastos.json`. Vive en la rama de laboratorio `lab/reinvencion` (DEC-LAB-001),
pensado para deployarse aparte (ej. Vercel apuntando a esta carpeta) sin tocar el deploy de
producción de LIFE (GitHub Pages, rama `main`, carpeta `src/` del resto del sitio).

## Cómo verlo local
```bash
cd src/lab-dashboard
python3 -m http.server 8000
# abrir http://localhost:8000/index.html
```
(Abrirlo directo con `file://` puede fallar por política de CORS al leer el JSON local —
usar un servidor estático simple como el de arriba.)

## Cómo regenerar los datos de ejemplo
```bash
cd ../../lab
python3 seed_and_export.py
```
Esto sobreescribe `data/gastos.json` de esta carpeta con 20 gastos de ejemplo nuevos.

## Diseño
Dirección editorial/orgánica (pedida explícitamente por Juan: "más refrescante", "más
natural", en vez de clonar el dark-mode del resto de LIFE): paleta papel/verde salvia/
terracota/mostaza, tipografía Fraunces (serif, itálica en títulos) + Work Sans. Contraste de
texto verificado contra WCAG AA.

## Qué falta
- Deploy real (Vercel u otro) — decisión y ejecución de Juan, no de un especialista.
- Conectar `data/gastos.json` a datos reales exportados desde la SQLite del bot conversacional
  (hoy son datos de ejemplo, ver badge "🌱 Datos de ejemplo" en el propio dashboard).
