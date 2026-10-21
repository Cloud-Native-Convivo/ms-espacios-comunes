from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.esquemas import CrearEspacioRequest
from app.model.modelos import Espacio
from app.repository import espacio_repository


@pytest.fixture
def mock_sesion():
    return AsyncMock(spec=AsyncSession)

async def test_obtener_todos_filtra_por_condominio(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Espacio(id=1, condominio_id=1)]
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_todos(mock_sesion, 1)
    assert len(res) == 1

async def test_obtener_todos_sin_condominio_no_filtra(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalars().all.return_value = [Espacio(id=1, condominio_id=1), Espacio(id=2, condominio_id=2)]
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_todos(mock_sesion)
    assert len(res) == 2

async def test_obtener_por_id_filtra_por_condominio(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = Espacio(id=1, condominio_id=1)
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_por_id(mock_sesion, 1, condominio_id=1)
    assert res.id == 1

async def test_obtener_por_id_de_otro_condominio_devuelve_none(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None  # el WHERE del condominio no matcheo
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_por_id(mock_sesion, 1, condominio_id=99)
    assert res is None

async def test_obtener_por_id_con_bloqueo(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = Espacio(id=1, condominio_id=1)
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.obtener_por_id(mock_sesion, 1, condominio_id=1, con_bloqueo=True)
    assert res.id == 1
    mock_sesion.execute.assert_awaited_once()

async def test_crear(mock_sesion):
    esp = Espacio(nombre="A", capacidad=10, condominio_id=1)
    mock_sesion.add = AsyncMock()
    mock_sesion.flush = AsyncMock()
    mock_sesion.refresh = AsyncMock()
    res = await espacio_repository.crear(mock_sesion, esp)
    assert res.nombre == "A"

async def test_actualizar(mock_sesion):
    esp = Espacio(id=1, nombre="A", condominio_id=1)
    res = await espacio_repository.actualizar(mock_sesion, esp)
    mock_sesion.flush.assert_awaited_once()

async def test_eliminar_fisico(mock_sesion):
    esp = Espacio(id=1, condominio_id=1)
    await espacio_repository.eliminar_fisico(mock_sesion, esp)
    mock_sesion.delete.assert_awaited_once_with(esp)

async def test_contar_reservas_asociadas(mock_sesion):
    res_mock = MagicMock()
    res_mock.scalar_one.return_value = 5
    mock_sesion.execute.return_value = res_mock
    res = await espacio_repository.contar_reservas_asociadas(mock_sesion, 1)
    assert res == 5
