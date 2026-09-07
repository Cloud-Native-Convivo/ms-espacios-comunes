from fastapi import APIRouter

from app.api.v1.espacio_router import router as espacio_router
from app.api.v1.reserva_router import router as reserva_router

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["health"])
async def salud():
    return {"estado": "ok"}


api_router.include_router(espacio_router)
api_router.include_router(reserva_router)
