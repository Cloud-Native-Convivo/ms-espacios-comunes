"""Esquemas del administrador de Kafka (/api/v1/kafka)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Caracteres que Kafka acepta en un nombre de tópico (máximo 249).
PATRON_NOMBRE_TOPICO = r"^[A-Za-z0-9._-]{1,249}$"
# El cluster local y el de la demo tienen 3 brokers.
MAX_BROKERS = 3


class ConfiguracionTopico(BaseModel):
    """Configuraciones editables; None = no se toca."""

    retencion_ms: int | None = Field(None, ge=-1, description="-1 = sin límite de tiempo")
    cleanup_policy: Literal["delete", "compact", "compact,delete"] | None = None
    min_insync_replicas: int | None = Field(None, ge=1, le=MAX_BROKERS)


class CrearTopicoRequest(ConfiguracionTopico):
    nombre: str = Field(pattern=PATRON_NOMBRE_TOPICO)
    particiones: int = Field(3, ge=1, le=50)
    factor_replicacion: int = Field(MAX_BROKERS, ge=1, le=MAX_BROKERS)

    @model_validator(mode="after")
    def _isr_no_supera_replicas(self):
        if self.min_insync_replicas and self.min_insync_replicas > self.factor_replicacion:
            raise ValueError("min_insync_replicas no puede superar factor_replicacion")
        return self


class ActualizarConfiguracionRequest(ConfiguracionTopico):
    @model_validator(mode="after")
    def _al_menos_un_campo(self):
        if all(valor is None for valor in self.model_dump().values()):
            raise ValueError("Indica al menos una configuración a modificar")
        return self


class TopicoResponse(BaseModel):
    nombre: str
    particiones: int
    factor_replicacion: int
    protegido: bool
    # Nombres de Kafka (retention.ms, cleanup.policy, min.insync.replicas) -> valor efectivo.
    configuracion: dict[str, str | None]


class OffsetParticionResponse(BaseModel):
    topico: str
    particion: int
    offset_confirmado: int
    offset_final: int
    lag: int


class ConsumerGroupResponse(BaseModel):
    grupo: str
    lag_total: int
    particiones: list[OffsetParticionResponse]
