from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import Espacio, Reserva


async def obtener_todos(sesion: AsyncSession, condominio_id: int | None = None) -> list[Espacio]:
    stmt = select(Espacio)
    if condominio_id is not None:
        stmt = stmt.where(Espacio.condominio_id == condominio_id)
    resultado = await sesion.execute(stmt)
    return list(resultado.scalars().all())

async def obtener_por_id(
    sesion: AsyncSession,
    espacio_id: int,
    condominio_id: int | None = None,
    con_bloqueo: bool = False,
) -> Espacio | None:
    # condominio_id es opcional: el flujo de reservas (reserva_service) busca el
    # espacio solo por id, sin contexto de condominio todavia (fuera de alcance).
    stmt = select(Espacio).where(Espacio.id == espacio_id)
    if condominio_id is not None:
        stmt = stmt.where(Espacio.condominio_id == condominio_id)
    if con_bloqueo:
        stmt = stmt.with_for_update()
    resultado = await sesion.execute(stmt)
    return resultado.scalar_one_or_none()

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
