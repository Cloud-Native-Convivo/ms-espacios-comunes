import logging

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.dto.request.reserva_request import GastoFallidoRequest
from app.repository.reserva_repository import ReservaRepository
from app.service.reserva_service import ReservaService

logger = logging.getLogger(__name__)

COLA_COMPENSACION = "gasto_fallido"


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_compensacion():
    """Escucha la cola gasto_fallido y cancela la reserva asociada. Reconecta en loop."""
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    await canal.set_qos(prefetch_count=1)
    cola = await canal.declare_queue(COLA_COMPENSACION, durable=True)

    async for mensaje in cola:
        async with mensaje.process():
            datos = GastoFallidoRequest.model_validate_json(mensaje.body)
            async with fabrica_sesiones() as sesion:
                servicio = ReservaService(ReservaRepository(sesion))
                reserva = await servicio.compensar_por_gasto_fallido(
                    usuario_sub=datos.usuario_sub,
                    espacio_id=datos.espacio_id,
                    fecha_inicio=datos.fecha_inicio,
                )
                if reserva:
                    await sesion.commit()
                    logger.info("Reserva %s cancelada por gasto fallido", reserva.id)
                else:
                    logger.warning("No se encontró reserva para compensar: %s", datos)
