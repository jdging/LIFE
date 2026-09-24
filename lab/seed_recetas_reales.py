"""Seed de recetas REALES de Juan, extraídas de su Notion (ver brief de la tarea).

Reemplaza el seed de ejemplo inventado (milanesas, tallarines, etc.) de la
tarea anterior. Idempotente: borra únicamente `receta_ingredientes` y
`recetas` antes de sembrar (mismo patrón que `seed_recetas_inventario.py`
del repo real) — no toca `gastos`, `estado_conversacional`, `tarjetas`,
`inventario_cocina` ni ninguna otra tabla.

Convenciones de parseo (ver README para el detalle completo):
    - Cuando el texto original da una cantidad numérica clara, se separa en
      `cantidad` (float) + `unidad` (texto corto).
    - Cuando no hay cantidad numérica clara ("a gusto", texto en prosa, etc.),
      `cantidad` queda en None y el texto descriptivo completo va en
      `unidad` (para no perder información sin inventar números).
    - Las recetas con texto narrativo (no lista estructurada) llevan además
      el texto de preparación completo en `notas` de la receta.
"""

import db

DB_PATH = db.DEFAULT_DB_PATH


def limpiar_recetas(conn):
    """Borra solo recetas/receta_ingredientes (idempotente, no toca otras tablas)."""
    conn.execute("DELETE FROM receta_ingredientes")
    conn.execute("DELETE FROM recetas")
    conn.commit()


def cargar_receta(conn, nombre, ingredientes, porciones=None, tiempo_preparacion_min=None, notas=None):
    """Inserta una receta y sus ingredientes.

    `ingredientes` es una lista de tuplas (nombre, cantidad_o_None, unidad_o_texto).
    """
    receta_id = db.insert_receta(
        conn,
        {
            "nombre": nombre,
            "porciones": porciones,
            "tiempo_preparacion_min": tiempo_preparacion_min,
            "notas": notas,
            "activa": True,
        },
    )
    for ingrediente_nombre, cantidad, unidad in ingredientes:
        db.insert_receta_ingrediente(
            conn,
            {
                "receta_id": receta_id,
                "ingrediente_nombre": ingrediente_nombre,
                "cantidad": cantidad,
                "unidad": unidad,
            },
        )
    return receta_id


