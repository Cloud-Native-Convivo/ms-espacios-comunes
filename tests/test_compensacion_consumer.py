import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.events.compensacion_consumer import (
    procesar_compensacion,
    procesar_pago,
)
from app.model.modelos import Reserva


async def test_procesar_compensacion_json_invalido_hace_ack():
    mensaje = AsyncMock()
    mensaje.body = b"no es json valido"
    mensaje.ack = AsyncMock()
    mensaje.process = MagicMock()

    await procesar_compensacion(mensaje)

    mensaje.ack.assert_awaited_once()
    mensaje.process.assert_not_called()


async def test_procesar_compensacion_valido_usa_requeue():
    cuerpo = json.dumps(
        {
            "reserva_id": 1,
            "espacio_id": 2,
            "usuario_sub": "user-test",
            "fecha_inicio": "2026-09-10T10:00:00",
            "motivo": "pago rechazado",
        }
    ).encode("utf-8")

    mensaje = AsyncMock()
    mensaje.body = cuerpo
    mensaje.ack = AsyncMock()

    contexto_process = AsyncMock()
    contexto_process.__aenter__.return_value = None
    contexto_process.__aexit__.return_value = None
    mensaje.process = MagicMock(return_value=contexto_process)

    sesion_mock = AsyncMock()
    sesion_mock.__aenter__.return_value = sesion_mock
    sesion_mock.__aexit__.return_value = None

    with (
        patch("app.events.compensacion_consumer.fabrica_sesiones", return_value=sesion_mock),
        patch("app.events.compensacion_consumer.ReservaService") as mock_servicio_cls,
    ):
        servicio = AsyncMock()
        servicio.compensar_por_gasto_fallido.return_value = Reserva(id=1, estado="cancelada")
        mock_servicio_cls.return_value = servicio

        await procesar_compensacion(mensaje)

        mensaje.process.assert_called_once_with(requeue=True)
        servicio.compensar_por_gasto_fallido.assert_awaited_once_with(
            usuario_sub="user-test",
            espacio_id=2,
            fecha_inicio=datetime.datetime(2026, 9, 10, 10, 0),
            reserva_id=1,
        )
        sesion_mock.commit.assert_awaited_once()


async def test_procesar_pago_json_invalido_hace_ack():
    mensaje = AsyncMock()
    mensaje.body = b"{json: incompleto"
    mensaje.ack = AsyncMock()
    mensaje.process = MagicMock()

    await procesar_pago(mensaje)

    mensaje.ack.assert_awaited_once()
    mensaje.process.assert_not_called()


async def test_procesar_pago_valido_usa_requeue():
    cuerpo = json.dumps(
        {
            "reserva_id": 5,
            "monto_pagado": 15000.0,
            "metodo_pago": "debito",
        }
    ).encode("utf-8")

    mensaje = AsyncMock()
    mensaje.body = cuerpo
    mensaje.ack = AsyncMock()

    contexto_process = AsyncMock()
    contexto_process.__aenter__.return_value = None
    contexto_process.__aexit__.return_value = None
    mensaje.process = MagicMock(return_value=contexto_process)

    sesion_mock = AsyncMock()
    sesion_mock.__aenter__.return_value = sesion_mock
    sesion_mock.__aexit__.return_value = None

    with (
        patch("app.events.compensacion_consumer.fabrica_sesiones", return_value=sesion_mock),
        patch("app.events.compensacion_consumer.ReservaService") as mock_servicio_cls,
    ):
        servicio = AsyncMock()
        servicio.confirmar_pago.return_value = Reserva(id=5, estado="activa")
        mock_servicio_cls.return_value = servicio

        await procesar_pago(mensaje)

        mensaje.process.assert_called_once_with(requeue=True)
        servicio.confirmar_pago.assert_awaited_once_with(5)
        sesion_mock.commit.assert_awaited_once()


async def test_procesar_pago_esquema_invalido_hace_ack():
    # reserva_id debe ser un entero, pasar string no numérico
    cuerpo = json.dumps({"reserva_id": "no-es-entero"}).encode("utf-8")
    mensaje = AsyncMock()
    mensaje.body = cuerpo
    mensaje.ack = AsyncMock()
    mensaje.process = MagicMock()

    await procesar_pago(mensaje)

    mensaje.ack.assert_awaited_once()
    mensaje.process.assert_not_called()


async def test_procesar_compensacion_fallo_operacional_reencola_y_registra_error():
    cuerpo = json.dumps(
        {
            "reserva_id": 1,
            "espacio_id": 2,
            "usuario_sub": "user-test",
            "fecha_inicio": "2026-09-10T10:00:00",
            "motivo": "pago rechazado",
        }
    ).encode("utf-8")

    mensaje = AsyncMock()
    mensaje.body = cuerpo
    mensaje.ack = AsyncMock()

    contexto_process = AsyncMock()
    contexto_process.__aenter__.return_value = None
    contexto_process.__aexit__.return_value = None
    mensaje.process = MagicMock(return_value=contexto_process)

    sesion_mock = AsyncMock()
    sesion_mock.__aenter__.return_value = sesion_mock
    sesion_mock.__aexit__.return_value = None

    with (
        patch("app.events.compensacion_consumer.fabrica_sesiones", return_value=sesion_mock),
        patch("app.events.compensacion_consumer.ReservaService") as mock_servicio_cls,
        patch("app.events.compensacion_consumer.logger") as mock_logger,
    ):
        servicio = AsyncMock()
        servicio.compensar_por_gasto_fallido.side_effect = RuntimeError("Error en conexión BD")
        mock_servicio_cls.return_value = servicio

        # Debe capturar el error con logger.exception sin romper el consumidor
        await procesar_compensacion(mensaje)

        mensaje.process.assert_called_once_with(requeue=True)
        contexto_process.__aexit__.assert_awaited_once()
        mock_logger.exception.assert_called_once()


async def test_procesar_pago_fallo_operacional_reencola_y_registra_error():
    cuerpo = json.dumps(
        {
            "reserva_id": 5,
            "monto_pagado": 15000.0,
            "metodo_pago": "debito",
        }
    ).encode("utf-8")

    mensaje = AsyncMock()
    mensaje.body = cuerpo
    mensaje.ack = AsyncMock()

    contexto_process = AsyncMock()
    contexto_process.__aenter__.return_value = None
    contexto_process.__aexit__.return_value = None
    mensaje.process = MagicMock(return_value=contexto_process)

    sesion_mock = AsyncMock()
    sesion_mock.__aenter__.return_value = sesion_mock
    sesion_mock.__aexit__.return_value = None

    with (
        patch("app.events.compensacion_consumer.fabrica_sesiones", return_value=sesion_mock),
        patch("app.events.compensacion_consumer.ReservaService") as mock_servicio_cls,
        patch("app.events.compensacion_consumer.logger") as mock_logger,
    ):
        servicio = AsyncMock()
        servicio.confirmar_pago.side_effect = RuntimeError("Caída de base de datos")
        mock_servicio_cls.return_value = servicio

        # Debe capturar el error con logger.exception sin romper el consumidor
        await procesar_pago(mensaje)

        mensaje.process.assert_called_once_with(requeue=True)
        contexto_process.__aexit__.assert_awaited_once()
        mock_logger.exception.assert_called_once()
