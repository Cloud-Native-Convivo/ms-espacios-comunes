import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.events.expiracion_worker import worker_expiracion


def _fabrica_con(sesion):
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


async def test_worker_marca_expiradas_y_propaga_cancelacion_en_espera():
    sesion = AsyncMock()
    reserva = MagicMock()
    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", _fabrica_con(sesion)),
        patch("app.events.expiracion_worker.reserva_repository") as repo,
        patch("app.events.expiracion_worker.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        repo.obtener_expiradas = AsyncMock(return_value=[reserva])
        repo.marcar_expirada = AsyncMock()
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)

    repo.marcar_expirada.assert_awaited_once_with(sesion, reserva)
    sesion.commit.assert_awaited_once()


async def test_worker_re_lanza_cancelacion_durante_procesamiento():
    fabrica = MagicMock(side_effect=asyncio.CancelledError)
    with patch("app.events.expiracion_worker.fabrica_sesiones", fabrica):
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)


async def test_worker_registra_error_y_sigue_en_bucle():
    fabrica = MagicMock(side_effect=RuntimeError("db caida"))
    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", fabrica),
        patch("app.events.expiracion_worker.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)
    fabrica.assert_called_once()
