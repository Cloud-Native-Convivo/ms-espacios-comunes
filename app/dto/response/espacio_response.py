import datetime

from pydantic import BaseModel, ConfigDict


class EspacioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None
    capacidad: int
    ubicacion: str | None
    estado: str
    creado_en: datetime.datetime
    actualizado_en: datetime.datetime
