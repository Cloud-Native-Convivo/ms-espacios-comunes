import pytest
from unittest.mock import AsyncMock, patch
from app.service import espacio_service
from app.model.modelos import Espacio
from app.dto.esquemas import CrearEspacioRequest, ActualizarEspacioRequest
from app.exception.espacio_exception import EspacioNoEncontradoException

@pytest.fixture
def mock_sesion(): return AsyncMock()

@pytest.fixture
def mock_repo():
    with patch("app.service.espacio_service.espacio_repository") as m:
        m.obtener_todos = AsyncMock()
        m.obtener_por_id = AsyncMock()
        m.crear = AsyncMock()
        m.actualizar = AsyncMock()
        m.eliminar_fisico = AsyncMock()
        m.contar_reservas_asociadas = AsyncMock()
        yield m

async def test_listar_todos(mock_sesion, mock_repo):
    mock_repo.obtener_todos.return_value = [Espacio(id=1, nombre="A")]
    res = await espacio_service.listar_todos(mock_sesion)
    assert len(res) == 1

async def test_obtener_por_id(mock_sesion, mock_repo):
    mock_repo.obtener_por_id.return_value = Espacio(id=1, nombre="A")
    res = await espacio_service.obtener_por_id(mock_sesion, 1)
    assert res.nombre == "A"

async def test_obtener_por_id_no_encontrado(mock_sesion, mock_repo):
    mock_repo.obtener_por_id.return_value = None
    res = await espacio_service.obtener_por_id(mock_sesion, 1)
    assert res is None

async def test_crear(mock_sesion, mock_repo):
    req = CrearEspacioRequest(nombre="A", capacidad=10, tarifa_hora=100.0)
    mock_repo.crear.return_value = Espacio(id=1, nombre="A")
    res = await espacio_service.crear(mock_sesion, req)
    assert res.id == 1

async def test_actualizar(mock_sesion, mock_repo):
    req = ActualizarEspacioRequest(nombre="B")
    espacio = Espacio(id=1, nombre="A")
    mock_repo.obtener_por_id.return_value = espacio
    mock_repo.actualizar.return_value = Espacio(id=1, nombre="B")
    res = await espacio_service.actualizar(mock_sesion, 1, req)
    assert res.nombre == "B"

async def test_eliminar_sin_reservas(mock_sesion, mock_repo):
    espacio = Espacio(id=1, estado="activo")
    mock_repo.obtener_por_id.return_value = espacio
    mock_repo.contar_reservas_asociadas.return_value = 0
    res = await espacio_service.eliminar(mock_sesion, 1)
    assert res == "eliminado"
    mock_repo.eliminar_fisico.assert_awaited_once_with(mock_sesion, espacio)

async def test_eliminar_con_reservas(mock_sesion, mock_repo):
    espacio = Espacio(id=1, estado="activo")
    mock_repo.obtener_por_id.return_value = espacio
    mock_repo.contar_reservas_asociadas.return_value = 5
    res = await espacio_service.eliminar(mock_sesion, 1)
    assert res == "inactivado"
    mock_repo.actualizar.assert_awaited_once_with(mock_sesion, espacio)
    assert espacio.estado == "inactivo"

async def test_actualizar_campos_completos(mock_sesion, mock_repo):
    req = ActualizarEspacioRequest(nombre="C", capacidad=20, tarifa_hora=200.0, descripcion="D", ubicacion="U", estado="inactivo")
    espacio = Espacio(id=1, nombre="A")
    mock_repo.obtener_por_id.return_value = espacio
    mock_repo.actualizar.return_value = espacio
    res = await espacio_service.actualizar(mock_sesion, 1, req)
    assert res.nombre == "C"
    assert res.capacidad == 20
    assert res.tarifa_hora == 200.0
    assert res.descripcion == "D"
    assert res.ubicacion == "U"
    assert res.estado == "inactivo"

async def test_actualizar_no_encontrado(mock_sesion, mock_repo):
    req = ActualizarEspacioRequest(nombre="B")
    mock_repo.obtener_por_id.return_value = None
    with pytest.raises(EspacioNoEncontradoException):
        await espacio_service.actualizar(mock_sesion, 1, req)

async def test_eliminar_no_encontrado(mock_sesion, mock_repo):
    mock_repo.obtener_por_id.return_value = None
    with pytest.raises(EspacioNoEncontradoException):
        await espacio_service.eliminar(mock_sesion, 1)
