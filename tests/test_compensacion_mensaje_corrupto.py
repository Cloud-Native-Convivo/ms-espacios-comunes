from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events.compensacion_consumer import procesar_compensacion, procesar_pago


@pytest.mark.parametrize("procesar", [procesar_compensacion, procesar_pago])
async def test_mensaje_corrupto_se_rechaza_hacia_dlq_sin_reencolar(procesar):
    mensaje = MagicMock()
    mensaje.body = b"{no es json"
    mensaje.reject = AsyncMock()
    mensaje.ack = AsyncMock()

    await procesar(mensaje)

    mensaje.reject.assert_awaited_once_with(requeue=False)
    mensaje.ack.assert_not_awaited()
    mensaje.process.assert_not_called()
