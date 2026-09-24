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
    telegram_chat_id: str
    estado: str
    campo_pendiente: Optional[str] = None
    payload_parcial: Optional[dict] = None
    mensaje_original: Optional[str] = None
    # JD/Pinki; no se identifica activamente en Fase 1 (TODO Fase 2/3).
    usuario: Optional[str] = None
    intent_detectado: str = "gasto"
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
