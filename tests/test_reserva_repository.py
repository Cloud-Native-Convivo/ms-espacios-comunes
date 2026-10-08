import datetime
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.repository import reserva_repository
from app.model.modelos import Reserva, EventoOutbox

@pytest.fixture
def mock_sesion():
    return AsyncMock(spec=AsyncSession)

async def test_existe_solapamiento_true(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = Reserva(id=1)
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.existe_solapamiento(
        mock_sesion, 1, datetime.datetime.now(), datetime.datetime.now()
    )
    assert res is True

async def test_existe_solapamiento_false(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.existe_solapamiento(
        mock_sesion, 1, datetime.datetime.now(), datetime.datetime.now()
    )
    assert res is False

async def test_crear(mock_sesion):
    reserva = Reserva(id=1)
    evento = EventoOutbox(id=1)
    res = await reserva_repository.crear(mock_sesion, reserva, evento)
    assert res.id == 1
    assert mock_sesion.add.call_count == 2
    mock_sesion.flush.assert_awaited_once()

async def test_obtener_por_id(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = Reserva(id=1)
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.obtener_por_id(mock_sesion, 1)
    assert res.id == 1

async def test_obtener_por_usuario(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Reserva(id=1, usuario_sub="A")]
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.obtener_por_usuario(mock_sesion, "A")
    assert len(res) == 1

async def test_obtener_todas(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Reserva(id=1), Reserva(id=2)]
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.obtener_todas(mock_sesion)
    assert len(res) == 2

async def test_obtener_pendientes_outbox(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [EventoOutbox(id=1)]
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.obtener_pendientes_outbox(mock_sesion)
    assert len(res) == 1

async def test_marcar_como_procesado(mock_sesion):
    evento = EventoOutbox(id=1, procesado=False)
    await reserva_repository.marcar_como_procesado(mock_sesion, evento)
    assert evento.procesado is True
    mock_sesion.flush.assert_awaited_once()

async def test_confirmar_pago_exito(mock_sesion):
    reserva = Reserva(id=1, estado="pendiente_pago")
    with patch("app.repository.reserva_repository.obtener_por_id", return_value=reserva):
        res = await reserva_repository.confirmar_pago(mock_sesion, 1)
        assert res.estado == "activa"
        mock_sesion.flush.assert_awaited_once()

async def test_cancelar_por_id(mock_sesion):
    reserva = Reserva(id=1, estado="activa")
    with patch("app.repository.reserva_repository.obtener_por_id", return_value=reserva):
        res = await reserva_repository.cancelar_por_id(mock_sesion, 1)
        assert res.estado == "cancelada"
        mock_sesion.flush.assert_awaited_once()

async def test_cancelar_por_evento_existe(mock_sesion):
    res_mock = MagicMock()
    reserva = Reserva(id=1, estado="activa")
    res_mock.scalar_one_or_none.return_value = reserva
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.cancelar_por_evento(mock_sesion, "A", 1, datetime.datetime.now())
    assert res.estado == "cancelada"

async def test_obtener_expiradas(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Reserva(id=1)]
    mock_sesion.execute.return_value = res_mock
    res = await reserva_repository.obtener_expiradas(mock_sesion, datetime.datetime.now())
    assert len(res) == 1

async def test_marcar_expirada(mock_sesion):
    reserva = Reserva(id=1, estado="pendiente_pago")
    await reserva_repository.marcar_expirada(mock_sesion, reserva)
    assert reserva.estado == "expirada"
    mock_sesion.flush.assert_awaited_once()
