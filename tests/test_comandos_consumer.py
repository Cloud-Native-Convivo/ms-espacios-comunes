import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.comandos_consumer import procesar_comando_mutacion
from app.exception.reserva_exception import ReservaSolapamientoException
from app.model.solicitud_job import SolicitudJob


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
async def test_procesar_comando_crear_reserva_propaga_usuario_email(mock_sesion):
    comando = {
        "ticket_id": "ticket-email-1",
        "modulo": "ESPACIOS",
        "accion": "CREAR_RESERVA",
        "usuario_id": "user-1",
        "usuario_email": "ana@convivo.cl",
        "rol": "residente",
        "payload": {
            "espacio_id": 1,
            "fecha_inicio": "2026-10-15T18:00:00Z",
            "fecha_fin": "2026-10-15T20:00:00Z",
        },
    }
    mock_reserva = MagicMock(id=101, estado="pendiente_pago")

    with patch(
        "app.events.comandos_consumer.reserva_service.crear",
        new=AsyncMock(return_value=mock_reserva),
    ) as crear_mock:
        await procesar_comando_mutacion(mock_sesion, comando)

    crear_mock.assert_awaited_once()
    _, kwargs = crear_mock.await_args
    assert kwargs["usuario_email"] == "ana@convivo.cl"


def _comando_cancelar(usuario_id="user-1", rol="residente", reserva_id=5):
    return {
        "ticket_id": "ticket-789",
        "modulo": "ESPACIOS",
        "accion": "CANCELAR_RESERVA",
        "usuario_id": usuario_id,
        "rol": rol,
        "payload": {"reserva_id": reserva_id},
    }


def _repo_con_reserva(dueno="user-1", estado="activa"):
    reserva = MagicMock()
    reserva.id = 5
    reserva.usuario_sub = dueno
    reserva.estado = estado

    async def cancelar(sesion, reserva_id):
        reserva.estado = "cancelada"
        return reserva

    return (
        patch(
            "app.service.reserva_service.reserva_repository.obtener_por_id",
            new=AsyncMock(return_value=reserva),
        ),
        patch(
            "app.service.reserva_service.reserva_repository.cancelar_por_id",
            new=AsyncMock(side_effect=cancelar),
        ),
        reserva,
    )


@pytest.mark.asyncio
async def test_procesar_comando_cancelar_reserva_propia(mock_sesion):
    p_get, p_cancel, reserva = _repo_con_reserva(dueno="user-1")
    with p_get, p_cancel:
        await procesar_comando_mutacion(mock_sesion, _comando_cancelar())
    assert reserva.estado == "cancelada"
    mock_sesion.commit.assert_awaited()


@pytest.mark.asyncio
async def test_cancelar_reserva_ajena_como_residente_queda_fallido_403(mock_sesion):
    p_get, p_cancel, reserva = _repo_con_reserva(dueno="otro-usuario")
    with p_get, p_cancel, patch(
        "app.events.comandos_consumer.job_repository.actualizar_estado_job", new=AsyncMock()
    ) as actualizar:
        await procesar_comando_mutacion(mock_sesion, _comando_cancelar(usuario_id="user-1"))
    assert reserva.estado == "activa"
    kwargs = actualizar.await_args.kwargs
    assert kwargs["estado"] == "FALLIDO"
    assert json.loads(kwargs["error"])["status_code"] == 403


@pytest.mark.asyncio
async def test_cancelar_reserva_ajena_como_conserje_funciona(mock_sesion):
    p_get, p_cancel, reserva = _repo_con_reserva(dueno="otro-usuario")
    with p_get, p_cancel:
        await procesar_comando_mutacion(mock_sesion, _comando_cancelar(rol="conserje"))
    assert reserva.estado == "cancelada"


@pytest.mark.asyncio
async def test_cancelar_reserva_inexistente_queda_fallido_404(mock_sesion):
    with patch(
        "app.service.reserva_service.reserva_repository.obtener_por_id",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.events.comandos_consumer.job_repository.actualizar_estado_job", new=AsyncMock()
    ) as actualizar:
        await procesar_comando_mutacion(mock_sesion, _comando_cancelar(reserva_id=999))
    kwargs = actualizar.await_args.kwargs
    assert kwargs["estado"] == "FALLIDO"
    assert json.loads(kwargs["error"])["status_code"] == 404


@pytest.mark.asyncio
async def test_procesar_mensaje_comando_corrupto():
    from app.events.comandos_consumer import procesar_mensaje_comando

    mensaje = MagicMock()
    mensaje.body = b"not-a-json"
    mensaje.ack = AsyncMock()

    await procesar_mensaje_comando(mensaje)
    mensaje.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumidor_comandos_declara_dlq_y_bind():
    from app.events.comandos_consumer import (
        COLA_COMANDOS,
        COLA_COMANDOS_DLQ,
        EXCHANGE_DLX,
        consumidor_comandos,
    )

    exchange_dlx = MagicMock()
    cola_principal = AsyncMock()
    cola_dlq = AsyncMock()

    def _declare_queue(nombre, durable=True, arguments=None):
        cola = cola_dlq if nombre == COLA_COMANDOS_DLQ else cola_principal
        cola.nombre = nombre
        cola.arguments = arguments
        return cola

    canal = AsyncMock()
    canal.declare_exchange = AsyncMock(return_value=exchange_dlx)
    canal.declare_queue = AsyncMock(side_effect=_declare_queue)
    conexion = AsyncMock()
    conexion.channel = AsyncMock(return_value=canal)

    with patch("app.events.comandos_consumer.aio_pika.connect_robust", AsyncMock(return_value=conexion)):
        tarea = asyncio.create_task(consumidor_comandos.__wrapped__())
        while not cola_principal.consume.await_count:
            await asyncio.sleep(0)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

    cola_dlq.bind.assert_awaited_once_with(exchange_dlx, routing_key=COLA_COMANDOS_DLQ)
    assert cola_principal.arguments == {
        "x-dead-letter-exchange": EXCHANGE_DLX,
        "x-dead-letter-routing-key": COLA_COMANDOS_DLQ,
    }

