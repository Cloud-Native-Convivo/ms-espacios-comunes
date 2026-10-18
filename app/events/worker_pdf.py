"""Worker 2: consume reserva_pdf_queue, genera el PDF y envía el correo
"lista". Puerto de prototipo-rabbit-residente/worker_pdf.py.
"""

import asyncio
import logging
import pathlib

import aio_pika
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.settings import settings
from app.events.consumidor_notificaciones_base import crear_procesador
from app.events.correo import enviar_correo
from app.events.eventos import EventoReserva
from app.events.pdf_reserva import generar_pdf_reserva
from app.events.topologia_notificaciones import COLA_PDF, declarar_topologia_notificaciones

logger = logging.getLogger(__name__)
NOMBRE_CONSUMIDOR = "pdf_reserva_confirmada"
CARPETA_PDFS = "pdfs"


async def manejar_confirmacion(evento: EventoReserva) -> None:
    pdf = await asyncio.to_thread(generar_pdf_reserva, evento)
    nombre_archivo = f"reserva_{evento.reserva_id}.pdf"

    carpeta = pathlib.Path(CARPETA_PDFS)
    carpeta.mkdir(exist_ok=True)
    (carpeta / nombre_archivo).write_bytes(pdf)

    cuerpo = (
        f"Hola {evento.nombre_residente}:\n\n"
        f"¡Tu reserva N° {evento.reserva_id} para {evento.espacio} está LISTA!\n"
        f"Fecha: {evento.fecha_inicio} a {evento.fecha_fin}.\n\n"
        "Adjuntamos el comprobante en PDF.\n\n"
        "Equipo Convivo"
    )
    await enviar_correo(
        evento.email,
        f"Tu reserva N° {evento.reserva_id} está confirmada",
        cuerpo,
        adjunto=(nombre_archivo, pdf),
    )


async def iniciar_worker_pdf(canal) -> None:
    await canal.set_qos(prefetch_count=1)
    colas = await declarar_topologia_notificaciones(canal)
    procesar = crear_procesador(NOMBRE_CONSUMIDOR, manejar_confirmacion)
    await colas[COLA_PDF].consume(procesar)
    logger.info("Worker de PDF escuchando '%s'", COLA_PDF)


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_pdf():
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    await iniciar_worker_pdf(canal)
    try:
        await asyncio.Future()
    finally:
        await conexion.close()
