import asyncio
import logging

from app.config.database import fabrica_sesiones
from app.model.modelos import EventoOutbox, Espacio
from app.repository import reserva_repository
from app.service.reserva_service import payload_reserva
from app.util.tiempo import ahora_utc

logger = logging.getLogger(__name__)


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
                    await sesion.commit()
                    logger.info("Worker expiración: %d reservas marcadas como expiradas", len(expiradas))
        except asyncio.CancelledError:
            logger.info("Worker de expiración cancelado")
            raise
        except Exception as error:
            logger.exception("Error en worker de expiración: %s", error)

        await asyncio.sleep(intervalo_segundos)
