"""Outbox de Kafka contra una base real (SQLite en memoria) y relay con productor falso.

Técnica: tabla de decisión para las transiciones de estado del espacio
(estado anterior x estado pedido -> evento o nada) y partición de equivalencia
para las transiciones de reserva (estado que cambia / estado ya cerrado).
"""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.dto.esquemas import (
    ActualizarEspacioRequest,
    CrearEspacioRequest,
    CrearReservaRequest,
)
from app.dto.kafka_eventos import TOPICO_HISTORIAL, EventoEspacioV1
from app.events import kafka_outbox
from app.model.modelos import Base, Espacio, EventoOutboxKafka, Reserva
from app.repository import kafka_outbox_repository
from app.service import espacio_service, reserva_service
from app.util.tiempo import ahora_utc

CONDOMINIO = 7


@pytest_asyncio.fixture
async def fabrica():
    motor = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    await motor.dispose()


async def _eventos(fabrica) -> list[EventoEspacioV1]:
    async with fabrica() as sesion:
        filas = (
            await sesion.execute(select(EventoOutboxKafka).order_by(EventoOutboxKafka.id))
        ).scalars().all()
    for fila in filas:
        assert fila.topico == TOPICO_HISTORIAL
        assert fila.procesado is False
    eventos = [EventoEspacioV1.model_validate_json(f.carga_util) for f in filas]
    assert [f.clave for f in filas] == [str(e.espacio_id) for e in eventos]
    return eventos


async def _crear_espacio(fabrica, estado: str = "activo") -> int:
    async with fabrica() as sesion:
        espacio = await espacio_service.crear(
            sesion,
            CrearEspacioRequest(condominio_id=CONDOMINIO, nombre="Quincho", capacidad=10),
            actor_sub="admin-1",
        )
        espacio.estado = estado
        await sesion.commit()
        return espacio.id


async def _actualizar(fabrica, espacio_id: int, **campos) -> None:
    async with fabrica() as sesion:
        await espacio_service.actualizar(
            sesion, espacio_id, CONDOMINIO, ActualizarEspacioRequest(**campos), actor_sub="admin-1"
        )
        await sesion.commit()


async def _crear_reserva(fabrica, espacio_id: int) -> int:
    inicio = ahora_utc() + datetime.timedelta(days=1)
    async with fabrica() as sesion:
        reserva = await reserva_service.crear(
            sesion,
            CrearReservaRequest(
                espacio_id=espacio_id, fecha_inicio=inicio, fecha_fin=inicio + datetime.timedelta(hours=2)
            ),
            usuario_sub="residente-1",
        )
        await sesion.commit()
        return reserva.id


async def test_crear_espacio_registra_evento_en_la_misma_transaccion(fabrica):
    espacio_id = await _crear_espacio(fabrica)

    (evento,) = await _eventos(fabrica)
    assert evento.tipo == "ESPACIO_CREADO"
    assert (evento.condominio_id, evento.espacio_id) == (CONDOMINIO, espacio_id)
    assert evento.actor_sub == "admin-1"
    assert evento.datos.estado_nuevo == "activo"


async def test_rollback_no_deja_evento(fabrica):
    async with fabrica() as sesion:
        await espacio_service.crear(
            sesion, CrearEspacioRequest(condominio_id=CONDOMINIO, nombre="X", capacidad=1)
        )
        await sesion.rollback()
    assert await _eventos(fabrica) == []


@pytest.mark.parametrize(
    ("anterior", "pedido", "tipo"),
    [
        ("activo", "mantenimiento", "ESPACIO_EN_MANTENCION"),
        ("activo", "inactivo", "ESPACIO_DESHABILITADO"),
        ("mantenimiento", "activo", "ESPACIO_HABILITADO"),
        ("inactivo", "activo", "ESPACIO_HABILITADO"),
        ("activo", "activo", None),
    ],
)
async def test_tabla_de_transiciones_de_estado(fabrica, anterior, pedido, tipo):
    espacio_id = await _crear_espacio(fabrica, estado=anterior)
    await _actualizar(fabrica, espacio_id, estado=pedido)

    eventos = (await _eventos(fabrica))[1:]  # [0] es ESPACIO_CREADO
    if tipo is None:
        assert eventos == []
    else:
        (evento,) = eventos
        assert evento.tipo == tipo
        assert (evento.datos.estado_anterior, evento.datos.estado_nuevo) == (anterior, pedido)


