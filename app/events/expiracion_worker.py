import asyncio
import datetime
import logging

from app.config.database import fabrica_sesiones
from app.repository.reserva_repository import ReservaRepository

logger = logging.getLogger(__name__)


async def worker_expiracion(intervalo_segundos: int = 60) -> None:
    """Revisa periódicamente reservas en 'pendiente_pago' expiradas y las marca como 'expirada'."""
    logger.info("Iniciando worker de expiración de reservas (intervalo: %ss)...", intervalo_segundos)
    while True:
        try:
            ahora = datetime.datetime.now()
            async with fabrica_sesiones() as sesion:
                repo = ReservaRepository(sesion)
                expiradas = await repo.obtener_expiradas(ahora)
                if expiradas:
                    for reserva in expiradas:
                        await repo.marcar_expirada(reserva)
                    await sesion.commit()
                    logger.info("Worker expiración: %d reservas marcadas como expiradas", len(expiradas))
        except asyncio.CancelledError:
            logger.info("Worker de expiración cancelado")
            break
        except Exception as error:
            logger.exception("Error en worker de expiración: %s", error)

        await asyncio.sleep(intervalo_segundos)
