"""Outbox de Kafka: registro de eventos en la transacción de negocio y relay.

El evento se agrega a la misma sesión que el cambio de espacio/reserva: si el
commit falla no queda evento, y si pasa el evento queda guardado aunque Kafka
esté caído. El relay publica después, at-least-once (los consumidores
deduplican por event_id).
"""

import asyncio
import datetime
import logging

from aiokafka import AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.dto.kafka_eventos import (
    TOPICO_ALERTAS,
    TOPICO_HISTORIAL,
    AlertaEspacioV1,
    DatosEventoEspacio,
    EventoEspacioV1,
    TipoEventoEspacio,
)
from app.events.kafka_productor import crear_productor_kafka
from app.model.modelos import Espacio, EventoOutboxKafka, Reserva
from app.repository import kafka_outbox_repository

logger = logging.getLogger(__name__)

MODELO_POR_TOPICO = {TOPICO_HISTORIAL: EventoEspacioV1, TOPICO_ALERTAS: AlertaEspacioV1}

# Estado del espacio (columna espacios.estado) -> tipo de evento de su transición.
TIPO_POR_ESTADO_ESPACIO: dict[str, TipoEventoEspacio] = {
    "activo": "ESPACIO_HABILITADO",
    "mantenimiento": "ESPACIO_EN_MANTENCION",
    "inactivo": "ESPACIO_DESHABILITADO",
}


def _a_utc(valor: datetime.datetime | None) -> datetime.datetime | None:
    """Las columnas guardan UTC naive; el contrato exige fecha con zona."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=datetime.UTC)
    return valor.astimezone(datetime.UTC)


def _agregar(sesion: AsyncSession, evento: EventoEspacioV1) -> EventoEspacioV1:
    sesion.add(
        EventoOutboxKafka(
            event_id=str(evento.event_id),
            topico=TOPICO_HISTORIAL,
            clave=evento.clave,
            carga_util=evento.model_dump_json(),
        )
    )
    return evento


def registrar_evento_espacio(
    sesion: AsyncSession,
    tipo: TipoEventoEspacio,
    espacio: Espacio,
    actor_sub: str | None = None,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
) -> EventoEspacioV1:
    """Agrega a la sesión un evento del historial de un espacio."""
    return _agregar(
        sesion,
        EventoEspacioV1(
            tipo=tipo,
            condominio_id=espacio.condominio_id,
            espacio_id=espacio.id,
            actor_sub=actor_sub,
            datos=DatosEventoEspacio(estado_anterior=estado_anterior, estado_nuevo=estado_nuevo),
        ),
    )


async def registrar_evento_reserva(
    sesion: AsyncSession,
    tipo: TipoEventoEspacio,
    reserva: Reserva,
    actor_sub: str | None = None,
    estado_anterior: str | None = None,
    espacio: Espacio | None = None,
) -> EventoEspacioV1:
    """Agrega a la sesión un evento de reserva; la reserva debe tener id (post flush)."""
    if espacio is None:
        espacio = await sesion.get(Espacio, reserva.espacio_id)
    return _agregar(
        sesion,
        EventoEspacioV1(
            tipo=tipo,
            condominio_id=espacio.condominio_id,
            espacio_id=reserva.espacio_id,
            reserva_id=reserva.id,
            actor_sub=actor_sub,
            datos=DatosEventoEspacio(
                estado_anterior=estado_anterior,
                estado_nuevo=reserva.estado,
                fecha_inicio=_a_utc(reserva.fecha_inicio),
                fecha_fin=_a_utc(reserva.fecha_fin),
                monto=float(reserva.monto_total) if reserva.monto_total is not None else None,
            ),
        ),
    )


async def publicar_pendientes(
    productor: AIOKafkaProducer, eventos: list[EventoOutboxKafka]
) -> None:
    """Envía los eventos y los marca procesados solo tras el ack (acks=all).

    Si un envío falla la excepción sube sin commit: los ya confirmados se
    reenvían en el próximo intento (duplicado con el mismo event_id).
    """
    futuros = [
        await productor.send(
            evento.topico,
            value=MODELO_POR_TOPICO[evento.topico].model_validate_json(evento.carga_util),
            key=evento.clave,
        )
        for evento in eventos
    ]
    for evento, futuro in zip(eventos, futuros, strict=True):
        await futuro
        evento.procesado = True


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def relay_outbox_kafka(intervalo_segundos: float = 5) -> None:
    """Publica en Kafka la tabla eventos_outbox_kafka. Reconecta en loop."""
    productor = crear_productor_kafka()
    await productor.start()
    try:
        while True:
            async with fabrica_sesiones() as sesion:
                eventos = await kafka_outbox_repository.obtener_pendientes(sesion)
                if eventos:
                    await publicar_pendientes(productor, eventos)
                    await sesion.commit()
                    logger.info("Relay Kafka: %d eventos publicados", len(eventos))
            await asyncio.sleep(intervalo_segundos)
    finally:
        await productor.stop()
