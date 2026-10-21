"""Worker 1: consume notificaciones_queue y envía correos sin adjunto.

Puerto de prototipo-rabbit-residente/worker_notificaciones.py — misma
lógica de armado de correo, adaptada a la topología y settings propios de
ms-espacios-comunes.
"""

import asyncio
import logging

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.settings import settings
from app.events.consumidor_notificaciones_base import crear_procesador
from app.events.correo import enviar_correo
from app.events.eventos import EventoInvalido, EventoReserva
from app.events.topologia_notificaciones import (
    COLA_NOTIFICACIONES,
    RK_RESERVA_CREADA,
    RK_RESERVA_EXPIRADA,
    declarar_topologia_notificaciones,
)

logger = logging.getLogger(__name__)
NOMBRE_CONSUMIDOR = "notificaciones_residente"


def armar_correo(evento: EventoReserva) -> tuple[str, str]:
    if evento.tipo == RK_RESERVA_CREADA:
        asunto = f"Tu reserva N° {evento.reserva_id} está en proceso"
        cuerpo = (
            f"Hola {evento.nombre_residente}:\n\n"
            f"Recibimos tu solicitud de reserva N° {evento.reserva_id} para {evento.espacio}.\n"
            f"Fecha: {evento.fecha_inicio} a {evento.fecha_fin}.\n\n"
            "Tu solicitud está EN PROCESO. Tienes 15 minutos para pagar; cuando se "
            "confirme el pago te enviaremos otro correo con el comprobante en PDF.\n\n"
            "Equipo Convivo"
        )
    elif evento.tipo == RK_RESERVA_EXPIRADA:
        asunto = f"Tu reserva N° {evento.reserva_id} expiró"
        cuerpo = (
            f"Hola {evento.nombre_residente}:\n\n"
            f"Tu reserva N° {evento.reserva_id} para {evento.espacio} "
            f"({evento.fecha_inicio} a {evento.fecha_fin}) EXPIRÓ porque no se "
            "registró el pago dentro de los 15 minutos.\n\n"
            "El horario quedó liberado y el cobro asociado fue anulado. "
            "Si aún lo necesitas, puedes hacer una nueva reserva.\n\n"
            "Equipo Convivo"
        )
    else:
        raise EventoInvalido(f"Tipo de evento no soportado por este worker: '{evento.tipo}'")
    return asunto, cuerpo


async def manejar_evento(evento: EventoReserva) -> None:
    asunto, cuerpo = armar_correo(evento)
    await enviar_correo(evento.email, asunto, cuerpo)


async def iniciar_worker_notificaciones(canal) -> None:
    await canal.set_qos(prefetch_count=10)
    colas = await declarar_topologia_notificaciones(canal)
    procesar = crear_procesador(NOMBRE_CONSUMIDOR, manejar_evento)
    await colas[COLA_NOTIFICACIONES].consume(procesar)
    logger.info("Worker de notificaciones escuchando '%s'", COLA_NOTIFICACIONES)


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_notificaciones():
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    await iniciar_worker_notificaciones(canal)
    try:
        await asyncio.Future()
    finally:
        await conexion.close()
