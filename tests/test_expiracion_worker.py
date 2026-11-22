import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dto.kafka_eventos import EventoEspacioV1
from app.events.expiracion_worker import worker_expiracion
from app.model.modelos import EventoOutbox, EventoOutboxKafka


def _fabrica_con(sesion):
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


async def test_worker_marca_expiradas_y_propaga_cancelacion_en_espera():
    sesion = AsyncMock()
    sesion.get = AsyncMock(return_value=MagicMock(nombre="Espacio", condominio_id=1))
    reserva = MagicMock(
        id=1,
        espacio_id=1,
        usuario_sub="u1",
        usuario_email=None,
        estado="expirada",
        fecha_inicio=datetime.datetime.now(),
        fecha_fin=datetime.datetime.now(),
        monto_total=1000.0,
        expira_en=None,
    )
    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", _fabrica_con(sesion)),
        patch("app.events.expiracion_worker.reserva_repository") as repo,
        patch("app.events.expiracion_worker.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        repo.obtener_expiradas = AsyncMock(return_value=[reserva])
        repo.marcar_expirada = AsyncMock()
        repo.obtener_por_expirar = AsyncMock(return_value=[])
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)

    repo.marcar_expirada.assert_awaited_once_with(sesion, reserva)
    sesion.commit.assert_awaited_once()


async def test_worker_re_lanza_cancelacion_durante_procesamiento():
    fabrica = MagicMock(side_effect=asyncio.CancelledError)
    with patch("app.events.expiracion_worker.fabrica_sesiones", fabrica):
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)


async def test_worker_registra_error_y_sigue_en_bucle():
    fabrica = MagicMock(side_effect=RuntimeError("db caida"))
    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", fabrica),
        patch("app.events.expiracion_worker.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)
    fabrica.assert_called_once()


async def test_worker_agrega_evento_outbox_reserva_expirada_en_la_misma_sesion():
    sesion = AsyncMock()
    espacio = MagicMock(nombre="Quincho", condominio_id=1)
    sesion.get = AsyncMock(return_value=espacio)
    reserva = MagicMock(
        id=9,
        espacio_id=1,
        usuario_sub="u1",
        usuario_email="a@b.cl",
        estado="expirada",
        fecha_inicio=datetime.datetime.now(),
        fecha_fin=datetime.datetime.now(),
        monto_total=1000.0,
        expira_en=None,
    )
    with (
        patch("app.events.expiracion_worker.fabrica_sesiones", _fabrica_con(sesion)),
        patch("app.events.expiracion_worker.reserva_repository") as repo,
        patch("app.events.expiracion_worker.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        repo.obtener_expiradas = AsyncMock(return_value=[reserva])
        repo.marcar_expirada = AsyncMock()
        repo.obtener_por_expirar = AsyncMock(return_value=[])
        with pytest.raises(asyncio.CancelledError):
            await worker_expiracion(intervalo_segundos=0)

    # Una fila por broker, ambas en la misma sesión que marca la expiración.
    rabbit, kafka = (c.args[0] for c in sesion.add.call_args_list)
    assert isinstance(rabbit, EventoOutbox)
    assert rabbit.tipo_evento == "reserva_expirada"
    assert isinstance(kafka, EventoOutboxKafka)
    evento = EventoEspacioV1.model_validate_json(kafka.carga_util)
    assert evento.tipo == "RESERVA_EXPIRADA"
    assert evento.reserva_id == 9
    assert evento.datos.estado_anterior == "pendiente_pago"
    sesion.commit.assert_awaited_once()
