"""Idempotencia por (event_id, consumidor): ver prototipo idempotencia.py.

El event_id se reserva ANTES de hacer el trabajo (INSERT sobre la llave
primaria) para que, si dos copias del mismo evento llegan casi juntas, la
base de datos garantice que solo una gana la reserva.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.evento_procesado import EventoProcesado

NUEVO = "NUEVO"
EN_CURSO = "EN_CURSO"
COMPLETADO = "COMPLETADO"


async def reclamar(
    sesion: AsyncSession, event_id: str, consumidor: str, retomar_en_curso: bool = False
) -> str:
    """Reserva event_id+consumidor con un INSERT. Usa SAVEPOINT (begin_nested)
    en vez de sesion.rollback(): esta función no es dueña de la sesión que
    recibe — un rollback de toda la sesión deshacía cualquier otro trabajo
    pendiente que el llamador tuviera ahí (ver consumidor_notificaciones_base.py,
    que reusa la misma sesión para completar/liberar después de reclamar).
    """
    try:
        async with sesion.begin_nested():
            sesion.add(EventoProcesado(event_id=event_id, consumidor=consumidor, estado=EN_CURSO))
            await sesion.flush()
        await sesion.commit()
        return NUEVO
    except IntegrityError:
        registro = await sesion.get(EventoProcesado, (event_id, consumidor))
        if registro.estado == EN_CURSO and retomar_en_curso:
            return NUEVO
        return registro.estado


async def completar(sesion: AsyncSession, event_id: str, consumidor: str) -> None:
    registro = await sesion.get(EventoProcesado, (event_id, consumidor))
    registro.estado = COMPLETADO
    await sesion.commit()


async def liberar(sesion: AsyncSession, event_id: str, consumidor: str) -> None:
    registro = await sesion.get(EventoProcesado, (event_id, consumidor))
    if registro and registro.estado == EN_CURSO:
        await sesion.delete(registro)
        await sesion.commit()
