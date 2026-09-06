import datetime
import json

from app.exception.reserva_exception import (
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.model.modelos import EventoOutbox, Reserva
from app.repository.reserva_repository import ReservaRepository


class ReservaService:
    def __init__(self, repo: ReservaRepository):
        self._repo = repo

    async def crear(
        self,
        espacio_id: int,
        usuario_sub: str,
        fecha_inicio: datetime.datetime,
        fecha_fin: datetime.datetime,
    ) -> Reserva:
        if fecha_fin <= fecha_inicio:
            raise ReservaFechaInvalidaException()

        if await self._repo.existe_solapamiento(espacio_id, fecha_inicio, fecha_fin):
            raise ReservaSolapamientoException(
                espacio_id,
                fecha_inicio.isoformat(),
                fecha_fin.isoformat(),
            )

        reserva = Reserva(
            espacio_id=espacio_id,
            usuario_sub=usuario_sub,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

        evento = EventoOutbox(
            tipo_evento="reserva_espacio_creada",
            carga_util=json.dumps(
                {
                    "espacio_id": espacio_id,
                    "usuario_sub": usuario_sub,
                    "fecha_inicio": fecha_inicio.isoformat(),
                    "fecha_fin": fecha_fin.isoformat(),
                }
            ),
        )

        return await self._repo.crear(reserva, evento)

    async def listar_por_usuario(self, usuario_sub: str) -> list[Reserva]:
        return await self._repo.obtener_por_usuario(usuario_sub)

    async def listar_todas(self) -> list[Reserva]:
        return await self._repo.obtener_todas()

    async def compensar_por_gasto_fallido(
        self, usuario_sub: str, espacio_id: int, fecha_inicio: datetime.datetime
    ) -> Reserva | None:
        return await self._repo.cancelar_por_evento(usuario_sub, espacio_id, fecha_inicio)
