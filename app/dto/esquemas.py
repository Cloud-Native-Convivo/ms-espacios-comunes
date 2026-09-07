import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Espacios ---

class CrearEspacioRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    capacidad: int = Field(..., gt=0, le=5000)
    tarifa_hora: float = Field(default=0.0, ge=0.0, le=10_000_000.0)
    descripcion: str | None = Field(default=None, max_length=1000)
    ubicacion: str | None = Field(default=None, max_length=255)


class ActualizarEspacioRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    capacidad: int | None = Field(default=None, gt=0, le=5000)
    tarifa_hora: float | None = Field(default=None, ge=0.0, le=10_000_000.0)
    descripcion: str | None = Field(default=None, max_length=1000)
    ubicacion: str | None = Field(default=None, max_length=255)
    estado: str | None = Field(
        default=None, pattern="^(activo|inactivo|mantenimiento)$"
    )



class EspacioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None = None
    capacidad: int
    tarifa_hora: float = 0.0
    ubicacion: str | None = None
    estado: str
    creado_en: datetime.datetime
    actualizado_en: datetime.datetime

    @field_validator("tarifa_hora", mode="before")
    @classmethod
    def normalizar_tarifa(cls, v):
        return 0.0 if v is None else float(v)


# --- Reservas ---

class CrearReservaRequest(BaseModel):
    espacio_id: int = Field(..., gt=0)
    fecha_inicio: datetime.datetime
    fecha_fin: datetime.datetime



class GastoFallidoRequest(BaseModel):
    reserva_id: int | None = None
    usuario_sub: str | None = None
    espacio_id: int | None = None
    fecha_inicio: datetime.datetime | None = None


class EventoPagoConfirmadoRequest(BaseModel):
    reserva_id: int


class ReservaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    espacio_id: int
    usuario_sub: str
    fecha_inicio: datetime.datetime
    fecha_fin: datetime.datetime
    estado: str
    monto_total: float = 0.0
    expira_en: datetime.datetime | None = None
    creado_en: datetime.datetime

    @field_validator("monto_total", mode="before")
    @classmethod
    def normalizar_monto(cls, v):
        return 0.0 if v is None else float(v)

