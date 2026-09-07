import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exception.espacio_exception import EspacioException
from app.exception.reserva_exception import (
    ReservaException,
    ReservaFechaInvalidaException,
)

logger = logging.getLogger(__name__)


def registrar_manejadores_excepciones(app: FastAPI):
    """Registra los manejadores de excepciones personalizados."""

    @app.exception_handler(ReservaFechaInvalidaException)
    async def manejar_fecha_invalida_exception(
        request: Request, exc: ReservaFechaInvalidaException
    ):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

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

    @app.exception_handler(Exception)
    async def manejar_error_no_controlado(request: Request, exc: Exception):
        logger.exception(
            "Excepción no controlada en %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )

