# F4-QA2 · PDF de supermercado

## Alcance implementado

El generador usa las filas canónicas que entrega el servidor, en su orden original. Filtra únicamente las filas con `a_comprar > 0`. Muestra `producto — Comprar cantidad unidad` y, debajo, `Actual cantidad unidad · Deseado cantidad unidad`. Los tres valores numéricos se toman de la fila recibida; si falta alguno de los dos stocks de un producto a comprar, el generador falla en vez de inventarlo. El faltante vacío conserva `ValueError("No falta nada")`.

## Métricas de página

| Elemento | Medida |
| --- | ---: |
| Hoja | A4 vertical, 595,28 × 841,89 pt |
| Márgenes laterales e inferior | 30 pt |
| Separación entre columnas | 12 pt |
| Columnas | 3 × 170,43 pt |
| Ancho de texto de producto | 156,43 pt, después de la casilla |
| Inicio / fin del área de ítems | 758,89 / 30 pt |
| Altura útil por columna | 728,89 pt |
| Fuente producto / stock / categoría | Helvetica 9 / 8 / Helvetica Bold 9 pt |

El encabezado ocupa todo el ancho y muestra título, fecha UTC, cantidad de productos y número de página. El flujo llena cada columna de arriba abajo y continúa en la siguiente; las tres columnas pueden quedar parcialmente ocupadas si la lista es corta. La cabecera de categoría se mide junto con su primer ítem para evitar títulos huérfanos. Si una categoría continúa en otra columna o página, se repite con `(CONT.)`. El salto de línea usa el ancho real de Helvetica, incluso en palabras sin espacios, categorías y unidades largas.

## Verificación para coordinación

Estos comandos son para ejecutar **desde el workdir candidato** en un entorno que tenga ReportLab. No se ejecutaron desde el wrapper implementador:

```bash
PYTHONPATH=lab TMPDIR=/tmp python -m unittest discover -s lab/tests -p 'test_supermercado*.py'
PYTHONPATH=lab python lab/generar_demo_supermercado.py --out /tmp/f4-qa2-pdf
```

Los demos son sintéticos y están marcados como tales. Revisar `/tmp/f4-qa2-pdf/f4-lista-demo-sintetica.pdf` y `/tmp/f4-qa2-pdf/f4-lista-larga-demo-sintetica.pdf`:

1. Confirmar A4 vertical, tres columnas útiles en la lista larga, flujo de lectura por columna y ausencia de página vacía.
2. Verificar que cada producto tenga una casilla, que cantidad y unidad sigan al nombre, y que “Actual” y “Deseado” conserven valor y unidad.
3. Verificar acentos, categorías extensas, unidades de 24 caracteres, continuación de categoría y que ningún texto o casilla cruce márgenes ni se solape.
4. Extraer texto y rectángulos de ambos PDF con PyMuPDF si está disponible en el venv del coordinador; comparar cantidad de casillas y nombres únicos con las filas sintéticas (3 y 240).
5. Pedir QA visual y aceptación de esta versión a Juan. Las decisiones de identidad visual que excedan estos ajustes técnicos corresponden a R.P.

## Límites

El PDF usa Helvetica incorporada y codificación CP1252; caracteres fuera de ese repertorio se sustituyen. No se agregaron fuentes, paquetes de sistema ni servicios. La lista no recalcula cantidades ni suma unidades. La API, la DB, la autenticación y el contrato HTTP no se modificaron. Esta entrega no implica aceptación de la nueva versión ni despliegue.
