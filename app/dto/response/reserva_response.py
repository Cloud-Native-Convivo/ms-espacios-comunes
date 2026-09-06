import datetime

from pydantic import BaseModel, ConfigDict


class ReservaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    espacio_id: int
    usuario_sub: str
    fecha_inicio: datetime.datetime
    fecha_fin: datetime.datetime
    estado: str
    creado_en: datetime.datetime
