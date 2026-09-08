import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.reserva_router import obtener_servicio
from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.main import app
from app.model.modelos import Reserva


@pytest.fixture
def servicio_mock():
    return AsyncMock()


@pytest.fixture
async def cliente(servicio_mock):
    app.dependency_overrides[obtener_servicio] = lambda: servicio_mock
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_salud(cliente):
    respuesta = await cliente.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


async def test_crear_reserva_sin_header(cliente):
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=1)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=3)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 422


async def test_crear_reserva_x_usuario_sub_vacio_retorna_422(cliente):
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=1)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=3)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 422


async def test_listar_reservas_sin_header_retorna_422(cliente):
    respuesta = await cliente.get(
        "/api/v1/reservas/",
        headers={"X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 422


async def test_listar_reservas_x_usuario_sub_vacio_retorna_422(cliente):
    respuesta = await cliente.get(
        "/api/v1/reservas/",
        headers={"X-Usuario-Sub": "", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 422


async def test_crear_reserva_x_usuario_sub_espacios_retorna_400(cliente, servicio_mock):
    servicio_mock.crear.side_effect = ReservaFechaInvalidaException(
        "El identificador de usuario no puede estar vacío"
    )
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=1)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=3)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "   ", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 400
    assert "identificador de usuario" in respuesta.json()["detail"]


async def test_listar_reservas_x_usuario_sub_espacios_retorna_400(cliente, servicio_mock):
    servicio_mock.listar_por_usuario.side_effect = ReservaFechaInvalidaException(
        "El identificador de usuario no puede estar vacío"
    )
    respuesta = await cliente.get(
        "/api/v1/reservas/",
        headers={"X-Usuario-Sub": "   ", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 400
    assert "identificador de usuario" in respuesta.json()["detail"]



async def test_crear_reserva_exitosa(cliente, servicio_mock):
    ahora = datetime.datetime.now()
    inicio = ahora + datetime.timedelta(hours=1)
    fin = ahora + datetime.timedelta(hours=3)
    reserva = Reserva(
        id=1,
        espacio_id=1,
        usuario_sub="user-123",
        fecha_inicio=inicio,
        fecha_fin=fin,
        estado="pendiente_pago",
        monto_total=20000.0,
        creado_en=ahora,
    )
    servicio_mock.crear.return_value = reserva

    datos = {
        "espacio_id": 1,
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["usuario_sub"] == "user-123"
    assert respuesta.json()["estado"] == "pendiente_pago"
    assert respuesta.json()["monto_total"] == 20000.0


async def test_crear_reserva_sin_rol_retorna_403(cliente):
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=1)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=3)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "invitado"},
    )
    assert respuesta.status_code == 403


async def test_crear_reserva_fecha_invalida_retorna_400(cliente, servicio_mock):
    servicio_mock.crear.side_effect = ReservaFechaInvalidaException()
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": (now + datetime.timedelta(hours=3)).isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=1)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 400
    assert "posterior" in respuesta.json()["detail"]


async def test_crear_reserva_solapamiento_retorna_409(cliente, servicio_mock):
    servicio_mock.crear.side_effect = ReservaSolapamientoException(1, "2026-09-10", "2026-09-11")
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": now.isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=2)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 409
    assert "ya está reservado" in respuesta.json()["detail"]


async def test_crear_reserva_espacio_inactivo_retorna_409(cliente, servicio_mock):
    servicio_mock.crear.side_effect = ReservaEspacioNoDisponibleException(1, "inactivo")
    now = datetime.datetime.now()
    datos = {
        "espacio_id": 1,
        "fecha_inicio": now.isoformat(),
        "fecha_fin": (now + datetime.timedelta(hours=2)).isoformat(),
    }
    respuesta = await cliente.post(
        "/api/v1/reservas/",
        json=datos,
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 409
    assert "no está disponible" in respuesta.json()["detail"]


async def test_listar_reservas_usuario(cliente, servicio_mock):
    servicio_mock.listar_por_usuario.return_value = []
    respuesta = await cliente.get(
        "/api/v1/reservas/",
        headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == []
    servicio_mock.listar_por_usuario.assert_awaited_once_with("user-123")


async def test_listar_reservas_admin(cliente, servicio_mock):
    servicio_mock.listar_todas.return_value = []
    respuesta = await cliente.get(
        "/api/v1/reservas/",
        headers={"X-Usuario-Sub": "admin-123", "X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == []
    servicio_mock.listar_todas.assert_awaited_once()


async def test_confirmar_pago_exitoso(cliente, servicio_mock):
    ahora = datetime.datetime.now()
    reserva = Reserva(
        id=1,
        espacio_id=1,
        usuario_sub="user-123",
        fecha_inicio=ahora,
        fecha_fin=ahora + datetime.timedelta(hours=2),
        estado="activa",
        monto_total=10000.0,
        creado_en=ahora,
    )
    servicio_mock.confirmar_pago.return_value = reserva
    respuesta = await cliente.post(
        "/api/v1/reservas/1/confirmar-pago",
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "activa"


async def test_confirmar_pago_sin_rol_admin_retorna_403(cliente):
    respuesta = await cliente.post(
        "/api/v1/reservas/1/confirmar-pago",
        headers={"X-Usuario-Roles": "residente"},
    )
    assert respuesta.status_code == 403


async def test_confirmar_pago_no_encontrada(cliente, servicio_mock):
    servicio_mock.confirmar_pago.return_value = None
    respuesta = await cliente.post(
        "/api/v1/reservas/999/confirmar-pago",
        headers={"X-Usuario-Roles": "admin"},
    )
    assert respuesta.status_code == 404


async def test_cabeceras_de_seguridad_presentes(cliente):
    respuesta = await cliente.get("/api/v1/health")
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in respuesta.headers
    assert respuesta.headers["Content-Security-Policy"] == "default-src 'self'"
    assert respuesta.headers["Server"] == "convivo"


