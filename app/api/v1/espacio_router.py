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
from app.repository.espacio_repository import EspacioRepository
from app.service.espacio_service import EspacioService

router = APIRouter(prefix="/espacios", tags=["espacios"])


def obtener_servicio(sesion: AsyncSession = Depends(obtener_sesion)) -> EspacioService:
    return EspacioService(EspacioRepository(sesion))


@router.get("/", response_model=list[EspacioResponse])
async def listar_espacios(
    servicio: EspacioService = Depends(obtener_servicio),
):
    return await servicio.listar_todos()


@router.get("/{espacio_id}", response_model=EspacioResponse)
async def obtener_espacio(
    espacio_id: int,
    servicio: EspacioService = Depends(obtener_servicio),
):
    espacio = await servicio.obtener_por_id(espacio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    return espacio


@router.post(
    "/",
    response_model=EspacioResponse,
    status_code=201,
    dependencies=[Depends(requerir_roles(["admin"]))],
)
async def crear_espacio(
    datos: CrearEspacioRequest,
    servicio: EspacioService = Depends(obtener_servicio),
):
    return await servicio.crear(
        nombre=datos.nombre,
        capacidad=datos.capacidad,
        tarifa_hora=datos.tarifa_hora,
        descripcion=datos.descripcion,
        ubicacion=datos.ubicacion,
    )


@router.put(
    "/{espacio_id}",
    response_model=EspacioResponse,
    dependencies=[Depends(requerir_roles(["admin"]))],
)
async def actualizar_espacio(
    espacio_id: int,
    datos: ActualizarEspacioRequest,
    servicio: EspacioService = Depends(obtener_servicio),
):
    return await servicio.actualizar(
        espacio_id=espacio_id,
        nombre=datos.nombre,
        capacidad=datos.capacidad,
        tarifa_hora=datos.tarifa_hora,
        descripcion=datos.descripcion,
        ubicacion=datos.ubicacion,
        estado=datos.estado,
    )


@router.delete(
    "/{espacio_id}",
    status_code=204,
    dependencies=[Depends(requerir_roles(["admin"]))],
)
async def eliminar_espacio(
    espacio_id: int,
    servicio: EspacioService = Depends(obtener_servicio),
):
    await servicio.eliminar(espacio_id)
    return None


