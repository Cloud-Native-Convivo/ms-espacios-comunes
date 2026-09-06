import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def cliente():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_salud(cliente):
    respuesta = await cliente.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


async def test_crear_reserva_sin_header(cliente):
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=1)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=3)).isoformat(),
    }
    respuesta = await cliente.post("/api/v1/reservas/", json=datos)
    assert respuesta.status_code == 422
