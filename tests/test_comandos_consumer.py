from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exception.reserva_exception import ReservaSolapamientoException
from app.model.solicitud_job import SolicitudJob
from app.events.comandos_consumer import procesar_comando_mutacion


@pytest.fixture
def mock_sesion():
    sesion = AsyncMock(spec=AsyncSession)
    return sesion


@pytest.mark.asyncio
async def test_procesar_comando_crear_reserva_exitoso(mock_sesion):
    comando = {
        "ticket_id": "ticket-123",
        "modulo": "ESPACIOS",
        "accion": "CREAR_RESERVA",
        "usuario_id": "user-1",
        "rol": "residente",
        "payload": {
            "espacio_id": 1,
            "fecha_inicio": "2026-10-15T18:00:00Z",
            "fecha_fin": "2026-10-15T20:00:00Z",
        },
    }

    mock_reserva = MagicMock()
    mock_reserva.id = 101
    mock_reserva.estado = "pendiente_pago"

    with patch(
        "app.events.comandos_consumer.reserva_service.crear",
        new=AsyncMock(return_value=mock_reserva),
    ):
        await procesar_comando_mutacion(mock_sesion, comando)
        mock_sesion.commit.assert_awaited()


@pytest.mark.asyncio
async def test_procesar_comando_crear_reserva_conflicto_solapamiento(mock_sesion):
    comando = {
        "ticket_id": "ticket-456",
        "modulo": "ESPACIOS",
        "accion": "CREAR_RESERVA",
        "usuario_id": "user-1",
        "rol": "residente",
        "payload": {
            "espacio_id": 1,
            "fecha_inicio": "2026-10-15T18:00:00Z",
            "fecha_fin": "2026-10-15T20:00:00Z",
        },
    }

    with patch(
        "app.events.comandos_consumer.reserva_service.crear",
        new=AsyncMock(
            side_effect=ReservaSolapamientoException(
                1, "2026-10-15T18:00:00Z", "2026-10-15T20:00:00Z"
            )
        ),
    ):
        await procesar_comando_mutacion(mock_sesion, comando)
        mock_sesion.rollback.assert_awaited()
        mock_sesion.commit.assert_awaited()


@pytest.mark.asyncio
async def test_procesar_comando_cancelar_reserva(mock_sesion):
    comando = {
        "ticket_id": "ticket-789",
        "modulo": "ESPACIOS",
        "accion": "CANCELAR_RESERVA",
        "usuario_id": "user-1",
        "rol": "residente",
        "payload": {"reserva_id": 5},
    }
    mock_reserva = MagicMock()
    mock_reserva.id = 5
    mock_reserva.estado = "cancelada"

    with patch(
        "app.events.comandos_consumer.reserva_service.cancelar_por_id",
        new=AsyncMock(return_value=mock_reserva),
    ):
        await procesar_comando_mutacion(mock_sesion, comando)
        mock_sesion.commit.assert_awaited()



@pytest.mark.asyncio
async def test_procesar_mensaje_comando_corrupto():
    from app.events.comandos_consumer import procesar_mensaje_comando

    mensaje = MagicMock()
    mensaje.body = b"not-a-json"
    mensaje.ack = AsyncMock()

    await procesar_mensaje_comando(mensaje)
    mensaje.ack.assert_awaited_once()

