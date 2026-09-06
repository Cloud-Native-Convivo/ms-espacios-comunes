import datetime
from unittest.mock import AsyncMock

import pytest

from app.model.modelos import Reserva


class RepoMock:
    def __init__(self):
        self.existe_solapamiento = AsyncMock()
        self.crear = AsyncMock()
        self.obtener_por_usuario = AsyncMock()
        self.obtener_todas = AsyncMock()
        self.obtener_pendientes_outbox = AsyncMock()
        self.marcar_como_procesado = AsyncMock()
        self.cancelar_por_evento = AsyncMock()


@pytest.fixture
def repo():
    return RepoMock()


@pytest.fixture
def servicio(repo):
    from app.service.reserva_service import ReservaService

    return ReservaService(repo)


async def test_crear_reserva_exitosa(servicio, repo):
    now = datetime.datetime.now()
    espacio_id = 1
    usuario_sub = "user-123"
    fecha_inicio = now + datetime.timedelta(hours=1)
    fecha_fin = now + datetime.timedelta(hours=3)

    repo.existe_solapamiento.return_value = False
    repo.crear.return_value = Reserva()

    reserva = await servicio.crear(espacio_id, usuario_sub, fecha_inicio, fecha_fin)

    repo.crear.assert_awaited_once()


async def test_crear_reserva_solapamiento(servicio, repo):
    now = datetime.datetime.now()
    fecha_inicio = now + datetime.timedelta(hours=1)
    fecha_fin = now + datetime.timedelta(hours=3)

    repo.existe_solapamiento.return_value = True

    with pytest.raises(Exception, match="reservado"):
        await servicio.crear(1, "user-123", fecha_inicio, fecha_fin)


async def test_crear_reserva_fecha_fin_antes(servicio, repo):
    now = datetime.datetime.now()
    fecha_inicio = now + datetime.timedelta(hours=3)
    fecha_fin = now + datetime.timedelta(hours=1)

    with pytest.raises(Exception, match="posterior"):
        await servicio.crear(1, "user-123", fecha_inicio, fecha_fin)
