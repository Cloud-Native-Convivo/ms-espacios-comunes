"""Lógica común a los dos workers de notificación: ACK manual, idempotencia,
reintento y DLQ. Puerto de prototipo-rabbit-residente/consumidor_base.py,
con la idempotencia en la base de datos de espacios (Tarea E5) en vez de
SQLite.

Orden para cada mensaje:
    1. Leer el JSON            → si está roto: reject sin requeue → DLQ
    2. Reservar el event_id    → si ya estaba COMPLETADO/EN_CURSO: ACK y descartar
    3. Hacer el trabajo        (PDF, SMTP)
    4. Marcar COMPLETADO
    5. ACK

Si el paso 3 falla por algo técnico: se libera la reserva; primera vez NACK
con requeue, segunda vez (redelivered=True) reject sin requeue → DLQ.
"""

import logging
from collections.abc import Awaitable, Callable

import aio_pika

from app.config.database import fabrica_sesiones
from app.events.eventos import EventoInvalido, EventoReserva, leer_evento
from app.repository import idempotencia_repository
from app.repository.idempotencia_repository import NUEVO

logger = logging.getLogger(__name__)

Manejador = Callable[[EventoReserva], Awaitable[None]]


def crear_procesador(nombre_consumidor: str, manejar: Manejador):
    async def procesar(mensaje: aio_pika.abc.AbstractIncomingMessage) -> None:
        try:
            evento = leer_evento(mensaje.body)
        except EventoInvalido as error:
            logger.error("[%s] Mensaje inválido, va a la DLQ: %s", nombre_consumidor, error)
            await mensaje.reject(requeue=False)
            return
        if not evento.tipo:
            evento.tipo = mensaje.routing_key or ""

        async with fabrica_sesiones() as sesion:
            resultado = await idempotencia_repository.reclamar(
                sesion, evento.event_id, nombre_consumidor, retomar_en_curso=mensaje.redelivered
            )
            if resultado != NUEVO:
                logger.info(
                    "[%s] event_id=%s duplicado (%s): se descarta", nombre_consumidor, evento.event_id, resultado
                )
                await mensaje.ack()
                return

            try:
                await manejar(evento)
            except Exception as error:  # noqa: BLE001 - cualquier fallo técnico
                await idempotencia_repository.liberar(sesion, evento.event_id, nombre_consumidor)
                if mensaje.redelivered:
                    logger.error(
                        "[%s] event_id=%s falló de nuevo, va a la DLQ: %s", nombre_consumidor, evento.event_id, error
                    )
                    await mensaje.reject(requeue=False)
                else:
                    logger.warning(
                        "[%s] event_id=%s falló, se reintenta una vez: %s", nombre_consumidor, evento.event_id, error
                    )
                    await mensaje.nack(requeue=True)
                return

            await idempotencia_repository.completar(sesion, evento.event_id, nombre_consumidor)
            await mensaje.ack()
            logger.info("[%s] event_id=%s procesado OK (reserva %s)", nombre_consumidor, evento.event_id, evento.reserva_id)

    return procesar
