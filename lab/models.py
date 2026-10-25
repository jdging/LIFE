"""Estructuras de datos usadas por el bot Lasso (Fase 1)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Gasto:
    """Equivalente al "Log" de Finanzas, según LIFE-lab-propuesta.md sección 3."""

    monto: float
    moneda: str = "ARS"  # no se pregunta activamente en Fase 1, default ARS
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    descripcion_original: Optional[str] = None
    medio_pago: Optional[str] = None
    # JD/Pinki en el documento aprobado; no se pregunta en Fase 1 (TODO Fase 2/3).
    pagado_por: str = "Común"
    origen: str = "texto"  # Fase 1 = solo texto; "audio" queda para Fase 2
    chat_id: Optional[str] = None
    confirmado: bool = False
    fecha: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    # Tarjeta usada (opcional, FK a `tarjetas`) y reparto del costo entre
    # JD/Pinki — independiente de `pagado_por` (quién puso la plata). Ver
    # README sección "Tarjetas y reparto".
    tarjeta_id: Optional[str] = None
    tipo_proporcion: str = "dinamico"  # 'dinamico' o 'custom'
    proporcion_jd: Optional[float] = None
    proporcion_pinki: Optional[float] = None
    # Soft delete (ver README sección "Soft delete de gastos"): fecha ISO
    # del borrado lógico y quién lo ejecutó, o None si sigue activo.
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
    # Telegram (brief S2/S3, T1): quién mandó el mensaje y cuál fue
    # ('chat_id' ya existía). Permiten trazabilidad y vincular
    # `ComprobanteTelegram` sin volver a preguntar.
    telegram_user_id: Optional[str] = None
    telegram_message_id: Optional[str] = None


@dataclass
class Ingreso:
    """Movimiento de ingreso (Salario/Extra/Freelance/Otro), tabla hermana de
    `Gasto`. A diferencia de `Gasto.pagado_por`, `persona` no admite 'Común':
    un ingreso siempre es de una persona concreta (ver `validaciones.py`)."""

    monto: float
    categoria: str
    persona: str  # 'JD' o 'Pinki'
    moneda: str = "ARS"
    descripcion_original: Optional[str] = None
    origen: str = "texto"
    confirmado: bool = False
    fecha: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    # Telegram (brief S2/S3, T1): a diferencia de `Gasto`, `Ingreso` no
    # tenía ningún campo de Telegram todavía -- se agregan los tres.
    chat_id: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_message_id: Optional[str] = None


@dataclass
class GastoFijo:
    """Gasto recurrente, portado de la hoja `GastosFijos`.

    Versionado real (ver README sección "Versionado de fijos", t_85b8502b):
    cada cambio de descripción, monto, periodicidad o responsable crea una
    fila NUEVA con `vigente_desde` propio. La baja también es una versión.

    Identidad de la serie (corrección tras dictamen NO APTO del revisor
    independiente, run 3b184396, hallazgo 4): todas las versiones de un
    mismo gasto fijo comparten `fijo_grupo_id` — NO `nombre` (que puede
    repetirse entre gastos fijos distintos o cambiar al renombrar sin perder
    la identidad de la serie).
    """

    nombre: str
    monto_estimado: float
    periodicidad: str
    vigente_desde: str  # 'YYYY-MM-DD', desde cuándo esta versión es válida
    # 'Común' / 'JD' / 'Pinki' — OPCIONAL: compatibilidad legacy con
    # `reference/db.py`, donde siempre fue opcional con default NULL (ver
    # README sección "responsable TEXT: opcional"). Si no se pasa, queda
    # `None` tal cual; esta capa no le inventa un dueño a un fijo legacy que
    # nunca lo tuvo.
    responsable: Optional[str] = None
    fijo_grupo_id: Optional[int] = None  # identidad estable de la serie
    dia_vencimiento: Optional[int] = None
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    activo: bool = True
    ultima_actualizacion: Optional[str] = None
    tipo_proporcion: Optional[str] = None
    proporcion_jd: Optional[float] = None
    medio_pago: Optional[str] = None
    id: Optional[int] = None


@dataclass
class Tarjeta:
    """Catálogo de tarjetas, portado de la hoja `Tarjetas` del sistema real.

    Extensión deliberada de esta tarea: `titular` acepta 'Común' además de
    'JD'/'Pinki' (tarjeta de la cuenta conjunta), ver README.
    """

    id: str
    nombre: str
    tipo: str  # 'Crédito' o 'Débito'
    titular: str  # 'JD' / 'Pinki' / 'Común' — dueño legal/nominal
    banco: Optional[str] = None
    dia_cierre: Optional[int] = None  # solo crédito
    dia_vencimiento: Optional[int] = None  # solo crédito
    es_default_dinamico: bool = False
    # Independiente de `titular`: si ambos usan la tarjeta habitualmente
    # aunque el titular sea uno solo (ver README).
    uso_compartido: bool = False


@dataclass
class EstadoConversacional:
    """Borrador de un intent en curso para `(telegram_chat_id, usuario)`.

    Desde el brief S2/S3 (T1), la identidad es compuesta: dos usuarios del
    mismo chat tienen borradores independientes (`UNIQUE(telegram_chat_id,
    usuario)` en `db.py`, ver `set_estado`/`get_estado`/`clear_estado`).
    """

    telegram_chat_id: str
    estado: str
    campo_pendiente: Optional[str] = None
    payload_parcial: Optional[dict] = None
    mensaje_original: Optional[str] = None
    usuario: Optional[str] = None  # JD/Pinki; None = borrador sin usuario identificado
    intent_detectado: str = "gasto"
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class ComprobanteTelegram:
    """Comprobante (foto/PDF) de un gasto/ingreso ingresado por Telegram
    (brief S2/S3, T1). `hash_archivo` es la clave de dedupe exacta (ver
    `db.buscar_comprobante_dedupe`); `gasto_id`/`ingreso_id` son mutuamente
    excluyentes en la práctica -- un comprobante vincula a lo sumo uno de
    los dos."""

    hash_archivo: str
    chat_id: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_message_id: Optional[str] = None
    texto_extraido: Optional[str] = None
    monto_detectado: Optional[float] = None
    fecha_detectada: Optional[str] = None
    comercio_detectado: Optional[str] = None
    ruta_archivo: Optional[str] = None
    gasto_id: Optional[int] = None
    ingreso_id: Optional[int] = None
    id: Optional[int] = None
    creado_en: Optional[str] = None


@dataclass
class AvisoCredito:
    """Umbral de gasto en crédito detectado para un mes calendario (brief
    S2/S3, T1/T2). Esta API no tiene token de Telegram, así que solo
    DETECTA y registra (`enviado_en=None`); el envío y el marcado como
    enviado los hace Lasso vía `POST /api/avisos-credito/marcar-enviados`
    (ver `db.detectar_umbrales_credito`/`db.marcar_avisos_credito_enviados`,
    cambio respecto del CTO 66f52e78 documentado en DECISIONES.md)."""

    mes: str  # 'YYYY-MM'
    umbral: int
    total_al_detectar: float
    detectado_en: str
    enviado_en: Optional[str] = None
