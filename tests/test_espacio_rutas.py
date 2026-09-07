import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.espacio_router import obtener_servicio
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

