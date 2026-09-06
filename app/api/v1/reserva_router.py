from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.dto.request.reserva_request import CrearReservaRequest
from app.dto.response.reserva_response import ReservaResponse
from app.repository.reserva_repository import ReservaRepository
from app.service.reserva_service import ReservaService

router = APIRouter(prefix="/reservas", tags=["reservas"])


def obtener_servicio(sesion: AsyncSession = Depends(obtener_sesion)) -> ReservaService:
    return ReservaService(ReservaRepository(sesion))


@router.post("/", response_model=ReservaResponse, status_code=201)
async def crear_reserva(
    datos: CrearReservaRequest,
    x_usuario_sub: str = Header(...),
    servicio: ReservaService = Depends(obtener_servicio),
):
    return await servicio.crear(
        espacio_id=datos.espacio_id,
        usuario_sub=x_usuario_sub,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=datos.fecha_fin,
    )


@router.get("/", response_model=list[ReservaResponse])
async def listar_reservas(
    x_usuario_sub: str = Header(...),
    x_es_admin: bool = Header(False),
    servicio: ReservaService = Depends(obtener_servicio),
):
    if x_es_admin:
        return await servicio.listar_todas()
    return await servicio.listar_por_usuario(x_usuario_sub)
