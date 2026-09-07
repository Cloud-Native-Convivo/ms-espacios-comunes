from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import Espacio, Reserva


class EspacioRepository:
    def __init__(self, sesion: AsyncSession):
        self._sesion = sesion

    async def obtener_todos(self) -> list[Espacio]:
        resultado = await self._sesion.execute(select(Espacio))
        return list(resultado.scalars().all())

    async def obtener_por_id(self, espacio_id: int) -> Espacio | None:
        return await self._sesion.get(Espacio, espacio_id)

    async def crear(self, espacio: Espacio) -> Espacio:
        self._sesion.add(espacio)
        await self._sesion.flush()
        return espacio

    async def actualizar(self, espacio: Espacio) -> Espacio:
        await self._sesion.flush()
        return espacio

    async def contar_reservas_asociadas(self, espacio_id: int) -> int:
        resultado = await self._sesion.execute(
            select(func.count(Reserva.id)).where(Reserva.espacio_id == espacio_id)
        )
        return resultado.scalar_one()

    async def eliminar_fisico(self, espacio: Espacio) -> None:
        await self._sesion.delete(espacio)
        await self._sesion.flush()

