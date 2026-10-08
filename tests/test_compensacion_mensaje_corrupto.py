from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events.compensacion_consumer import procesar_compensacion, procesar_pago


@pytest.mark.parametrize("procesar", [procesar_compensacion, procesar_pago])
async def test_mensaje_corrupto_se_descarta_con_ack_sin_reencolar(procesar):
    mensaje = MagicMock()
    mensaje.body = b"{no es json"
    mensaje.ack = AsyncMock()

    await procesar(mensaje)

    mensaje.ack.assert_awaited_once()
    mensaje.process.assert_not_called()
