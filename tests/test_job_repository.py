import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.model.solicitud_job import SolicitudJob
from app.repository import job_repository


@pytest.fixture
def mock_sesion():
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_guardar_job(mock_sesion):
    job = SolicitudJob(
        ticket_id="ticket-abc",
        modulo="ESPACIOS",
        accion="CREAR_RESERVA",
        usuario_id="user-1",
        estado="EN_COLA",
    )
    guardado = await job_repository.guardar_job(mock_sesion, job)
    assert guardado.ticket_id == "ticket-abc"
    mock_sesion.add.assert_called_once_with(job)
    mock_sesion.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_obtener_por_ticket_id(mock_sesion):
    job = SolicitudJob(
        ticket_id="ticket-abc",
        modulo="ESPACIOS",
        accion="CREAR_RESERVA",
        usuario_id="user-1",
        estado="EN_COLA",
    )
    mock_sesion.get.return_value = job

    recuperado = await job_repository.obtener_por_ticket_id(mock_sesion, "ticket-abc")
    assert recuperado is not None
    assert recuperado.ticket_id == "ticket-abc"
    mock_sesion.get.assert_awaited_once_with(SolicitudJob, "ticket-abc")


@pytest.mark.asyncio
async def test_actualizar_estado_job(mock_sesion):
    job = SolicitudJob(
        ticket_id="ticket-abc",
        modulo="ESPACIOS",
        accion="CREAR_RESERVA",
        usuario_id="user-1",
        estado="EN_COLA",
    )
    mock_sesion.get.return_value = job

    actualizado = await job_repository.actualizar_estado_job(
        mock_sesion, "ticket-abc", "COMPLETADO", resultado='{"id": 1}'
    )
    assert actualizado is not None
    assert actualizado.estado == "COMPLETADO"
    assert actualizado.resultado == '{"id": 1}'
    mock_sesion.flush.assert_awaited_once()
