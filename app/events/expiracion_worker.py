import asyncio
import datetime
import logging
import math
import uuid

from app.config.database import fabrica_sesiones
from app.events import kafka_outbox
from app.model.modelos import Espacio, EventoOutbox
from app.repository import kafka_outbox_repository, reserva_repository
from app.service.reserva_service import payload_reserva
from app.util.tiempo import ahora_utc

logger = logging.getLogger(__name__)

MINUTOS_AVISO_EXPIRACION = 5


async def alertar_por_expirar(sesion, ahora: datetime.datetime) -> int:
    """Alerta RESERVA_POR_EXPIRAR una sola vez por reserva pendiente que expira pronto.

    El worker pasa cada minuto sobre la misma reserva: el event_id es
    determinista (uuid5 del id) y se omite si ya está en el outbox.
    """
    limite = ahora + datetime.timedelta(minutes=MINUTOS_AVISO_EXPIRACION)
    emitidas = 0
    for reserva in await reserva_repository.obtener_por_expirar(sesion, ahora, limite):
        event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"convivo:reserva-{reserva.id}-por-expirar")
        if await kafka_outbox_repository.existe_evento(sesion, str(event_id)):
            continue
        espacio = await sesion.get(Espacio, reserva.espacio_id)
        minutos = max(1, math.ceil((reserva.expira_en - ahora).total_seconds() / 60))
        kafka_outbox.registrar_alerta(
            sesion,
            "RESERVA_POR_EXPIRAR",
            "info",
            reserva,
            espacio.condominio_id,
            f"Tu reserva #{reserva.id} en {espacio.nombre} expira en {minutos} min "
            "si no se confirma el pago.",
            event_id=event_id,
        )
        emitidas += 1
    return emitidas


async def worker_expiracion(intervalo_segundos: int = 60) -> None:
    """Revisa periódicamente reservas en 'pendiente_pago' expiradas y las marca como 'expirada'."""
    logger.info("Iniciando worker de expiración de reservas (intervalo: %ss)...", intervalo_segundos)
    while True:
        try:
            ahora = ahora_utc()
            async with fabrica_sesiones() as sesion:
                expiradas = await reserva_repository.obtener_expiradas(sesion, ahora)
                if expiradas:
                    for reserva in expiradas:
                        await reserva_repository.marcar_expirada(sesion, reserva)
                        espacio = await sesion.get(Espacio, reserva.espacio_id)
                        evt_id = f"reserva-{reserva.id}-expirada"
                        sesion.add(EventoOutbox(
                            tipo_evento="reserva_expirada",
                            carga_util=payload_reserva(reserva, espacio, "reserva_expirada", evt_id),
                        ))
                        await kafka_outbox.registrar_evento_reserva(
                            sesion, "RESERVA_EXPIRADA", reserva,
                            estado_anterior="pendiente_pago", espacio=espacio,
                        )
                alertas = await alertar_por_expirar(sesion, ahora)
                if expiradas or alertas:
                    await sesion.commit()
                if expiradas:
                    logger.info("Worker expiración: %d reservas marcadas como expiradas", len(expiradas))
        except asyncio.CancelledError:
            logger.info("Worker de expiración cancelado")
            raise
        except Exception as error:
            logger.exception("Error en worker de expiración: %s", error)

        await asyncio.sleep(intervalo_segundos)
