import datetime
from unittest.mock import AsyncMock, patch
import pytest

from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException
)
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.model.modelos import Reserva, Espacio
from app.service import reserva_service
from app.dto.esquemas import CrearReservaRequest

@pytest.fixture
def mock_sesion():
    return AsyncMock()

@pytest.fixture
def mock_espacio_repo():
    with patch("app.service.reserva_service.espacio_repository") as m:
        m.obtener_por_id = AsyncMock()
        yield m

@pytest.fixture
def mock_reserva_repo():
    with patch("app.service.reserva_service.reserva_repository") as m:
        m.existe_solapamiento = AsyncMock()
        m.crear = AsyncMock()
        m.cancelar_por_id = AsyncMock()
        m.confirmar_pago = AsyncMock()
        yield m

async def test_crear_reserva_exitosa(mock_sesion, mock_espacio_repo, mock_reserva_repo):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=3)
    )
    usuario_sub = "user-123"

    mock_espacio_repo.obtener_por_id.return_value = Espacio(id=1, estado="activo", tarifa_hora=10000.0)
    mock_reserva_repo.existe_solapamiento.return_value = False
    mock_reserva_repo.crear.return_value = Reserva(id=42, estado="pendiente_pago", monto_total=20000.0)

    reserva = await reserva_service.crear(mock_sesion, datos, usuario_sub)

    mock_reserva_repo.crear.assert_awaited_once()
    assert reserva.id == 42
    assert reserva.monto_total == 20000.0

async def test_crear_reserva_solapamiento(mock_sesion, mock_espacio_repo, mock_reserva_repo):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=3)
    )
    mock_espacio_repo.obtener_por_id.return_value = Espacio(id=1, estado="activo")
    mock_reserva_repo.existe_solapamiento.return_value = True

    with pytest.raises(ReservaSolapamientoException, match="reservado"):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_crear_reserva_fecha_fin_antes(mock_sesion):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=3),
        fecha_fin=now + datetime.timedelta(hours=1)
    )

    with pytest.raises(ReservaFechaInvalidaException, match="posterior"):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_crear_reserva_fecha_en_el_pasado(mock_sesion):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now - datetime.timedelta(hours=2),
        fecha_fin=now + datetime.timedelta(hours=1)
    )

    with pytest.raises(ReservaFechaInvalidaException, match="pasado"):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_crear_reserva_duracion_excesiva(mock_sesion):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=26)
    )

    with pytest.raises(ReservaFechaInvalidaException, match="24 horas"):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_crear_reserva_usuario_sub_vacio(mock_sesion):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=3)
    )

    with pytest.raises(ReservaFechaInvalidaException, match="identificador de usuario"):
        await reserva_service.crear(mock_sesion, datos, "   ")

async def test_listar_reservas_usuario_sub_vacio(mock_sesion):
    with pytest.raises(ReservaFechaInvalidaException, match="identificador de usuario"):
        await reserva_service.listar_por_usuario(mock_sesion, "   ")

async def test_crear_reserva_espacio_no_encontrado(mock_sesion, mock_espacio_repo):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=999,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=3)
    )
    mock_espacio_repo.obtener_por_id.return_value = None

    with pytest.raises(EspacioNoEncontradoException):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_crear_reserva_espacio_inactivo(mock_sesion, mock_espacio_repo):
    now = datetime.datetime.now()
    datos = CrearReservaRequest(
        espacio_id=1,
        fecha_inicio=now + datetime.timedelta(hours=1),
        fecha_fin=now + datetime.timedelta(hours=3)
    )
    mock_espacio_repo.obtener_por_id.return_value = Espacio(id=1, estado="inactivo")

    with pytest.raises(ReservaEspacioNoDisponibleException, match="no está disponible"):
        await reserva_service.crear(mock_sesion, datos, "user-123")

async def test_compensar_por_gasto_fallido_con_id(mock_sesion, mock_reserva_repo):
    mock_reserva_repo.cancelar_por_id.return_value = Reserva(id=5, estado="cancelada")

    resultado = await reserva_service.compensar_por_gasto_fallido(mock_sesion, reserva_id=5)
    assert resultado is not None
    assert resultado.estado == "cancelada"
    mock_reserva_repo.cancelar_por_id.assert_awaited_once_with(mock_sesion, 5)
