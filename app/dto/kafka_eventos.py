"""Contratos JSON de los tópicos Kafka de espacios (v1).

Decisiones registradas en la tarjeta Trello #58: espacios.historial.v1 usa
key=espacio_id (orden por espacio) y espacios.alertas.v1 key=condominio_id.
Un cambio incompatible de estos modelos exige tópico .v2, no editar el v1.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

TOPICO_HISTORIAL = "espacios.historial.v1"
TOPICO_ALERTAS = "espacios.alertas.v1"

TipoEventoEspacio = Literal[
    "ESPACIO_CREADO",
    "ESPACIO_ACTUALIZADO",
    "ESPACIO_HABILITADO",
    "ESPACIO_EN_MANTENCION",
    "ESPACIO_DESHABILITADO",
    "RESERVA_CREADA",
    "RESERVA_CONFIRMADA",
    "RESERVA_EXPIRADA",
    "RESERVA_CANCELADA",
]

TipoAlertaEspacio = Literal[
    "ESPACIO_EN_MANTENCION_CON_RESERVAS",
    "RESERVA_CANCELADA_POR_ADMIN",
    "RESERVA_POR_EXPIRAR",
]


class _ContratoKafka(BaseModel):
    """Base común: inmutable, rechaza campos desconocidos y fuerza fechas en UTC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    version: Literal[1] = 1
    ocurrido_en: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("ocurrido_en")
    @classmethod
    def _normalizar_utc(cls, valor: datetime) -> datetime:
        return valor.astimezone(UTC)


class DatosEventoEspacio(BaseModel):
    """Detalle opcional del evento; cada tipo llena solo lo que le aplica."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    estado_anterior: str | None = None
    estado_nuevo: str | None = None
    fecha_inicio: AwareDatetime | None = None
    fecha_fin: AwareDatetime | None = None
    monto: float | None = None


class EventoEspacioV1(_ContratoKafka):
    """Evento del historial de un espacio o de sus reservas (espacios.historial.v1)."""

    tipo: TipoEventoEspacio
    condominio_id: int
    espacio_id: int
    reserva_id: int | None = None
    actor_sub: str | None = None
    datos: DatosEventoEspacio = Field(default_factory=DatosEventoEspacio)

    @property
    def clave(self) -> str:
        return str(self.espacio_id)


class AlertaEspacioV1(_ContratoKafka):
    """Alerta para residentes o administración (espacios.alertas.v1)."""

    tipo: TipoAlertaEspacio
    severidad: Literal["info", "advertencia"]
    condominio_id: int
    espacio_id: int
    reserva_id: int | None = None
    destinatario_sub: str | None = None
    mensaje: str = Field(min_length=1)
    origen_event_id: UUID | None = None

    @property
    def clave(self) -> str:
        return str(self.condominio_id)