async def test_cambio_de_campos_y_estado_emite_dos_eventos(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    await _actualizar(fabrica, espacio_id, nombre="Quincho grande", estado="mantenimiento")

    assert [e.tipo for e in await _eventos(fabrica)] == [
        "ESPACIO_CREADO", "ESPACIO_ACTUALIZADO", "ESPACIO_EN_MANTENCION",
    ]


async def test_actualizar_con_los_mismos_valores_no_emite(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    await _actualizar(fabrica, espacio_id, nombre="Quincho", capacidad=10, tarifa_hora=0.0)

    assert [e.tipo for e in await _eventos(fabrica)] == ["ESPACIO_CREADO"]


async def test_eliminar_sin_reservas_emite_deshabilitado_eliminado(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    async with fabrica() as sesion:
        assert await espacio_service.eliminar(sesion, espacio_id, CONDOMINIO) == "eliminado"
        await sesion.commit()

    evento = (await _eventos(fabrica))[-1]
    assert evento.tipo == "ESPACIO_DESHABILITADO"
    assert (evento.datos.estado_anterior, evento.datos.estado_nuevo) == ("activo", "eliminado")


async def test_eliminar_con_reservas_inactiva_una_sola_vez(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    await _crear_reserva(fabrica, espacio_id)
    for _ in range(2):
        async with fabrica() as sesion:
            assert await espacio_service.eliminar(sesion, espacio_id, CONDOMINIO) == "inactivado"
            await sesion.commit()

    eventos = await _eventos(fabrica)
    assert [e.tipo for e in eventos] == ["ESPACIO_CREADO", "RESERVA_CREADA", "ESPACIO_DESHABILITADO"]
    assert eventos[-1].datos.estado_nuevo == "inactivo"


async def test_crear_reserva_toma_condominio_del_espacio(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    reserva_id = await _crear_reserva(fabrica, espacio_id)

    evento = (await _eventos(fabrica))[-1]
    assert evento.tipo == "RESERVA_CREADA"
    assert (evento.condominio_id, evento.espacio_id, evento.reserva_id) == (
        CONDOMINIO, espacio_id, reserva_id,
    )
    assert evento.actor_sub == "residente-1"
    assert evento.datos.estado_nuevo == "pendiente_pago"
    assert evento.datos.fecha_inicio.utcoffset() == datetime.timedelta(0)


async def test_cancelar_emite_una_vez_con_actor(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    reserva_id = await _crear_reserva(fabrica, espacio_id)
    for _ in range(2):
        async with fabrica() as sesion:
            await reserva_service.cancelar_por_id(sesion, reserva_id, actor_sub="admin-1")
            await sesion.commit()

    eventos = [e for e in await _eventos(fabrica) if e.tipo == "RESERVA_CANCELADA"]
    assert len(eventos) == 1
    assert eventos[0].actor_sub == "admin-1"
    assert (eventos[0].datos.estado_anterior, eventos[0].datos.estado_nuevo) == (
        "pendiente_pago", "cancelada",
    )


async def test_confirmar_pago_emite_una_vez(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    reserva_id = await _crear_reserva(fabrica, espacio_id)
    for _ in range(2):
        async with fabrica() as sesion:
            reserva = await reserva_service.confirmar_pago(sesion, reserva_id)
            await sesion.commit()
    assert reserva.estado == "activa"

    eventos = [e for e in await _eventos(fabrica) if e.tipo == "RESERVA_CONFIRMADA"]
    assert len(eventos) == 1
    assert eventos[0].actor_sub is None


async def test_compensacion_por_evento_emite_cancelada_sin_actor(fabrica):
    espacio_id = await _crear_espacio(fabrica)
    reserva_id = await _crear_reserva(fabrica, espacio_id)
    async with fabrica() as sesion:
        reserva = await sesion.get(Reserva, reserva_id)
        await reserva_service.compensar_por_gasto_fallido(
            sesion, usuario_sub="residente-1", espacio_id=espacio_id,
            fecha_inicio=reserva.fecha_inicio,
        )
        await sesion.commit()

    evento = (await _eventos(fabrica))[-1]
    assert evento.tipo == "RESERVA_CANCELADA"
    assert evento.actor_sub is None


async def test_pendientes_en_orden_sin_procesados(fabrica):
    async with fabrica() as sesion:
        filas = [_fila(i) for i in range(1, 5)]
        filas[1].procesado = True
        sesion.add_all(filas)
        await sesion.commit()
    async with fabrica() as sesion:
        pendientes = await kafka_outbox_repository.obtener_pendientes(sesion)
    assert [p.clave for p in pendientes] == ["1", "3", "4"]


# --- Relay ---

def _fila(espacio_id: int) -> EventoOutboxKafka:
    evento = EventoEspacioV1(tipo="ESPACIO_CREADO", condominio_id=1, espacio_id=espacio_id)
    return EventoOutboxKafka(
        event_id=str(evento.event_id), topico=TOPICO_HISTORIAL,
        clave=evento.clave, carga_util=evento.model_dump_json(), procesado=False,
    )


def _productor(resultados: list) -> MagicMock:
    """send() devuelve un futuro por mensaje: None = ack, Exception = fallo del broker."""
    productor = MagicMock()

    async def _send(topico, value, key):
        futuro = asyncio.get_running_loop().create_future()
        resultado = resultados.pop(0)
        if isinstance(resultado, Exception):
            futuro.set_exception(resultado)
        else:
            futuro.set_result(resultado)
        return futuro

    productor.send = AsyncMock(side_effect=_send)
    return productor


async def test_publicar_marca_procesados_tras_el_ack_con_su_clave():
    filas = [_fila(3), _fila(4)]
    productor = _productor([None, None])

    await kafka_outbox.publicar_pendientes(productor, filas)

    assert all(f.procesado for f in filas)
    llamadas = productor.send.await_args_list
    assert [c.kwargs["key"] for c in llamadas] == ["3", "4"]
    assert all(c.args[0] == TOPICO_HISTORIAL for c in llamadas)
    assert isinstance(llamadas[0].kwargs["value"], EventoEspacioV1)


async def test_publicar_con_fallo_del_broker_no_marca_los_siguientes():
    filas = [_fila(3), _fila(4)]
    productor = _productor([None, RuntimeError("NotEnoughReplicas")])

    with pytest.raises(RuntimeError):
        await kafka_outbox.publicar_pendientes(productor, filas)
    # El llamador no hace commit: ambas siguen pendientes en la base y se reenvían.
    assert [f.procesado for f in filas] == [True, False]


async def test_relay_publica_hace_commit_y_detiene_el_productor():
    sesion = AsyncMock()
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    productor = _productor([None])
    productor.start = AsyncMock()
    productor.stop = AsyncMock()
    filas = [_fila(1)]
    with (
        patch.object(kafka_outbox, "crear_productor_kafka", return_value=productor),
        patch.object(kafka_outbox, "fabrica_sesiones", MagicMock(return_value=contexto)),
        patch.object(kafka_outbox.kafka_outbox_repository, "obtener_pendientes", AsyncMock(return_value=filas)),
        patch.object(kafka_outbox.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await kafka_outbox.relay_outbox_kafka()

    productor.start.assert_awaited_once()
    sesion.commit.assert_awaited_once()
    productor.stop.assert_awaited_once()
    assert filas[0].procesado is True


async def test_relay_sin_pendientes_no_hace_commit():
    sesion = AsyncMock()
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sesion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    productor = MagicMock(start=AsyncMock(), stop=AsyncMock())
    with (
        patch.object(kafka_outbox, "crear_productor_kafka", return_value=productor),
        patch.object(kafka_outbox, "fabrica_sesiones", MagicMock(return_value=contexto)),
        patch.object(kafka_outbox.kafka_outbox_repository, "obtener_pendientes", AsyncMock(return_value=[])),
        patch.object(kafka_outbox.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await kafka_outbox.relay_outbox_kafka()
    sesion.commit.assert_not_awaited()


def test_a_utc_acepta_naive_y_con_zona():
    naive = datetime.datetime(2026, 11, 21, 12, 0)
    chile = datetime.timezone(datetime.timedelta(hours=-3))
    assert kafka_outbox._a_utc(naive) == naive.replace(tzinfo=datetime.UTC)
    assert kafka_outbox._a_utc(datetime.datetime(2026, 11, 21, 9, 0, tzinfo=chile)) == naive.replace(
        tzinfo=datetime.UTC
    )
    assert kafka_outbox._a_utc(None) is None


def test_espacio_sin_id_no_cumple_el_contrato():
    # Defensa: registrar antes del flush (id None) es un bug; el contrato lo rechaza.
    with pytest.raises(ValueError):
        kafka_outbox.registrar_evento_espacio(MagicMock(), "ESPACIO_CREADO", Espacio(condominio_id=1))
