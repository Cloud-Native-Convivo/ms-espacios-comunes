import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inicio = time.time()
        respuesta = await call_next(request)
        duracion = time.time() - inicio

        logger.info(
            "%s %s %s %.3fs",
            request.method,
            request.url.path,
            respuesta.status_code,
            duracion,
        )
        return respuesta
