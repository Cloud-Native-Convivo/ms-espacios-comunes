import asyncio
import datetime
from unittest.mock import AsyncMock, patch

from app.events.expiracion_worker import worker_expiracion
from app.model.modelos import Reserva


async def test_worker_expiracion_marca_reservas():
    ahora = datetime.datetime.now()
    reserva_expirada = Reserva(
        id=10,
        estado="pendiente_pago",
        expira_en=ahora - datetime.timedelta(minutes=5),
    )

    mock_sesion = AsyncMock()
    mock_sesion.__aenter__.return_value = mock_sesion
    mock_sesion.__aexit__.return_value = None

    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", return_value=mock_sesion),
        patch("app.events.expiracion_worker.ReservaRepository") as mock_repo_cls,
    ):
        mock_repo = AsyncMock()
        mock_repo.obtener_expiradas.return_value = [reserva_expirada]
        mock_repo_cls.return_value = mock_repo

        # Ejecutar worker y cancelarlo tras la primera iteración
        tarea = asyncio.create_task(worker_expiracion(intervalo_segundos=1))
        await asyncio.sleep(0.05)
        tarea.cancel()
        await asyncio.gather(tarea, return_exceptions=True)

        mock_repo.marcar_expirada.assert_awaited_once_with(reserva_expirada)
        mock_sesion.commit.assert_awaited_once()
