from pydantic import BaseModel


class CrearEspacioRequest(BaseModel):
    nombre: str
    capacidad: int
    descripcion: str | None = None
    ubicacion: str | None = None


class ActualizarEspacioRequest(BaseModel):
    nombre: str | None = None
    capacidad: int | None = None
    descripcion: str | None = None
    ubicacion: str | None = None
    estado: str | None = None
