from unittest.mock import AsyncMock, MagicMock

from app.events.topologia_notificaciones import (
    COLA_NOTIFICACIONES,
    COLA_NOTIFICACIONES_DLQ,
    COLA_PDF,
    COLA_PDF_DLQ,
    EXCHANGE_DLX,
    declarar_topologia_notificaciones,
)


async def test_declara_colas_con_bindings_y_dlq():
    exchange_eventos = MagicMock()
    exchange_dlx = MagicMock()
    colas_creadas = {}

    def _declare_exchange(nombre, tipo, durable):
        return exchange_dlx if nombre == EXCHANGE_DLX else exchange_eventos

    def _declare_queue(nombre, durable=True, arguments=None):
        cola = AsyncMock()
        cola.nombre = nombre
        cola.arguments = arguments
        colas_creadas[nombre] = cola
        return cola

    canal = AsyncMock()
    canal.declare_exchange = AsyncMock(side_effect=_declare_exchange)
    canal.declare_queue = AsyncMock(side_effect=_declare_queue)

    colas = await declarar_topologia_notificaciones(canal)

    assert colas[COLA_NOTIFICACIONES].arguments == {
        "x-dead-letter-exchange": EXCHANGE_DLX,
        "x-dead-letter-routing-key": COLA_NOTIFICACIONES_DLQ,
    }
    assert colas[COLA_PDF].arguments == {
        "x-dead-letter-exchange": EXCHANGE_DLX,
        "x-dead-letter-routing-key": COLA_PDF_DLQ,
    }
    colas_creadas[COLA_NOTIFICACIONES].bind.assert_any_await(exchange_eventos, routing_key="reserva_espacio_creada")
    colas_creadas[COLA_NOTIFICACIONES].bind.assert_any_await(exchange_eventos, routing_key="reserva_expirada")
    colas_creadas[COLA_PDF].bind.assert_any_await(exchange_eventos, routing_key="reserva_confirmada")
    colas_creadas[COLA_NOTIFICACIONES_DLQ].bind.assert_awaited_once_with(exchange_dlx, routing_key=COLA_NOTIFICACIONES_DLQ)
    colas_creadas[COLA_PDF_DLQ].bind.assert_awaited_once_with(exchange_dlx, routing_key=COLA_PDF_DLQ)
