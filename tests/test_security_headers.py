from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.espacio_router import obtener_servicio
from app.main import app

CSP_DOCS_ESPERADO = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:; "
    "connect-src 'self'"
)

CSP_ESTRICTO_ESPERADO = "default-src 'self'"


@pytest.fixture
def servicio_mock():
    return AsyncMock()


@pytest.fixture
async def cliente(servicio_mock):
    app.dependency_overrides[obtener_servicio] = lambda: servicio_mock
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_csp_en_docs_permite_recursos_externos(cliente):
    respuesta = await cliente.get("/docs")
    assert respuesta.status_code == 200
    assert respuesta.headers.get("Content-Security-Policy") == CSP_DOCS_ESPERADO
    assert "https://cdn.jsdelivr.net" in respuesta.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" in respuesta.headers["Content-Security-Policy"]


async def test_csp_en_redoc_permite_recursos_externos(cliente):
    respuesta = await cliente.get("/redoc")
    assert respuesta.status_code == 200
    assert respuesta.headers.get("Content-Security-Policy") == CSP_DOCS_ESPERADO
    assert "https://fonts.googleapis.com" in respuesta.headers["Content-Security-Policy"]
    assert "https://fonts.gstatic.com" in respuesta.headers["Content-Security-Policy"]


async def test_csp_en_openapi_permite_recursos_externos(cliente):
    respuesta = await cliente.get("/openapi.json")
    assert respuesta.status_code == 200
    assert respuesta.headers.get("Content-Security-Policy") == CSP_DOCS_ESPERADO


async def test_csp_en_api_mantiene_politica_estricta(cliente, servicio_mock):
    servicio_mock.listar_todos.return_value = []

    # Verificación en endpoint de negocio
    respuesta_espacios = await cliente.get("/api/v1/espacios/")
    assert respuesta_espacios.status_code == 200
    assert respuesta_espacios.headers.get("Content-Security-Policy") == CSP_ESTRICTO_ESPERADO

    # Verificación en endpoint de salud
    respuesta_salud = await cliente.get("/api/v1/health")
    assert respuesta_salud.status_code == 200
    assert respuesta_salud.headers.get("Content-Security-Policy") == CSP_ESTRICTO_ESPERADO


async def test_otras_cabeceras_de_seguridad(cliente):
    respuesta = await cliente.get("/docs")
    assert respuesta.headers.get("X-Content-Type-Options") == "nosniff"
    assert respuesta.headers.get("X-Frame-Options") == "DENY"
    assert respuesta.headers.get("X-XSS-Protection") == "1; mode=block"
    assert respuesta.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"
    assert respuesta.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert respuesta.headers.get("server") == "convivo"
