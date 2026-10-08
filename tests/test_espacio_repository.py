import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.repository import espacio_repository
from app.model.modelos import Espacio
from app.dto.esquemas import CrearEspacioRequest

@pytest.fixture
def mock_sesion():
    return AsyncMock(spec=AsyncSession)

async def test_obtener_todos(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Espacio(id=1)]
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_todos(mock_sesion)
    assert len(res) == 1

async def test_obtener_por_id(mock_sesion):
    esp = Espacio(id=1)
    mock_sesion.get.return_value = esp
    res = await espacio_repository.obtener_por_id(mock_sesion, 1)
    assert res.id == 1

async def test_obtener_por_id_con_bloqueo(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = Espacio(id=1)
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_por_id(mock_sesion, 1, con_bloqueo=True)
    assert res.id == 1
    mock_sesion.execute.assert_awaited_once()

async def test_crear(mock_sesion):
    esp = Espacio(nombre="A", capacidad=10)
    mock_sesion.add = AsyncMock()
    mock_sesion.flush = AsyncMock()
    mock_sesion.refresh = AsyncMock()
    res = await espacio_repository.crear(mock_sesion, esp)
    assert res.nombre == "A"

async def test_actualizar(mock_sesion):
    esp = Espacio(id=1, nombre="A")
    res = await espacio_repository.actualizar(mock_sesion, esp)
    mock_sesion.flush.assert_awaited_once()

async def test_eliminar_fisico(mock_sesion):
    esp = Espacio(id=1)
    await espacio_repository.eliminar_fisico(mock_sesion, esp)
    mock_sesion.delete.assert_awaited_once_with(esp)

async def test_contar_reservas_asociadas(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one.return_value = 5
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.contar_reservas_asociadas(mock_sesion, 1)
    assert res == 5
