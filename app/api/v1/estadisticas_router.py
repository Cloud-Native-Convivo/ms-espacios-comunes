from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.dto.esquemas import EstadisticaEspacioResponse
from app.middleware.auth_roles import requerir_roles
from app.service import estadisticas_service

# Datos agregados sin información personal: los ven los tres roles.
router = APIRouter(
    prefix="/estadisticas",
    tags=["estadisticas"],
    dependencies=[Depends(requerir_roles(["admin", "conserje", "residente"]))],
)

# Tope = retención de espacios.historial.v1 (90 días).
_DIAS = Query(30, ge=1, le=90, description="Ventana en días, incluye hoy (UTC)")


@router.get("/espacios")
async def estadisticas_espacios(
    condominio_id: int = Query(..., gt=0),
    dias: int = _DIAS,
    sesion: AsyncSession = Depends(obtener_sesion),
) -> list[EstadisticaEspacioResponse]:
    return await estadisticas_service.listar(sesion, condominio_id, dias)


@router.get("/espacios/preferidos")
async def espacios_preferidos(
    condominio_id: int = Query(..., gt=0),
    dias: int = _DIAS,
    limite: int = Query(5, ge=1, le=50),
    sesion: AsyncSession = Depends(obtener_sesion),
) -> list[EstadisticaEspacioResponse]:
    return await estadisticas_service.preferidos(sesion, condominio_id, dias, limite)
