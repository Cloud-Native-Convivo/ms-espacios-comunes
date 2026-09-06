import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import EventoOutbox, Reserva


class ReservaRepository:
    def __init__(self, sesion: AsyncSession):
        self._sesion = sesion

    async def existe_solapamiento(
        self,
        espacio_id: int,
        fecha_inicio: datetime.datetime,
        fecha_fin: datetime.datetime,
    ) -> bool:
        consulta = select(Reserva).where(
            and_(
                Reserva.espacio_id == espacio_id,
                Reserva.estado == "activa",
                Reserva.fecha_inicio < fecha_fin,
                Reserva.fecha_fin > fecha_inicio,
            )
        )
        resultado = await self._sesion.execute(consulta)
        return resultado.scalar_one_or_none() is not None

    async def crear(
        self,
        reserva: Reserva,
        evento_outbox: EventoOutbox,
    ) -> Reserva:
        self._sesion.add(reserva)
        self._sesion.add(evento_outbox)
        await self._sesion.flush()
        return reserva

    async def obtener_por_usuario(self, usuario_sub: str) -> list[Reserva]:
        consulta = (
            select(Reserva)
            .where(Reserva.usuario_sub == usuario_sub)
            .order_by(Reserva.fecha_inicio.desc())
        )
        resultado = await self._sesion.execute(consulta)
        return list(resultado.scalars().all())

    async def obtener_todas(self) -> list[Reserva]:
        consulta = select(Reserva).order_by(Reserva.fecha_inicio.desc())
        resultado = await self._sesion.execute(consulta)
        return list(resultado.scalars().all())

    async def obtener_pendientes_outbox(self) -> list[EventoOutbox]:
        consulta = (
            select(EventoOutbox)
            .where(EventoOutbox.procesado == False)  # noqa: E712
            .order_by(EventoOutbox.creado_en)
        )
        resultado = await self._sesion.execute(consulta)
        return list(resultado.scalars().all())

    async def marcar_como_procesado(self, evento: EventoOutbox) -> None:
        evento.procesado = True
        await self._sesion.flush()

    async def cancelar_por_evento(
        self, usuario_sub: str, espacio_id: int, fecha_inicio: datetime.datetime
    ) -> Reserva | None:
        consulta = select(Reserva).where(
            and_(
                Reserva.usuario_sub == usuario_sub,
                Reserva.espacio_id == espacio_id,
                Reserva.fecha_inicio == fecha_inicio,
                Reserva.estado == "activa",
            )
        )
        resultado = await self._sesion.execute(consulta)
        reserva = resultado.scalar_one_or_none()
        if reserva:
            reserva.estado = "cancelada"
            await self._sesion.flush()
        return reserva
