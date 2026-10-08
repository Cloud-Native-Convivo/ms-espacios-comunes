import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.events.outbox_event import relay_outbox


def _fabrica_con(sesion):
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


async def test_relay_publica_pendientes_y_los_marca_procesados():
    exchange = AsyncMock()
    canal = AsyncMock()
    canal.declare_exchange = AsyncMock(return_value=exchange)
    conexion = AsyncMock()
    conexion.channel = AsyncMock(return_value=canal)
    sesion = AsyncMock()
    evento = MagicMock(carga_util='{"id": 1}', tipo_evento="reserva_espacio_creada")

    with (
        patch("app.events.outbox_event.aio_pika.connect_robust", AsyncMock(return_value=conexion)),
        patch("app.events.outbox_event.fabrica_sesiones", _fabrica_con(sesion)),
        patch("app.events.outbox_event.reserva_repository") as repo,
        patch("app.events.outbox_event.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        repo.obtener_pendientes_outbox = AsyncMock(return_value=[evento])
        repo.marcar_como_procesado = AsyncMock()
        # __wrapped__ evita el @retry de tenacity (reintentaría para siempre)
        with pytest.raises(asyncio.CancelledError):
            await relay_outbox.__wrapped__()

    mensaje = exchange.publish.await_args.args[0]
    assert mensaje.body == b'{"id": 1}'
    assert exchange.publish.await_args.kwargs["routing_key"] == "reserva_espacio_creada"
    repo.marcar_como_procesado.assert_awaited_once_with(sesion, evento)
    sesion.commit.assert_awaited_once()
