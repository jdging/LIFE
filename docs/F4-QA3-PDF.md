# F4-QA3 · PDF de supermercado

## Alcance implementado

El generador prepara y mide las filas canónicas del backend antes de dibujar el PDF. Conserva su orden, las cantidades y unidades recibidas, y el filtro `a_comprar > 0`. La planificación agrupa bloques de categoría e ítem por columna; cada encabezado se mide junto con el primer ítem para que no quede huérfano. Si una categoría sigue en otra columna o página, se repite con `(CONT.)`. No se balancean columnas ni se sintetizan filas.

Después de conocer las columnas ocupadas **en cada página**, el generador centra geométricamente el grupo de ancho fijo: una columna centrada, dos columnas centradas con separación de 12 pt y tres columnas en los márgenes originales de 30 pt. La última página se trata igual. El ancho de columna sigue siendo `(595,28 - 2 × 30 - 2 × 12) / 3 = 170,43 pt`. La hoja sigue siendo A4 vertical. El área de ítems comienza a 101 pt del borde superior y termina a 30 pt del inferior, para reservar espacio al encabezado.

El encabezado reutiliza el nombre LIFE y el acento existente `#8fb87a`. Título serif, texto de compra y metadatos monoespaciados, categoría verde oscuro y líneas finas generan jerarquía sin fondo oscuro ni áreas de tinta extensas. Para lectura impresa, los textos usan la tinta oscura y el verde oscuro presentes en la estética del dashboard. Se usan Times, Courier y Helvetica incorporadas en ReportLab; no se descargan ni agregan fuentes. La codificación CP1252 conserva su límite previo: caracteres fuera de ese repertorio se sustituyen.

## Pruebas y revisión pendientes de ejecución

El implementador **no ejecutó** la suite ni generó PDFs desde este wrapper. El coordinador puede correr desde el workdir candidato, con ReportLab instalado:

```bash
PYTHONPATH=lab TMPDIR=/tmp python -m unittest discover -s lab/tests -p 'test_supermercado*.py'
PYTHONPATH=lab python lab/generar_demo_supermercado.py --out /tmp/f4-qa3-pdf
```

Los cinco archivos sintéticos reproducibles son `f4-qa3-1-columna.pdf`, `f4-qa3-2-columnas.pdf`, `f4-qa3-3-columnas.pdf`, `f4-qa3-ultima-1-columna.pdf` y `f4-qa3-ultima-2-columnas.pdf`. Las dos últimas listas ocupan dos páginas y dejan una o dos columnas en la página final. El script no consulta DB, API ni datos reales.

La suite comprueba centro geométrico exacto para 1/2/3 columnas y páginas finales parciales, 120 caracteres de categoría/producto, unidad de 24 caracteres, 1000 filas, ausencia de páginas vacías, categoría antes del primer producto de cada columna, continuidad, orden, cantidad y stocks. También verifica el encabezado LIFE, el color verde, la ausencia de rectángulos rellenos y que el generador no solicite archivos temporales. Si PyMuPDF está disponible, comprueba A4, extracción de texto y casillas del PDF real. El coordinador debe contrastar los rectángulos y límites de texto con PyMuPDF y revisar visualmente los cinco demos, especialmente la legibilidad en escala de grises y la última página.

## Límites y aceptación

`build_pdf` devuelve bytes en memoria; no escribe archivos. Los demos solo escriben en el directorio indicado por `--out` o, si se omite, en un subdirectorio del temporal del sistema. No se modificaron API, servicio, DB, datos reales, recetas, infraestructura ni despliegue. La revisión independiente y la aceptación visual de Juan están pendientes. Una identidad visual nueva requeriría decisión de R.P.; esta entrega usa la marca y los tokens ya existentes.
