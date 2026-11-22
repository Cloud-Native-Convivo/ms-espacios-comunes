from fastapi import APIRouter

from app.api.v1.espacio_router import router as espacio_router
from app.api.v1.estadisticas_router import router as estadisticas_router
from app.api.v1.job_router import router as job_router
from app.api.v1.kafka_admin_router import router as kafka_admin_router
from app.api.v1.reserva_router import router as reserva_router

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["health"])
async def salud():
    return {"estado": "ok"}


api_router.include_router(espacio_router)
api_router.include_router(reserva_router)
api_router.include_router(job_router)
api_router.include_router(estadisticas_router)
api_router.include_router(kafka_admin_router)

