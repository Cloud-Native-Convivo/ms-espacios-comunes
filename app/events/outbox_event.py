import asyncio
import logging

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.repository.reserva_repository import ReservaRepository

logger = logging.getLogger(__name__)


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def relay_outbox():
    """Poll la tabla outbox y publica eventos en RabbitMQ. Reconecta en loop."""
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    exchange = await canal.declare_exchange("espacios_events", aio_pika.ExchangeType.DIRECT)

    while True:
        async with fabrica_sesiones() as sesion:
            repo = ReservaRepository(sesion)
            eventos = await repo.obtener_pendientes_outbox()
            for evento in eventos:
                mensaje = aio_pika.Message(
                    body=evento.carga_util.encode(),
                    content_type="application/json",
                )
                await exchange.publish(mensaje, routing_key=evento.tipo_evento)
                await repo.marcar_como_procesado(evento)
            await sesion.commit()
        await asyncio.sleep(5)
