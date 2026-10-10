import asyncio
import logging

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.dto.esquemas import EventoPagoConfirmadoRequest, GastoFallidoRequest
from app.service import reserva_service

logger = logging.getLogger(__name__)

COLA_COMPENSACION = "gasto_fallido"
COLA_PAGO = "reserva_pagada"
EXCHANGE_DLX = "espacios_dlx"
COLA_COMPENSACION_DLQ = "gasto_fallido_dlq"
COLA_PAGO_DLQ = "reserva_pagada_dlq"


async def procesar_compensacion(mensaje: aio_pika.IncomingMessage):
    try:
        datos = GastoFallidoRequest.model_validate_json(mensaje.body)
    except Exception as error_json:
        logger.exception(
            "Mensaje corrupto en cola compensación (desviado a DLQ): %s",
            error_json,
        )
        await mensaje.reject(requeue=False)
        return

    try:
        async with mensaje.process(requeue=True):
            async with fabrica_sesiones() as sesion:
                reserva = await reserva_service.compensar_por_gasto_fallido(
                    sesion,
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
    except Exception as error_proc:
        logger.exception(
            "Error operacional procesando mensaje de compensación (reencolado): %s",
            error_proc,
        )


async def procesar_pago(mensaje: aio_pika.IncomingMessage):
    try:
        datos = EventoPagoConfirmadoRequest.model_validate_json(mensaje.body)
    except Exception as error_json:
        logger.exception(
            "Mensaje corrupto en cola confirmación de pago (desviado a DLQ): %s",
            error_json,
        )
        await mensaje.reject(requeue=False)
        return

    try:
        async with mensaje.process(requeue=True):
            async with fabrica_sesiones() as sesion:
                reserva = await reserva_service.confirmar_pago(sesion, datos.reserva_id)
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
    except Exception as error_proc:
        logger.exception(
            "Error operacional procesando confirmación de pago (reencolado): %s",
            error_proc,
        )


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

    # Dead Letter Exchange y Dead Letter Queues para descarte seguro
    exchange_dlx = await canal.declare_exchange(
        EXCHANGE_DLX, aio_pika.ExchangeType.DIRECT, durable=True
    )
    cola_comp_dlq = await canal.declare_queue(COLA_COMPENSACION_DLQ, durable=True)
    cola_pago_dlq = await canal.declare_queue(COLA_PAGO_DLQ, durable=True)
    await cola_comp_dlq.bind(exchange_dlx, routing_key=COLA_COMPENSACION_DLQ)
    await cola_pago_dlq.bind(exchange_dlx, routing_key=COLA_PAGO_DLQ)

    # Mismo exchange que publica ms-gastos-comunes (RabbitMqConfig): sin
    # bind explicito, RabbitMQ nunca entrega los mensajes ruteados a este
    # exchange, aunque la cola exista y este declarada.
    exchange = await canal.declare_exchange(
        "espacios_events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    cola_compensacion = await canal.declare_queue(
        COLA_COMPENSACION,
        durable=True,
        arguments={
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": COLA_COMPENSACION_DLQ,
        },
    )
    cola_pago = await canal.declare_queue(
        COLA_PAGO,
        durable=True,
        arguments={
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": COLA_PAGO_DLQ,
        },
    )
    await cola_compensacion.bind(exchange, routing_key=COLA_COMPENSACION)
    await cola_pago.bind(exchange, routing_key=COLA_PAGO)

    await cola_compensacion.consume(procesar_compensacion)
    await cola_pago.consume(procesar_pago)
    logger.info(
        "Consumidores RabbitMQ activos en colas '%s' y '%s' (con DLX '%s')",
        COLA_COMPENSACION,
        COLA_PAGO,
        EXCHANGE_DLX,
    )

    try:
        await asyncio.Future()
    finally:
        await conexion.close()
