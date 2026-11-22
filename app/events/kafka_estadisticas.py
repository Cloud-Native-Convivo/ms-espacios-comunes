"""Consumidor de espacios.historial.v1 que proyecta disponibilidad y estadísticas.

Idempotencia: el event_id se inserta en eventos_procesados en la MISMA
transacción que actualiza los contadores; un duplicado choca con la llave
primaria y se descarta sin tocar nada. El offset se confirma recién después
del commit en la base: si el proceso cae entre ambos, el evento se reprocesa
y la idempotencia lo descarta.
"""

import datetime
import logging
from decimal import Decimal

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.dto.kafka_eventos import TOPICO_HISTORIAL, EventoEspacioV1
from app.model.evento_procesado import EventoProcesado
from app.model.modelos import EstadisticaEspacio, EstadisticaEspacioDia
from app.repository.idempotencia_repository import COMPLETADO

logger = logging.getLogger(__name__)

GRUPO_ESTADISTICAS = "ms-espacios-comunes.estadisticas"
CONSUMIDOR = "kafka-estadisticas"

# Tipo de evento de espacio -> estado resultante (None = no cambia el estado).
_ESTADO_POR_TIPO = {
    "ESPACIO_HABILITADO": "activo",
    "ESPACIO_EN_MANTENCION": "mantenimiento",
    "ESPACIO_ACTUALIZADO": None,
}
_CONTADOR_POR_TIPO = {
    "RESERVA_CREADA": "reservas_creadas",
    "RESERVA_CONFIRMADA": "reservas_confirmadas",
    "RESERVA_CANCELADA": "reservas_canceladas",
    "RESERVA_EXPIRADA": "reservas_expiradas",
}


def _naive_utc(valor: datetime.datetime) -> datetime.datetime:
    return valor.astimezone(datetime.UTC).replace(tzinfo=None)


async def _espacio(sesion: AsyncSession, evento: EventoEspacioV1) -> EstadisticaEspacio:
    fila = await sesion.get(EstadisticaEspacio, evento.espacio_id)
    if fila is None:
        # Espacio creado antes del PR 2 (sin ESPACIO_CREADO): solo se reserva si está activo.
        fila = EstadisticaEspacio(
            espacio_id=evento.espacio_id, condominio_id=evento.condominio_id, estado="activo"
        )
        sesion.add(fila)
    fila.actualizado_en = _naive_utc(evento.ocurrido_en)
    return fila


async def _dia(sesion: AsyncSession, evento: EventoEspacioV1) -> EstadisticaEspacioDia:
    fecha = evento.ocurrido_en.astimezone(datetime.UTC).date()
    fila = await sesion.get(EstadisticaEspacioDia, (evento.espacio_id, fecha))
    if fila is None:
        fila = EstadisticaEspacioDia(
            espacio_id=evento.espacio_id, fecha=fecha, condominio_id=evento.condominio_id,
            reservas_creadas=0, reservas_confirmadas=0, reservas_canceladas=0,
            reservas_expiradas=0, horas_confirmadas=Decimal("0"),
        )
        sesion.add(fila)
    return fila


async def proyectar(sesion: AsyncSession, evento: EventoEspacioV1) -> None:
    """Aplica un evento del historial al modelo de lectura."""
    espacio = await _espacio(sesion, evento)
    if evento.tipo in ("ESPACIO_CREADO", "ESPACIO_DESHABILITADO"):
        # DESHABILITADO trae "inactivo" o "eliminado" (eliminación física).
        espacio.estado = evento.datos.estado_nuevo or "activo"
        return
    if evento.tipo in _ESTADO_POR_TIPO:
        espacio.estado = _ESTADO_POR_TIPO[evento.tipo] or espacio.estado
        return

    dia = await _dia(sesion, evento)
    campo = _CONTADOR_POR_TIPO[evento.tipo]
    setattr(dia, campo, getattr(dia, campo) + 1)
    if evento.tipo == "RESERVA_CONFIRMADA" and evento.datos.fecha_inicio and evento.datos.fecha_fin:
        segundos = (evento.datos.fecha_fin - evento.datos.fecha_inicio).total_seconds()
        horas = Decimal(str(round(segundos / 3600, 2)))
        dia.horas_confirmadas = Decimal(str(dia.horas_confirmadas)) + horas


async def procesar_valor(sesion: AsyncSession, valor: bytes) -> bool:
    """Proyecta un mensaje; False si es inválido o duplicado (igual se confirma el offset)."""
    try:
        evento = EventoEspacioV1.model_validate_json(valor)
    except ValidationError as error:
        # Sin DLQ nativa en Kafka: se registra y se salta para no bloquear la partición.
        logger.error("Mensaje fuera de contrato en %s, se omite: %s", TOPICO_HISTORIAL, error)
        return False

    sesion.add(EventoProcesado(event_id=str(evento.event_id), consumidor=CONSUMIDOR, estado=COMPLETADO))
    try:
        await sesion.flush()
    except IntegrityError:
        await sesion.rollback()
        logger.info("Evento %s ya proyectado, se omite", evento.event_id)
        return False
    await proyectar(sesion, evento)
    await sesion.commit()
    return True


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_estadisticas() -> None:
    """Consume el historial y confirma el offset tras cada commit en la base."""
    consumidor = AIOKafkaConsumer(
        TOPICO_HISTORIAL,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-estadisticas",
        group_id=GRUPO_ESTADISTICAS,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumidor.start()
    try:
        async for mensaje in consumidor:
            async with fabrica_sesiones() as sesion:
                await procesar_valor(sesion, mensaje.value)
            await consumidor.commit()
    finally:
        await consumidor.stop()
