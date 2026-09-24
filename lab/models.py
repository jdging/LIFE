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
