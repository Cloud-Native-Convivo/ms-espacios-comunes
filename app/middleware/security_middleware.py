from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Agrega cabeceras de seguridad estándar HTTP a todas las respuestas."""

    async def dispatch(self, request: Request, call_next):
        respuesta = await call_next(request)
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["X-XSS-Protection"] = "1; mode=block"
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        respuesta.headers["Content-Security-Policy"] = "default-src 'self'"
        if "server" in respuesta.headers:
            del respuesta.headers["server"]
        respuesta.headers["server"] = "convivo"
        return respuesta

