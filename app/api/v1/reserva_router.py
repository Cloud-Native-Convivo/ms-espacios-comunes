from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.dto.esquemas import CrearReservaRequest, ReservaResponse
from app.middleware.auth_roles import requerir_roles
from app.service import reserva_service

router = APIRouter(prefix="/reservas", tags=["reservas"])

@router.post(
    "/",
    status_code=201,
    dependencies=[Depends(requerir_roles(["residente", "admin"]))],
)
async def crear_reserva(
    datos: CrearReservaRequest,
    x_usuario_sub: str = Header(..., min_length=1),
    sesion: AsyncSession = Depends(obtener_sesion),
) -> ReservaResponse:
    return await reserva_service.crear(sesion, datos, x_usuario_sub)


@router.get("/")
async def listar_reservas(
    x_usuario_sub: str = Header(..., min_length=1),
    x_usuario_roles: str = Header(default=""),
    sesion: AsyncSession = Depends(obtener_sesion),
) -> list[ReservaResponse]:
    roles = {r.strip().lower() for r in x_usuario_roles.split(",") if r.strip()}
    if "admin" in roles or "administrador" in roles or "conserje" in roles:
        return await reserva_service.listar_todas(sesion)
    return await reserva_service.listar_por_usuario(sesion, x_usuario_sub)


