import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.events import compensacion_consumer as consumer


def _fabrica_con(sesion):
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


def _mensaje(cuerpo: dict):
    mensaje = MagicMock()
    mensaje.body = json.dumps(cuerpo).encode()
    proceso = MagicMock()
    proceso.__aenter__ = AsyncMock(return_value=None)
    proceso.__aexit__ = AsyncMock(return_value=False)
    mensaje.process = MagicMock(return_value=proceso)
    mensaje.reject = AsyncMock()
    mensaje.ack = AsyncMock()
    return mensaje


def _mensaje_corrupto(cuerpo_bytes: bytes = b"invalido"):
    mensaje = MagicMock()
    mensaje.body = cuerpo_bytes
    mensaje.reject = AsyncMock()
    mensaje.ack = AsyncMock()
    return mensaje


@pytest.mark.parametrize(
    ("procesar", "cuerpo", "funcion_servicio"),
    [
        (consumer.procesar_compensacion, {"reserva_id": 3}, "compensar_por_gasto_fallido"),
        (consumer.procesar_pago, {"reserva_id": 3}, "confirmar_pago"),
    ],
)
@pytest.mark.parametrize("encontrada", [True, False])
async def test_procesa_mensaje_valido(procesar, cuerpo, funcion_servicio, encontrada):
    sesion = AsyncMock()
    reserva = MagicMock(id=3) if encontrada else None
    with (
        patch.object(consumer, "fabrica_sesiones", _fabrica_con(sesion)),
        patch.object(consumer.reserva_service, funcion_servicio, AsyncMock(return_value=reserva)) as servicio,
    ):
        await procesar(_mensaje(cuerpo))

    servicio.assert_awaited_once()
    assert sesion.commit.await_count == (1 if encontrada else 0)


@pytest.mark.parametrize(
    "procesar",
    [consumer.procesar_compensacion, consumer.procesar_pago],
)
async def test_mensaje_corrupto_se_rechaza_sin_requeue_hacia_dlq(procesar):
    mensaje = _mensaje_corrupto()
    await procesar(mensaje)
    mensaje.reject.assert_awaited_once_with(requeue=False)
    mensaje.ack.assert_not_awaited()


@pytest.mark.parametrize(
    ("procesar", "funcion_servicio"),
    [
        (consumer.procesar_compensacion, "compensar_por_gasto_fallido"),
        (consumer.procesar_pago, "confirmar_pago"),
    ],
)
async def test_error_operacional_no_se_propaga(procesar, funcion_servicio):
    sesion = AsyncMock()
    with (
        patch.object(consumer, "fabrica_sesiones", _fabrica_con(sesion)),
        patch.object(consumer.reserva_service, funcion_servicio, AsyncMock(side_effect=RuntimeError("db"))),
    ):
        await procesar(_mensaje({"reserva_id": 1}))
    sesion.commit.assert_not_awaited()


async def test_consumidor_declara_colas_con_bind_y_cierra_al_cancelar():
    exchange_events = MagicMock()
    exchange_dlx = MagicMock()

    colas = {
        consumer.COLA_COMPENSACION: AsyncMock(),
        consumer.COLA_PAGO: AsyncMock(),
        consumer.COLA_COMPENSACION_DLQ: AsyncMock(),
        consumer.COLA_PAGO_DLQ: AsyncMock(),
    }

    def _mock_declare_exchange(nombre, tipo, durable):
        return exchange_dlx if "dlx" in nombre else exchange_events

    def _mock_declare_queue(nombre, durable=True, arguments=None):
        cola = colas[nombre]
        cola.nombre = nombre
        cola.arguments = arguments
        return cola

    canal = AsyncMock()
    canal.declare_exchange = AsyncMock(side_effect=_mock_declare_exchange)
    canal.declare_queue = AsyncMock(side_effect=_mock_declare_queue)
    conexion = AsyncMock()
    conexion.channel = AsyncMock(return_value=canal)

    with patch.object(consumer.aio_pika, "connect_robust", AsyncMock(return_value=conexion)):
        tarea = asyncio.create_task(consumer.consumidor_compensacion.__wrapped__())
        while not colas[consumer.COLA_PAGO].consume.await_count:
            await asyncio.sleep(0)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

    canal.set_qos.assert_awaited_once_with(prefetch_count=1)
    # Verifica que declare el exchange de eventos y el DLX
    assert canal.declare_exchange.await_count >= 2
    # Verifica colas DLQ y bindings
    colas[consumer.COLA_COMPENSACION_DLQ].bind.assert_awaited_once_with(
        exchange_dlx, routing_key=consumer.COLA_COMPENSACION_DLQ
    )
    colas[consumer.COLA_PAGO_DLQ].bind.assert_awaited_once_with(
        exchange_dlx, routing_key=consumer.COLA_PAGO_DLQ
    )
    # Verifica colas principales con bind al exchange principal y argumentos DLQ
    colas[consumer.COLA_COMPENSACION].bind.assert_awaited_once_with(
        exchange_events, routing_key=consumer.COLA_COMPENSACION
    )
    colas[consumer.COLA_PAGO].bind.assert_awaited_once_with(
        exchange_events, routing_key=consumer.COLA_PAGO
    )
    assert colas[consumer.COLA_COMPENSACION].arguments == {
        "x-dead-letter-exchange": consumer.EXCHANGE_DLX,
        "x-dead-letter-routing-key": consumer.COLA_COMPENSACION_DLQ,
    }
    assert colas[consumer.COLA_PAGO].arguments == {
        "x-dead-letter-exchange": consumer.EXCHANGE_DLX,
        "x-dead-letter-routing-key": consumer.COLA_PAGO_DLQ,
    }
    conexion.close.assert_awaited_once()


def test_gasto_fallido_request_acepta_camel_case():
    from app.dto.esquemas import GastoFallidoRequest
    raw_json = '{"reservaId": "42", "motivo": "datos_inconsistentes"}'
    req = GastoFallidoRequest.model_validate_json(raw_json)
    assert req.reserva_id == 42
