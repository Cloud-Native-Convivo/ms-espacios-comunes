from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.model.solicitud_job import SolicitudJob


@pytest.fixture
async def cliente():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_consultar_job_encontrado(cliente):
    job_mock = SolicitudJob(
        ticket_id="ticket-123",
        modulo="ESPACIOS",
        accion="CREAR_RESERVA",
        usuario_id="user-1",
        estado="COMPLETADO",
        resultado='{"id": 42, "estado": "confirmada"}',
        error=None,
    )
    with patch(
        "app.api.v1.job_router.job_repository.obtener_por_ticket_id",
        new=AsyncMock(return_value=job_mock),
    ):
        resp = await cliente.get("/api/v1/jobs/ticket-123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticket_id"] == "ticket-123"
        assert body["estado"] == "COMPLETADO"
        assert body["resultado"] == {"id": 42, "estado": "confirmada"}
        assert body["error"] is None


@pytest.mark.asyncio
async def test_consultar_job_no_encontrado(cliente):
    with patch(
        "app.api.v1.job_router.job_repository.obtener_por_ticket_id",
        new=AsyncMock(return_value=None),
    ):
        resp = await cliente.get("/api/v1/jobs/ticket-inexistente")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job no encontrado"
