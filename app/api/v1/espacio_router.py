from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.dto.esquemas import (
    ActualizarEspacioRequest,
    CrearEspacioRequest,
    EspacioResponse,
)
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.middleware.auth_roles import requerir_roles
from app.service import espacio_service

router = APIRouter(prefix="/espacios", tags=["espacios"])

@router.get("/")
async def listar_espacios(
    sesion: AsyncSession = Depends(obtener_sesion),
) -> list[EspacioResponse]:
    return await espacio_service.listar_todos(sesion)

@router.get("/{espacio_id}")
async def obtener_espacio(
    espacio_id: int,
    sesion: AsyncSession = Depends(obtener_sesion),
) -> EspacioResponse:
    espacio = await espacio_service.obtener_por_id(sesion, espacio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    return espacio

@router.post(
    "/",
    status_code=201,
    dependencies=[Depends(requerir_roles(["admin", "administrador", "conserje"]))],
)
async def crear_espacio(
    datos: CrearEspacioRequest,
    sesion: AsyncSession = Depends(obtener_sesion),
) -> EspacioResponse:
    return await espacio_service.crear(sesion, datos)

@router.put(
    "/{espacio_id}",
    dependencies=[Depends(requerir_roles(["admin", "administrador", "conserje"]))],
)
async def actualizar_espacio(
    espacio_id: int,
    datos: ActualizarEspacioRequest,
    sesion: AsyncSession = Depends(obtener_sesion),
) -> EspacioResponse:
    return await espacio_service.actualizar(sesion, espacio_id, datos)

@router.delete(
    "/{espacio_id}",
    status_code=204,
    dependencies=[Depends(requerir_roles(["admin", "administrador", "conserje"]))],
)
async def eliminar_espacio(
    espacio_id: int,
    sesion: AsyncSession = Depends(obtener_sesion),
) -> None:
    await espacio_service.eliminar(sesion, espacio_id)
    return None
