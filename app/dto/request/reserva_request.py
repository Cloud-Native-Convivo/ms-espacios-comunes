import datetime

from pydantic import BaseModel


class CrearReservaRequest(BaseModel):
    espacio_id: int
    fecha_inicio: datetime.datetime
    fecha_fin: datetime.datetime


class GastoFallidoRequest(BaseModel):
    usuario_sub: str
    espacio_id: int
    fecha_inicio: datetime.datetime
