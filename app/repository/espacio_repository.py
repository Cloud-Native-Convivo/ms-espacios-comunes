from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import Espacio, Reserva


async def obtener_todos(sesion: AsyncSession) -> list[Espacio]:
    resultado = await sesion.execute(select(Espacio))
    return list(resultado.scalars().all())

async def obtener_por_id(sesion: AsyncSession, espacio_id: int, con_bloqueo: bool = False) -> Espacio | None:
    if con_bloqueo:
        stmt = select(Espacio).where(Espacio.id == espacio_id).with_for_update()
        resultado = await sesion.execute(stmt)
        return resultado.scalar_one_or_none()
    return await sesion.get(Espacio, espacio_id)

async def crear(sesion: AsyncSession, espacio: Espacio) -> Espacio:
    sesion.add(espacio)
    await sesion.flush()
    return espacio

async def actualizar(sesion: AsyncSession, espacio: Espacio) -> Espacio:
    await sesion.flush()
    await sesion.refresh(espacio)
    return espacio

async def contar_reservas_asociadas(sesion: AsyncSession, espacio_id: int) -> int:
    resultado = await sesion.execute(
        select(func.count(Reserva.id)).where(Reserva.espacio_id == espacio_id)
    )
    return resultado.scalar_one()

async def eliminar_fisico(sesion: AsyncSession, espacio: Espacio) -> None:
    await sesion.delete(espacio)
    await sesion.flush()