def seed(conn):
    limpiar_recetas(conn)

    # 1. Salmorejo cordobés (Entrada) — texto libre, prosa
    cargar_receta(
        conn,
        "Salmorejo cordobés",
        [
            ("tomate", 4, "unidad"),
            ("pan", 4, "unidad (~6-7cm de largo y diámetro)"),
            ("ajo", None, "1-2 dientes (Juan dice: mejor con solo un ajito chiquito)"),
            ("aceite de oliva", 0.5, "vaso tipo café expreso"),
            ("sal", None, "a gusto (Juan dice: mejor con menos sal)"),
            ("huevo", 2, "unidad"),
            ("jamón crudo", None, "a gusto"),
            ("perejil", None, "a gusto"),
        ],
        porciones=4,
        notas=(
            "Texto original de Juan: 'Agarré 4 tomates, como 4 panes de 6/7 cm de largo y "
            "4 de diámetro. 2 ajitos (1 grande y otro chico, a lo mejor era 1 grande nada "
            "más). Medio vasito de café de Regi tipo expreso de aceite de oliva. Sal. 2 "
            "huevos, jamón crudo y perejil.' Nota de mejora de Juan: 'Era mejor con solo "
            "un ajito chiquito y menos sal.'"
        ),
    )

    # 2. Salsa Pinki
    cargar_receta(
        conn,
        "Salsa Pinki",
        [
            ("zanahoria", 2, "mediana, en cubos pequeños"),
            ("pimiento (rojo y/o verde)", 2, "mediano, en cubos"),
            ("apio", 2.5, "rama, en rodajitas finas (2-3)"),
            ("cebolla", 1, "grande"),
            ("ajo", 2.5, "diente, picado (2-3)"),
            ("tomate maduro", 11, "unidad (10-12, o 1.5-2 kg)"),
            ("aceite de oliva", 3.5, "cucharada (3-4)"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("laurel", 1, "hoja (opcional)"),
            ("orégano seco o tomillo", 1, "cucharadita"),
            ("albahaca fresca o seca", None, "un puñadito (opcional, al final)"),
            ("azúcar o miel", 1, "cucharadita (opcional, para balancear acidez)"),
        ],
        porciones=5,
        notas=(
            "Rinde 500-600g de pasta seca (5 personas). Preparación: sofrito de "
            "cebolla+ajo, sumar zanahoria+apio 5min, sumar pimientos 5-7min, agregar "
            "tomates+laurel+orégano+sal+pimienta, cocinar 45min-1h a fuego bajo "
            "semitapado, ajustar sazón, opcional procesar, agregar albahaca al final."
        ),
    )

    # 3. Salsita de hojas de apio
    cargar_receta(
        conn,
        "Salsita de hojas de apio",
        [
            ("hojas de apio frescas", None, "un buen puñado"),
            ("ajo", 1, "diente"),
            ("ralladura y jugo de limón", 0.5, "limón"),
            ("aceite de oliva", 3.5, "cucharada (3-4)"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("perejil o albahaca", None, "opcional"),
        ],
        porciones=1,
        notas=(
            "Preparación: lavar hojas de apio, picar ajo fino, triturar (mortero o "
            "procesador) apio+ajo+ralladura+jugo limón+sal, incorporar aceite de a poco "
            "emulsionando, ajustar acidez. Nota de mejora real de Juan (variante "
            "mencionada por él, texto parcialmente ambiguo en el original — 'lote en "
            "Polo polvo' — se guarda tal cual): 'La receta quedó mucho mejor cuando puse "
            "hojas de apio, limón, jengibre, un poquito de ajo, lo trituré todo, un "
            "chorrito o dos de aceite de oliva y finalmente le tiré miel y un toque de "
            "polvo de oro/algo (lote en Polo polvo).'"
        ),
    )

    # 4. Sopa de calabaza — prosa
    cargar_receta(
        conn,
        "Sopa de calabaza",
        [
            ("cebolla", 1, "grande, cortada"),
            ("manteca", None, "para dorar"),
            ("zapallo", None, "para cortar y hervir (pelar después de hervido)"),
            ("agua", None, "hasta consistencia de crema"),
            ("leche de coco", None, "hasta consistencia de crema"),
            ("jengibre", None, "a gusto"),
            ("curry", None, "a gusto"),
            ("cebolla de verdeo", None, "para servir arriba"),
            ("queso crema", None, "para servir arriba"),
        ],
        porciones=4,
        notas=(
            "Preparación: dorar cebolla con manteca, hervir zapallo y pelarlo, agregar "
            "agua+leche de coco hasta consistencia crema, agregar jengibre y curry, "
            "procesar, servir con cebolla de verdeo y queso crema arriba."
        ),
    )

    # 5. Tutancamón (Postre — receta de Lula)
    cargar_receta(
        conn,
        "Tutancamón",
        [
            ("leche", 2, "litro"),
            ("yema de huevo", 5, "unidad"),
            ("clara de huevo", 5, "unidad"),
            ("maicena", 10, "cucharada"),
            ("azúcar", 10, "cucharada"),
            ("esencia de vainilla", 2, "cucharada de té"),
            ("colorante amarillo", 1, "cucharada de té"),
        ],
        porciones=8,
        notas=(
            "Receta de Lula. Preparación: calentar 1.5L de leche, mezclar maicena con "
            "leche restante sin grumos, volcar a la olla revolviendo, agregar yemas "
            "mezcladas, agregar azúcar+vainilla+colorante, mezclar hasta que espese más "
            "que mayonesa, hervir 5 minutos más."
        ),
    )

    # 6. Corazones de alcaucil
    cargar_receta(
        conn,
        "Corazones de alcaucil",
        [
            ("corazones de alcaucil", None, "a gusto"),
            ("cebolla blanca", None, "a gusto"),
            ("panceta ahumada", None, "a gusto"),
            ("vino blanco", 1, "vaso, aprox"),
            ("maicena", 2, "cucharada"),
            ("sal", None, "a gusto"),
        ],
        porciones=4,
        notas=(
            "Preparación: rehogar cebolla a fuego mínimo sin dorar, agregar panceta "
            "hasta cebolla blanda, incorporar corazones de alcaucil cortados por mitad, "
            "espolvorear con maicena, verter vino blanco revolviendo constantemente "
            "hasta espesar."
        ),
    )

    # 7. Crema de alcaparras — texto muy libre
    cargar_receta(
        conn,
        "Crema de alcaparras",
        [
            ("alcaparras", None, "a gusto"),
            ("ajo", None, "a gusto"),
            ("jengibre", None, "a gusto"),
            ("hierbas de Provenza", None, "a gusto"),
            ("limón (jugo)", None, "chorrito"),
            ("aceite de oliva", None, "chorrito"),
            ("crema de leche", None, "a gusto"),
        ],
        porciones=1,
        notas=(
            "Texto original literal de Juan (prosa): 'alcaparras ajo jengibre hierba de "
            "la Provenza chorrito de limón y aceite y obviamente crema'."
        ),
    )

    # 8. Ensalada Pinki (ensalada keppe)
    cargar_receta(
        conn,
        "Ensalada Pinki",
        [
            ("repollo morado", None, "a gusto"),
            ("cebolla morada", None, "rallada, a gusto"),
            ("manzana", None, "rallada, a gusto"),
            ("tomate o cherrys", None, "a gusto"),
            ("aceite de oliva", None, "para condimentar"),
            ("vinagre de manzana", None, "para condimentar"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
        ],
        porciones=4,
        notas=(
            "Ensalada keppe. Nota original de Juan (así, tal cual, aparenta referirse a "
            "'el pollo' pero podría ser un error de dictado/transcripción por 'la "
            "cebolla'; se guarda literal): 'El pollo, la cebolla y la manzana ralladas.'"
        ),
    )

    # 9. Espárragos limón
    cargar_receta(
        conn,
        "Espárragos limón",
        [
            ("espárragos", None, "a gusto"),
            ("limón", None, "en rodajas"),
            ("manteca", None, "un poquito"),
            ("aceite de oliva", None, "un poquito"),
            ("ajo", None, "cortadito"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
        ],
        porciones=2,
        notas=(
            "Preparación: cocinar espárragos solos en sartén, cuando oscurecen agregar "
            "rodajas de limón, manteca, aceite, salpimentar y agregar ajo cortadito, "
            "sacar cuando estén cocinaditos."
        ),
    )

    # 10. Hamburguesa
    cargar_receta(
        conn,
        "Hamburguesa",
        [
            ("carne (100% roast beef)", 600, "g"),
            ("panceta ahumada", 100, "g (evitar marca Paladini)"),
            ("cheddar", 11, "feta (10-12, marca Milkaut o Tonadita)"),
            ("pan de papa Bimbo", 1, "paquete"),
            ("cebolla morada", None, "a gusto"),
            ("lechuga", None, "a gusto"),
            ("tomate", None, "a gusto"),
            ("pepino agridulce", None, "a gusto"),
            ("mayonesa", None, "a gusto"),
            ("ketchup", None, "a gusto"),
        ],
        porciones=6,
        notas="Rinde 6 hamburguesas de 100g cada una.",
    )

    # 11. Kebab + acompañamientos
    cargar_receta(
        conn,
        "Kebab con acompañamientos",
        [
            ("carne picada especial", 1, "kg"),
            ("cebolla", 1, "mediana, picada chica"),
            ("perejil", None, "un buen puñado (~5 cucharadas)"),
            ("cilantro", None, "la mitad de la cantidad de perejil"),
            ("menta", 8, "hoja, picada"),
            ("sal", None, "a gusto"),
            ("baharat", 2, "cucharadita"),
            ("nuez moscada", 0.5, "cucharadita"),
            ("comino", 1, "cucharadita"),
            ("gelatina sin sabor", 2, "sobrecito chico"),
            ("pan pita (laffa)", None, "a gusto"),
            ("hummus", None, "comprado o casero, sin detalle"),
            ("tahini", 0.5, "pote"),
            ("ajo (para tahinia)", 2, "diente, picado"),
            ("limón (para tahinia)", None, "a gusto"),
            ("sal (para tahinia)", None, "a gusto"),
            ("tomate perita (ensalada de pepino)", None, "picado chico"),
            ("perejil (ensalada de pepino)", None, "picado chico"),
            ("cebolla (ensalada de pepino)", None, "picada chica"),
            ("trigo burgol", None, "hidratado"),
        ],
        porciones=7,
        notas=(
            "Rinde 6-8 porciones con 1kg de carne. Acompañamientos incluidos en la misma "
            "receta: tahinia (textura cremosa tipo pasta de dientes) y ensalada de pepino "
            "con trigo burgol."
        ),
    )

    # 12. Zanahoria glaseada
    cargar_receta(
        conn,
        "Zanahoria glaseada",
        [
            ("zanahoria", None, "cortada en rodajas"),
            ("manteca", None, "un trozo"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("miel", 1, "cucharada"),
            ("jengibre", None, "en trozos"),
        ],
        porciones=4,
        notas=(
            "Preparación: cocinar zanahoria en rodajas con manteca en ollita, cuando "
            "esté medio cocida agregar miel y salpimentar, hacia el final agregar "
            "jengibre en trozos."
        ),
    )

    # 13. Yogurt casero
    cargar_receta(
        conn,
        "Yogurt casero",
        [
            ("leche entera", 1, "litro (marca sugerida: Milkout o sachet con vaca en el envase)"),
            ("yogurt natural (fermento)", 100, "g (marca sugerida: La Serenísima natural, el celeste)"),
        ],
        porciones=1,
        notas=(
            "Rinde ~1 litro. Preparación: calentar leche a 48°C (hasta que no aguantes "
            "un dedo sumergido más de 8 segundos), sacar del fuego, agregar el yogurt, "
            "mezclar bien, tapar la olla, envolver en toalla, guardar en horno apagado "
            "12-16 horas, colar con tela/repasador dentro de la heladera para sacar el "
            "suero (10h+ para más firmeza)."
        ),
    )

    # 14a. Coliflor Gratinada
    cargar_receta(
        conn,
        "Coliflor Gratinada",
        [
            ("coliflor", 1, "grande"),
            ("crema de leche o leche", 1, "taza"),
            ("queso rallado (mozzarella/parmesano o mezcla)", 1, "taza"),
            ("pan rallado", 0.5, "taza"),
            ("manteca derretida", 2.5, "cucharada (2-3)"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("nuez moscada", None, "opcional, a gusto"),
        ],
        porciones=4,
        notas=(
            "Preparación: cocinar coliflor al vapor/hervido 5-7min, hacer salsa de "
            "crema+queso, armar en fuente, cubrir con pan rallado+manteca, hornear 180°C "
            "20-25min."
        ),
    )

    # 14b. Coliflor al Horno con Especias
    cargar_receta(
        conn,
        "Coliflor al Horno con Especias",
        [
            ("coliflor", 1, "grande"),
            ("aceite de oliva", 3, "cucharada"),
            ("cúrcuma", 1, "cucharadita"),
            ("comino", 1, "cucharadita"),
            ("pimentón dulce", 1, "cucharadita"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("cilantro fresco", None, "opcional, decoración"),
        ],
        porciones=4,
        notas=(
            "Preparación: mezclar aceite+especias, cubrir floretes, hornear 200°C "
            "25-30min."
        ),
    )

    # 15a. Coliflor Salteada con Ajo y Limón
    cargar_receta(
        conn,
        "Coliflor Salteada con Ajo y Limón",
        [
            ("coliflor", 1, "grande"),
            ("ajo", 2.5, "diente picado (2-3)"),
            ("aceite de oliva", 2.5, "cucharada (2-3)"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("limón (jugo)", 1, "limón"),
            ("perejil o cilantro", None, "opcional, decoración"),
        ],
        porciones=4,
        notas=(
            "Preparación: saltear coliflor en aceite 7-10min hasta dorar, agregar ajo "
            "1-2min, sazonar, agregar jugo de limón."
        ),
    )

    # 15b. Coliflor Salteada con Salsa de Soja y Jengibre
    cargar_receta(
        conn,
        "Coliflor Salteada con Salsa de Soja y Jengibre",
        [
            ("coliflor", 1, "grande"),
            ("aceite de sésamo (o de oliva)", 2.5, "cucharada (2-3)"),
            ("ajo", 2.5, "diente picado (2-3)"),
            ("jengibre fresco rallado", 1, "cucharada"),
            ("salsa de soja (o tamari)", 2.5, "cucharada (2-3)"),
            ("miel", 1, "cucharadita (opcional)"),
            ("cebollín o cilantro", None, "opcional, decoración"),
        ],
        porciones=4,
        notas=(
            "Preparación: saltear coliflor 5-7min, agregar ajo+jengibre 1-2min, agregar "
            "soja+miel, cocinar 2-3min más."
        ),
    )

    # 16. Caldo de huesos
    cargar_receta(
        conn,
        "Caldo de huesos",
        [
            ("agua mineral", 2, "litro"),
            ("huesos (caña, rodilla, costilla de ternera)", 1, "kg"),
            ("sal", 12, "gramo"),
            ("vinagre", None, "opcional, chorrito (ayuda a liberar minerales)"),
        ],
        porciones=1,
        notas=(
            "Rinde ~2 litros de caldo base. Preparación: cubrir huesos con agua fría, "
            "hervor mínimo (burbujas chicas), espumar impurezas al principio, cocinar "
            "8-12h (pollo) o 12-24h (vaca)."
        ),
    )

    # 17. Caldo / sopa con fideos
    cargar_receta(
        conn,
        "Caldo con fideos",
        [
            ("huesos de pollo", None, "a gusto"),
            ("apio", None, "a gusto"),
            ("cebolla", None, "a gusto"),
            ("zanahoria", None, "a gusto"),
            ("jengibre", None, "a gusto"),
            ("ajo", None, "a gusto"),
            ("cúrcuma", None, "a gusto"),
            ("pimienta negra", None, "a gusto"),
            ("sal", None, "a gusto"),
            ("fideos de arroz", None, "a gusto"),
            ("huevo", None, "duro o batido, a gusto"),
            ("aceite de oliva", None, "chorrito"),
            ("limón (jugo)", None, "a gusto"),
            ("verde (espinaca, puerro o zucchini)", None, "opcional"),
        ],
        porciones=4,
        notas=(
            "Caldo base + extras para la sopa final. Notas adicionales sobre verduras "
            "compatibles mencionadas por Juan: zanahoria no enturbia el caldo, puerro "
            "(parte blanca y verde clara) es excelente, evitar semillas de chía en el "
            "caldo (forma gel viscoso), otras opciones: zucchini, espinaca/acelga (al "
            "final), repollo, hongos (shiitake/champiñón para umami), brotes de soja (al "
            "final)."
        ),
    )

    # 18. Puré de raíces con ajo asado (acompañamiento para ojo de bife)
    cargar_receta(
        conn,
        "Puré de raíces con ajo asado",
        [
            ("camote", 1, "mediano"),
            ("batata", 1, "mediana"),
            ("papa", 2, "mediana"),
            ("zanahoria", 2, "grande"),
            ("remolacha", 1, "mediana, opcional"),
            ("ajo", 1, "cabeza entera (asada)"),
            ("manteca", 2, "cucharada"),
            ("crema de leche", 50, "ml"),
            ("nuez moscada", None, "una pizca"),
            ("sal", None, "a gusto"),
            ("pimienta", None, "a gusto"),
            ("perejil fresco", None, "decoración"),
            ("nueces tostadas", None, "opcional, decoración"),
            ("aceite de oliva virgen extra", None, "para asar el ajo y decorar"),
        ],
        porciones=4,
        notas=(
            "Acompañamiento para ojo de bife (receta separada). Preparación: asar ajo "
            "(y remolacha opcional) envueltos en papel aluminio en freidora de aire "
            "190°C 45-60min; hervir camote+batata+papas+zanahoria 15-20min hasta "
            "tiernos; combinar todo con ajo asado pelado, manteca, crema, nuez moscada; "
            "triturar; sazonar; decorar."
        ),
    )

    # 19. Ojo de bife
    cargar_receta(
        conn,
        "Ojo de bife",
        [
            ("ojo de bife", 350, "g por persona (300-400g)"),
            ("sal gruesa", None, "a gusto"),
            ("pimienta negra recién molida", None, "a gusto"),
            ("aceite de oliva o girasol", None, "alto punto de humo"),
            ("hierbas provenzales", None, "opcional"),
        ],
        porciones=1,
        notas=(
            "Cantidades por persona — escalar según comensales. Preparación: sacar de "
            "la heladera 30min antes, secar bien, sazonar, calentar sartén de hierro a "
            "fuego medio-alto con aceite, sellar 3-4min por lado (término medio), "
            "reposar 5min antes de cortar."
        ),
    )

    # 20. Panchitos con "cebolla" alemana y salsa picante-arábiga
    cargar_receta(
        conn,
        "Panchitos con cebolla alemana y salsa picante-arábiga",
        [
            ("salchicha tipo alemana", 4, "unidad"),
            ("pan para pancho", 4, "unidad"),
            ("pepinillos en vinagre", 3, "unidad, picados"),
            ("queso (hebras o fetas finas)", None, "a gusto"),
            ("cebolla morada", 1, "en cubitos, remojada en agua fría"),
            ("cebolla de verdeo (parte verde)", None, "picada"),
            ("ají putaparió", 1, "unidad, picado fino"),
            ("alcaparras", 1, "cucharadita"),
            ("salsa de tomate", 3, "cucharada"),
            ("salsa barbacoa", 1, "cucharadita"),
            ("curry", 0.5, "cucharadita"),
            ("condimento árabe (baharat o similar)", 0.5, "cucharadita"),
            ("aceite de oliva", None, "para saltear"),
        ],
        porciones=4,
        notas=(
            "Preparación: dorar cebollas en aceite, mezclar con ají+alcaparras+salsas+"
            "curry+condimento, calentar salchichas y tostar panes, armar con "
            "pepinillos+queso+salsa."
        ),
    )

    # 21. Pastichio
    cargar_receta(
        conn,
        "Pastichio",
        [
            ("macarrones", 400, "g"),
            ("carne de cerdo picada", 400, "g"),
            ("carne de ternera picada", 400, "g"),
            ("cebolla", 2, "mediana"),
            ("tomate natural triturado", 800, "g"),
            ("caldo de carne concentrado", 2, "pastilla"),
            ("canela", 1, "cucharada postre"),
            ("vino blanco", 1, "vaso"),
            ("pimienta negra", None, "a gusto"),
            ("aceite de oliva", 2, "cucharada sopera"),
            ("harina de trigo", 10, "cucharada sopera"),
            ("harina de maíz", 5, "cucharada sopera"),
            ("nuez moscada", None, "a gusto"),
            ("queso rallado", 100, "g"),
            ("sal", None, "a gusto"),
            ("leche", 1, "litro"),
            ("huevo", 1, "unidad (para la bechamel)"),
        ],
        porciones=8,
        notas=(
            "Lasaña griega de macarrones. Preparación: cocer macarrones al dente; "
            "sofreír cebolla, agregar caldo desmenuzado+canela+pimienta+carne+vino, "
            "reducir, agregar tomate, cocinar a fuego medio, incorporar macarrones; para "
            "bechamel calentar leche, agregar harinas disueltas en un vaso de leche "
            "fría, espesar, agregar huevo batido+nuez moscada+sal; armar en fuente "
            "(boloñesa+macarrones, cubrir con bechamel, queso rallado encima), hornear "
            "180°C 30-40min."
        ),
    )

    # 22. Pho Bo
    cargar_receta(
        conn,
        "Pho Bo",
        [
            ("huesos de médula/rodilla", 1.13, "kg"),
            ("agua", None, "8-12 vasos"),
            ("cebolla", 1, "grande"),
            ("jengibre", None, "1 trozo grande"),
            ("ajo", 3, "diente"),
            ("azúcar", 1, "cucharada"),
            ("salsa de pescado", 3, "cucharada"),
            ("semillas de cilantro", None, "para la bolsita de especias (tostar antes)"),
            ("semillas de hinojo", None, "para la bolsita de especias (tostar antes)"),
            ("canela en barra", None, "para la bolsita de especias (tostar antes)"),
            ("anís estrellado", None, "para la bolsita de especias (tostar antes)"),
            ("cardamomo", None, "para la bolsita de especias (tostar antes)"),
            ("fideos de arroz", None, "hidratados"),
            ("lomo de vaca", None, "en láminas finas, se cocina con el calor del caldo"),
            ("cilantro fresco", None, "a gusto"),
            ("cebolla de verdeo", None, "picada"),
            ("brotes de soja", None, "topping"),
            ("lima", None, "gajos, topping"),
            ("chile", None, "en rodajitas, topping"),
        ],
        porciones=4,
        notas="Sopa vietnamita de fideos de arroz con carne.",
    )

    # 23. Puré de vegetales
    cargar_receta(
        conn,
        "Puré de vegetales",
        [
            ("zanahoria", 2, "grande"),
            ("calabaza", 300, "g"),
            ("batata", 1, "mediana"),
            ("papa", 2, "mediana"),
            ("queso crema", 2, "cucharada"),
            ("manteca", 1, "cucharada"),
            ("ajo asado", 1, "diente, opcional"),
            ("crema de leche", 0.25, "taza, opcional"),
            ("sal", None, "a gusto"),
            ("pimienta negra", None, "a gusto"),
            ("nuez moscada", None, "opcional, a gusto"),
        ],
        porciones=4,
        notas=(
            "Zanahoria, calabaza, batata y papa. Preparación: pelar y cortar en cubos "
            "todo, hervir 20-25min hasta tiernos, escurrir, aplastar, mezclar con "
            "manteca+queso crema+(ajo asado+crema si se usan), sazonar."
        ),
    )

    # 24. Limoncello clásico
    cargar_receta(
        conn,
        "Limoncello clásico",
        [
            ("limón", 8, "unidad (6 a 10, solo cáscara, sin parte blanca)"),
            ("alcohol etílico alimentario", 500, "ml"),
            ("agua", 1.2, "litro"),
            ("azúcar", 1, "kg"),
        ],
        porciones=1,
        notas=(
            "Rinde ~4.7L por litro de alcohol usado. Preparación: pelar limones en "
            "tiras, macerar cáscaras con alcohol en frasco hermético 30 días en lugar "
            "fresco y oscuro; hervir agua+azúcar hasta disolver, enfriar; colar alcohol "
            "macerado, mezclar con almíbar frío; envasar, guardar en freezer."
        ),
    )

    # 25. Limoncello cremoso
    cargar_receta(
        conn,
        "Limoncello cremoso",
        [
            ("limón", 8, "unidad, solo cáscara"),
            ("crema de leche", 1, "litro"),
            ("leche", 0.5, "litro"),
            ("azúcar", 1, "kg"),
            ("alcohol etílico alimentario", 0.5, "litro"),
            ("vainilla (chaucha o esencia)", None, "a gusto"),
        ],
        porciones=1,
        notas=(
            "Rinde ~5.3L por litro de alcohol usado. Preparación: macerar cáscaras en "
            "alcohol 30 días; hervir leche+crema+vainilla, retirar vainilla, enfriar un "
            "poco, agregar azúcar hasta disolver, enfriar completo; colar alcohol, "
            "mezclar con la base cremosa; embotellar; madurar en freezer 1 mes antes de "
            "consumir."
        ),
    )


def main():
    conn = db.get_connection(DB_PATH)
    try:
        db.init_db(conn)
        seed(conn)
        total = conn.execute("SELECT COUNT(*) AS n FROM recetas").fetchone()["n"]
        print(f"Seed completo: {total} recetas cargadas en {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
