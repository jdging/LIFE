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


@dataclass
class GastoFijo:
    """Gasto recurrente, portado de la hoja `GastosFijos`.

    Versionado real (ver README sección "Versionado de fijos", t_85b8502b):
    cada cambio de monto crea una fila NUEVA con `vigente_desde` propio, en
    vez de pisar la anterior.

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
