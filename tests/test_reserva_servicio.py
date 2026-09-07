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


async def test_crear_reserva_fecha_en_el_pasado(servicio, repo):
    now = datetime.datetime.now()
    fecha_inicio = now - datetime.timedelta(hours=2)
    fecha_fin = now + datetime.timedelta(hours=1)

    with pytest.raises(Exception, match="pasado"):
        await servicio.crear(1, "user-123", fecha_inicio, fecha_fin)


async def test_crear_reserva_duracion_excesiva(servicio, repo):
    now = datetime.datetime.now()
    fecha_inicio = now + datetime.timedelta(hours=1)
    fecha_fin = now + datetime.timedelta(hours=26)  # 25 horas

    with pytest.raises(Exception, match="24 horas"):
        await servicio.crear(1, "user-123", fecha_inicio, fecha_fin)



async def test_crear_reserva_calculo_monto_y_estado(repo):
    from app.model.modelos import Espacio
    from app.service.reserva_service import ReservaService

    espacio_repo = AsyncMock()
    espacio = Espacio(id=1, nombre="Quincho", capacidad=15, tarifa_hora=10000.0)
    espacio_repo.obtener_por_id.return_value = espacio

    servicio_con_espacio = ReservaService(repo, espacio_repo)

    now = datetime.datetime.now()
    inicio = now + datetime.timedelta(hours=2)
    fin = now + datetime.timedelta(hours=5)  # 3 horas

    repo.existe_solapamiento.return_value = False

    async def mock_crear(reserva, evento):
        reserva.id = 42
        return reserva

    repo.crear.side_effect = mock_crear

    reserva = await servicio_con_espacio.crear(1, "user-123", inicio, fin)

    assert reserva.estado == "pendiente_pago"
    assert reserva.monto_total == 30000.0
    assert reserva.expira_en is not None


async def test_compensar_por_gasto_fallido_con_id(servicio, repo):
    repo.cancelar_por_id = AsyncMock()
    repo.cancelar_por_id.return_value = Reserva(id=5, estado="cancelada")

    resultado = await servicio.compensar_por_gasto_fallido(reserva_id=5)
    assert resultado is not None
    assert resultado.estado == "cancelada"
    repo.cancelar_por_id.assert_awaited_once_with(5)

