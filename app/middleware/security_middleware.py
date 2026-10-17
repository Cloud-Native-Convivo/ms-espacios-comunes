from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.security_config import (
    CSP_DOCS,
    CSP_ESTRICTO,
    HSTS_VALOR,
    REFERRER_POLICY,
    SERVER_NAME,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Agrega cabeceras de seguridad estándar HTTP a todas las respuestas."""

    async def dispatch(self, request: Request, call_next):
        respuesta = await call_next(request)
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Strict-Transport-Security"] = HSTS_VALOR
        respuesta.headers["Referrer-Policy"] = REFERRER_POLICY

        es_documentacion = (
            request.url.path in ("/docs", "/redoc", "/openapi.json")
            or request.url.path.startswith(("/docs/", "/redoc/"))
        )
        if es_documentacion:
            respuesta.headers["Content-Security-Policy"] = CSP_DOCS
        else:
            respuesta.headers["Content-Security-Policy"] = CSP_ESTRICTO

        if "server" in respuesta.headers:
            del respuesta.headers["server"]
        respuesta.headers["server"] = SERVER_NAME
        return respuesta
