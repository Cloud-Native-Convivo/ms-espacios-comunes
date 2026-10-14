import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.model.modelos import Reserva


@pytest.fixture
def mock_sesion():
    return AsyncMock()


@pytest.fixture
async def cliente():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _crear_reserva_mock(id: int = 1, usuario_sub: str = "user-123"):
    ahora = datetime.datetime.now()
    reserva = Reserva(
        id=id,
        espacio_id=1,
        usuario_sub=usuario_sub,
        fecha_inicio=ahora,
        fecha_fin=ahora + datetime.timedelta(hours=2),
        estado="activa",
        monto_total=10000.0,
        creado_en=ahora,
    )
    return reserva


async def test_residente_cancela_su_propia_reserva_exito(cliente):
    reserva = _crear_reserva_mock(id=1, usuario_sub="user-123")
    reserva_cancelada = _crear_reserva_mock(id=1, usuario_sub="user-123")
    reserva_cancelada.estado = "cancelada"

    with patch("app.api.v1.reserva_router.reserva_repository.obtener_por_id", new_callable=AsyncMock) as mock_get, \
         patch("app.api.v1.reserva_router.reserva_service.cancelar_por_id", new_callable=AsyncMock) as mock_cancel:
        mock_get.return_value = reserva
        mock_cancel.return_value = reserva_cancelada

        resp = await cliente.delete(
            "/api/v1/reservas/1",
            headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "cancelada"


async def test_residente_cancela_reserva_ajena_retorna_403(cliente):
    reserva_ajena = _crear_reserva_mock(id=2, usuario_sub="user-otro")

    with patch("app.api.v1.reserva_router.reserva_repository.obtener_por_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = reserva_ajena

        resp = await cliente.delete(
            "/api/v1/reservas/2",
            headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
        )
        assert resp.status_code == 403
        assert "No autorizado" in resp.json()["detail"]


async def test_admin_cancela_reserva_ajena_exito(cliente):
    reserva_ajena = _crear_reserva_mock(id=3, usuario_sub="user-otro")
    reserva_cancelada = _crear_reserva_mock(id=3, usuario_sub="user-otro")
    reserva_cancelada.estado = "cancelada"

    with patch("app.api.v1.reserva_router.reserva_repository.obtener_por_id", new_callable=AsyncMock) as mock_get, \
         patch("app.api.v1.reserva_router.reserva_service.cancelar_por_id", new_callable=AsyncMock) as mock_cancel:
        mock_get.return_value = reserva_ajena
        mock_cancel.return_value = reserva_cancelada

        resp = await cliente.delete(
            "/api/v1/reservas/3",
            headers={"X-Usuario-Sub": "admin-sub", "X-Usuario-Roles": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "cancelada"


async def test_conserje_cancela_reserva_ajena_exito(cliente):
    reserva_ajena = _crear_reserva_mock(id=4, usuario_sub="user-otro")
    reserva_cancelada = _crear_reserva_mock(id=4, usuario_sub="user-otro")
    reserva_cancelada.estado = "cancelada"

    with patch("app.api.v1.reserva_router.reserva_repository.obtener_por_id", new_callable=AsyncMock) as mock_get, \
         patch("app.api.v1.reserva_router.reserva_service.cancelar_por_id", new_callable=AsyncMock) as mock_cancel:
        mock_get.return_value = reserva_ajena
        mock_cancel.return_value = reserva_cancelada

        resp = await cliente.delete(
            "/api/v1/reservas/4",
            headers={"X-Usuario-Sub": "conserje-sub", "X-Usuario-Roles": "conserje"},
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "cancelada"


async def test_cancelar_sin_header_sub_retorna_401(cliente):
    resp = await cliente.delete(
        "/api/v1/reservas/1",
        headers={"X-Usuario-Roles": "residente"},
    )
    assert resp.status_code == 401


async def test_cancelar_sub_vacio_retorna_401(cliente):
    resp = await cliente.delete(
        "/api/v1/reservas/1",
        headers={"X-Usuario-Sub": "   ", "X-Usuario-Roles": "residente"},
    )
    assert resp.status_code == 401


async def test_cancelar_reserva_no_encontrada_retorna_404(cliente):
    with patch("app.api.v1.reserva_router.reserva_repository.obtener_por_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        resp = await cliente.delete(
            "/api/v1/reservas/999",
            headers={"X-Usuario-Sub": "user-123", "X-Usuario-Roles": "residente"},
        )
        assert resp.status_code == 404
