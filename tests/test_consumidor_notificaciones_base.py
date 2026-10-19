from unittest.mock import AsyncMock, MagicMock, patch

from app.events.consumidor_notificaciones_base import crear_procesador


def _fabrica_con(sesion):
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


def _mensaje(cuerpo: bytes = b'{"event_id":"e1","reserva_id":"1","email":"a@b.cl"}', redelivered=False):
    mensaje = MagicMock()
    mensaje.body = cuerpo
    mensaje.redelivered = redelivered
    mensaje.routing_key = "reserva_espacio_creada"
    mensaje.reject = AsyncMock()
    mensaje.ack = AsyncMock()
    mensaje.nack = AsyncMock()
    return mensaje


async def test_mensaje_invalido_va_a_dlq_sin_reservar_idempotencia():
    manejar = AsyncMock()
    with (
        patch("app.events.consumidor_notificaciones_base.fabrica_sesiones", _fabrica_con(AsyncMock())),
        patch("app.events.consumidor_notificaciones_base.idempotencia_repository") as repo,
    ):
        procesar = crear_procesador("worker_x", manejar)
        mensaje = _mensaje(cuerpo=b"{no es json")
        await procesar(mensaje)
    mensaje.reject.assert_awaited_once_with(requeue=False)
    manejar.assert_not_awaited()
    repo.reclamar.assert_not_called()


async def test_evento_duplicado_se_descarta_sin_trabajar():
    manejar = AsyncMock()
    with (
        patch("app.events.consumidor_notificaciones_base.fabrica_sesiones", _fabrica_con(AsyncMock())),
        patch("app.events.consumidor_notificaciones_base.idempotencia_repository") as repo,
    ):
        repo.reclamar = AsyncMock(return_value="COMPLETADO")
        procesar = crear_procesador("worker_x", manejar)
        await procesar(_mensaje())
    manejar.assert_not_awaited()


async def test_fallo_tecnico_primera_vez_hace_nack_con_requeue():
    manejar = AsyncMock(side_effect=RuntimeError("smtp caido"))
    with (
        patch("app.events.consumidor_notificaciones_base.fabrica_sesiones", _fabrica_con(AsyncMock())),
        patch("app.events.consumidor_notificaciones_base.idempotencia_repository") as repo,
    ):
        repo.reclamar = AsyncMock(return_value="NUEVO")
        repo.liberar = AsyncMock()
        procesar = crear_procesador("worker_x", manejar)
        mensaje = _mensaje(redelivered=False)
        await procesar(mensaje)
    mensaje.nack.assert_awaited_once_with(requeue=True)
    mensaje.reject.assert_not_awaited()


async def test_fallo_tecnico_segunda_vez_va_a_dlq():
    manejar = AsyncMock(side_effect=RuntimeError("smtp caido"))
    with (
        patch("app.events.consumidor_notificaciones_base.fabrica_sesiones", _fabrica_con(AsyncMock())),
        patch("app.events.consumidor_notificaciones_base.idempotencia_repository") as repo,
    ):
        repo.reclamar = AsyncMock(return_value="NUEVO")
        repo.liberar = AsyncMock()
        procesar = crear_procesador("worker_x", manejar)
        mensaje = _mensaje(redelivered=True)
        await procesar(mensaje)
    mensaje.reject.assert_awaited_once_with(requeue=False)


async def test_exito_completa_y_hace_ack():
    manejar = AsyncMock()
    with (
        patch("app.events.consumidor_notificaciones_base.fabrica_sesiones", _fabrica_con(AsyncMock())),
        patch("app.events.consumidor_notificaciones_base.idempotencia_repository") as repo,
    ):
        repo.reclamar = AsyncMock(return_value="NUEVO")
        repo.completar = AsyncMock()
        procesar = crear_procesador("worker_x", manejar)
        mensaje = _mensaje()
        await procesar(mensaje)
    manejar.assert_awaited_once()
    mensaje.ack.assert_awaited_once()
