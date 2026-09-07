from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.dto.esquemas import CrearReservaRequest, ReservaResponse
from app.middleware.auth_roles import requerir_roles
from app.repository.espacio_repository import EspacioRepository
from app.repository.reserva_repository import ReservaRepository
from app.service.reserva_service import ReservaService

router = APIRouter(prefix="/reservas", tags=["reservas"])


def obtener_servicio(sesion: AsyncSession = Depends(obtener_sesion)) -> ReservaService:
    return ReservaService(
        repo=ReservaRepository(sesion),
        espacio_repo=EspacioRepository(sesion),
    )


@router.post(
    "/",
    response_model=ReservaResponse,
    status_code=201,
    dependencies=[Depends(requerir_roles(["residente", "admin"]))],
)
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
    x_usuario_roles: str = Header(default=""),
    servicio: ReservaService = Depends(obtener_servicio),
):
    roles = {r.strip().lower() for r in x_usuario_roles.split(",") if r.strip()}
    if "admin" in roles or "conserje" in roles:
        return await servicio.listar_todas()
    return await servicio.listar_por_usuario(x_usuario_sub)


@router.post(
    "/{reserva_id}/confirmar-pago",
    response_model=ReservaResponse,
    dependencies=[Depends(requerir_roles(["admin"]))],
)
async def confirmar_pago_reserva(
    reserva_id: int,
    servicio: ReservaService = Depends(obtener_servicio),
):

    reserva = await servicio.confirmar_pago(reserva_id)
    if not reserva:
        raise HTTPException(
            status_code=404,
            detail=f"Reserva {reserva_id} no encontrada o no pendiente de pago",
        )
    return reserva

