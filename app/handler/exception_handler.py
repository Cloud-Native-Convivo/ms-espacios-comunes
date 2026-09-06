from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exception.espacio_exception import EspacioException
from app.exception.reserva_exception import ReservaException


def registrar_manejadores_excepciones(app: FastAPI):
    """Registra los manejadores de excepciones personalizados."""

    @app.exception_handler(ReservaException)
    async def manejar_reserva_exception(request: Request, exc: ReservaException):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(EspacioException)
    async def manejar_espacio_exception(request: Request, exc: EspacioException):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )
