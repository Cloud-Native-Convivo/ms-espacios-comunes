import asyncio
import logging

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.dto.esquemas import EventoPagoConfirmadoRequest, GastoFallidoRequest
from app.repository.reserva_repository import ReservaRepository
from app.service.reserva_service import ReservaService

logger = logging.getLogger(__name__)

COLA_COMPENSACION = "gasto_fallido"
COLA_PAGO = "reserva_pagada"


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_compensacion():
    """Escucha colas de RabbitMQ para compensaciones y confirmaciones de pago."""
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    await canal.set_qos(prefetch_count=1)

    cola_compensacion = await canal.declare_queue(COLA_COMPENSACION, durable=True)
    cola_pago = await canal.declare_queue(COLA_PAGO, durable=True)

    async def procesar_compensacion(mensaje: aio_pika.IncomingMessage):
        async with mensaje.process():
            try:
                datos = GastoFallidoRequest.model_validate_json(mensaje.body)
                async with fabrica_sesiones() as sesion:
                    servicio = ReservaService(ReservaRepository(sesion))
                    reserva = await servicio.compensar_por_gasto_fallido(
                        usuario_sub=datos.usuario_sub,
                        espacio_id=datos.espacio_id,
                        fecha_inicio=datos.fecha_inicio,
                        reserva_id=datos.reserva_id,
                    )
                    if reserva:
                        await sesion.commit()
                        logger.info(
                            "Reserva %s cancelada por compensación/fallo",
                            reserva.id,
                        )
                    else:
                        logger.warning(
                            "No se encontró reserva para compensar: %s", datos
                        )
            except Exception as e:
                logger.exception("Error procesando mensaje de compensación: %s", e)

    async def procesar_pago(mensaje: aio_pika.IncomingMessage):
        async with mensaje.process():
            try:
                datos = EventoPagoConfirmadoRequest.model_validate_json(mensaje.body)
                async with fabrica_sesiones() as sesion:
                    servicio = ReservaService(ReservaRepository(sesion))
                    reserva = await servicio.confirmar_pago(datos.reserva_id)
                    if reserva:
                        await sesion.commit()
                        logger.info(
                            "Reserva %s confirmada a estado 'activa'", reserva.id
                        )
                    else:
                        logger.warning(
                            "Reserva %s no encontrada o no pendiente de pago",
                            datos.reserva_id,
                        )
            except Exception as e:
                logger.exception("Error procesando confirmación de pago: %s", e)

    await cola_compensacion.consume(procesar_compensacion)
    await cola_pago.consume(procesar_pago)
    logger.info(
        "Consumidores RabbitMQ activos en colas '%s' y '%s'",
        COLA_COMPENSACION,
        COLA_PAGO,
    )

    try:
        await asyncio.Future()
    finally:
        await conexion.close()

