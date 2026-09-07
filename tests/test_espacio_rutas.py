import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.espacio_router import obtener_servicio
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.main import app
from app.model.modelos import Espacio


@pytest.fixture
def servicio_mock():
    mock = AsyncMock()
    return mock


@pytest.fixture
async def cliente(servicio_mock):
    app.dependency_overrides[obtener_servicio] = lambda: servicio_mock
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_listar_espacios_vacio(cliente, servicio_mock):
    servicio_mock.listar_todos.return_value = []
    respuesta = await cliente.get("/api/v1/espacios/")
    assert respuesta.status_code == 200
    assert respuesta.json() == []


async def test_obtener_espacio_existente(cliente, servicio_mock):
    ahora = datetime.datetime.now()
    espacio = Espacio(
        id=1,
        nombre="Sala Multiuso",
        descripcion="Sala grande",
        capacidad=50,
        ubicacion="Piso 1",
        estado="activo",
        creado_en=ahora,
        actualizado_en=ahora,
    )
    servicio_mock.obtener_por_id.return_value = espacio

    respuesta = await cliente.get("/api/v1/espacios/1")
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Sala Multiuso"
    assert respuesta.json()["id"] == 1


async def test_obtener_espacio_no_encontrado(cliente, servicio_mock):
    servicio_mock.obtener_por_id.return_value = None

    respuesta = await cliente.get("/api/v1/espacios/999")
    assert respuesta.status_code == 404
    assert "no encontrado" in respuesta.json()["detail"]


async def test_crear_espacio_exitoso(cliente, servicio_mock):
    ahora = datetime.datetime.now()
    espacio = Espacio(
        id=2,
        nombre="Piscina",
        capacidad=20,
        tarifa_hora=12000.0,
        estado="activo",
        creado_en=ahora,
        actualizado_en=ahora,
    )
    servicio_mock.crear.return_value = espacio

    datos = {"nombre": "Piscina", "capacidad": 20, "tarifa_hora": 12000.0}
    respuesta = await cliente.post(
        "/api/v1/espacios/",
        json=datos,
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["nombre"] == "Piscina"
    assert respuesta.json()["tarifa_hora"] == 12000.0


async def test_crear_espacio_sin_rol_admin_retorna_403(cliente):
    datos = {"nombre": "Piscina", "capacidad": 20}
    respuesta = await cliente.post(
        "/api/v1/espacios/",
        json=datos,
        headers={"X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 403
    assert "Permisos insuficientes" in respuesta.json()["detail"]


async def test_crear_espacio_datos_invalidos(cliente):
    respuesta = await cliente.post(
        "/api/v1/espacios/",
        json={"capacidad": "invalido"},
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 422


async def test_actualizar_espacio_exitoso(cliente, servicio_mock):
    ahora = datetime.datetime.now()
    espacio = Espacio(
        id=1,
        nombre="Piscina Climatizada",
        capacidad=25,
        tarifa_hora=15000.0,
        estado="activo",
        creado_en=ahora,
        actualizado_en=ahora,
    )
    servicio_mock.actualizar.return_value = espacio

    datos = {"nombre": "Piscina Climatizada", "capacidad": 25}
    respuesta = await cliente.put(
        "/api/v1/espacios/1",
        json=datos,
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Piscina Climatizada"


async def test_actualizar_espacio_sin_rol_admin_retorna_403(cliente):
    datos = {"nombre": "Piscina Climatizada", "capacidad": 25}
    respuesta = await cliente.put(
        "/api/v1/espacios/1",
        json=datos,
    )
    assert respuesta.status_code == 403


async def test_eliminar_espacio_exitoso_retorna_204(cliente, servicio_mock):
    servicio_mock.eliminar.return_value = "eliminado"

    respuesta = await cliente.delete(
        "/api/v1/espacios/1",
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 204
    assert respuesta.content == b""


async def test_eliminar_espacio_sin_rol_admin_retorna_403(cliente):
    respuesta = await cliente.delete(
        "/api/v1/espacios/1",
        headers={"X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 403
    assert "Permisos insuficientes" in respuesta.json()["detail"]


async def test_eliminar_espacio_no_encontrado_retorna_404(cliente, servicio_mock):
    servicio_mock.eliminar.side_effect = EspacioNoEncontradoException(999)

    respuesta = await cliente.delete(
        "/api/v1/espacios/999",
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 404
    assert "no encontrado" in respuesta.json()["detail"]


async def test_servicio_eliminar_sin_reservas_elimina_fisico():
    from app.service.espacio_service import EspacioService

    repo_mock = AsyncMock()
    espacio = Espacio(id=1, nombre="Quincho", capacidad=15, estado="activo")
    repo_mock.obtener_por_id.return_value = espacio
    repo_mock.contar_reservas_asociadas.return_value = 0

    servicio = EspacioService(repo_mock)
    resultado = await servicio.eliminar(1)

    assert resultado == "eliminado"
    repo_mock.eliminar_fisico.assert_awaited_once_with(espacio)


async def test_servicio_eliminar_con_reservas_inactiva():
    from app.service.espacio_service import EspacioService

    repo_mock = AsyncMock()
    espacio = Espacio(id=2, nombre="Piscina", capacidad=20, estado="activo")
    repo_mock.obtener_por_id.return_value = espacio
    repo_mock.contar_reservas_asociadas.return_value = 3

    servicio = EspacioService(repo_mock)
    resultado = await servicio.eliminar(2)

    assert resultado == "inactivado"
    assert espacio.estado == "inactivo"
    repo_mock.actualizar.assert_awaited_once_with(espacio)
    repo_mock.eliminar_fisico.assert_not_called()


async def test_servicio_eliminar_no_encontrado_lanza_excepcion():
    from app.service.espacio_service import EspacioService

    repo_mock = AsyncMock()
    repo_mock.obtener_por_id.return_value = None

    servicio = EspacioService(repo_mock)
    with pytest.raises(EspacioNoEncontradoException):
        await servicio.eliminar(999)


async def test_cors_preflight_options(cliente):
    respuesta = await cliente.options(
        "/api/v1/espacios/",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,x-usuario-roles",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert "DELETE" in respuesta.headers["access-control-allow-methods"]




