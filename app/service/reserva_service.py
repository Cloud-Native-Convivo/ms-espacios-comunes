import datetime
import json

from app.exception.espacio_exception import EspacioNoEncontradoException
from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.model.modelos import EventoOutbox, Reserva
from app.repository.espacio_repository import EspacioRepository
from app.repository.reserva_repository import ReservaRepository


class ReservaService:
    def __init__(
        self,
        repo: ReservaRepository,
        espacio_repo: EspacioRepository | None = None,
    ):
        self._repo = repo
        self._espacio_repo = espacio_repo

    async def crear(
        self,
        espacio_id: int,
        usuario_sub: str,
        fecha_inicio: datetime.datetime,
        fecha_fin: datetime.datetime,
    ) -> Reserva:
        if not usuario_sub or not usuario_sub.strip():
            raise ReservaFechaInvalidaException(
                "El identificador de usuario no puede estar vacío"
            )

        ahora = datetime.datetime.now()
        fecha_inicio_cmp = (
            fecha_inicio.replace(tzinfo=None)
            if fecha_inicio.tzinfo
            else fecha_inicio
        )
        fecha_fin_cmp = (
            fecha_fin.replace(tzinfo=None) if fecha_fin.tzinfo else fecha_fin
        )

        if fecha_inicio_cmp < ahora:
            raise ReservaFechaInvalidaException(
                "La fecha de inicio no puede ser en el pasado"
            )

        if fecha_fin_cmp <= fecha_inicio_cmp:
            raise ReservaFechaInvalidaException(
                "La fecha de fin debe ser posterior a la de inicio"
            )

        if (fecha_fin_cmp - fecha_inicio_cmp) > datetime.timedelta(hours=24):
            raise ReservaFechaInvalidaException(
                "La duración máxima permitida de una reserva es de 24 horas"
            )

        tarifa_hora = 0.0
        if self._espacio_repo:
            espacio = await self._espacio_repo.obtener_por_id(
                espacio_id, con_bloqueo=True
            )
            if not espacio:
                raise EspacioNoEncontradoException(espacio_id)
            if (espacio.estado or "").strip().lower() != "activo":
                raise ReservaEspacioNoDisponibleException(espacio_id, espacio.estado)
            tarifa_hora = float(espacio.tarifa_hora) if espacio.tarifa_hora else 0.0

        if await self._repo.existe_solapamiento(espacio_id, fecha_inicio, fecha_fin):
            raise ReservaSolapamientoException(
                espacio_id,
                fecha_inicio.isoformat(),
                fecha_fin.isoformat(),
            )

        duracion_segundos = (fecha_fin_cmp - fecha_inicio_cmp).total_seconds()
        duracion_horas = duracion_segundos / 3600.0
        monto_total = round(duracion_horas * tarifa_hora, 2)
        expira_en = ahora + datetime.timedelta(minutes=15)

        reserva = Reserva(
            espacio_id=espacio_id,
            usuario_sub=usuario_sub,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado="pendiente_pago",
            monto_total=monto_total,
            expira_en=expira_en,
        )

        evento = EventoOutbox(
            tipo_evento="reserva_espacio_creada",
            carga_util=json.dumps(
                {
                    "reserva_id": None,
                    "espacio_id": espacio_id,
                    "usuario_sub": usuario_sub,
                    "fecha_inicio": fecha_inicio.isoformat(),
                    "fecha_fin": fecha_fin.isoformat(),
                    "monto_total": monto_total,
                    "expira_en": expira_en.isoformat(),
                }
            ),
        )

        reserva_creada = await self._repo.crear(reserva, evento)
        evento.carga_util = json.dumps(
            {
                "reserva_id": reserva_creada.id,
                "espacio_id": espacio_id,
                "usuario_sub": usuario_sub,
                "fecha_inicio": fecha_inicio.isoformat(),
                "fecha_fin": fecha_fin.isoformat(),
                "monto_total": monto_total,
                "expira_en": expira_en.isoformat(),
            }
        )
        return reserva_creada

    async def listar_por_usuario(self, usuario_sub: str) -> list[Reserva]:
        if not usuario_sub or not usuario_sub.strip():
            raise ReservaFechaInvalidaException(
                "El identificador de usuario no puede estar vacío"
            )
        return await self._repo.obtener_por_usuario(usuario_sub)

    async def listar_todas(self) -> list[Reserva]:
        return await self._repo.obtener_todas()

    async def confirmar_pago(self, reserva_id: int) -> Reserva | None:
        return await self._repo.confirmar_pago(reserva_id)

    async def cancelar_por_id(self, reserva_id: int) -> Reserva | None:
        return await self._repo.cancelar_por_id(reserva_id)

    async def compensar_por_gasto_fallido(
        self,
        usuario_sub: str | None = None,
        espacio_id: int | None = None,
        fecha_inicio: datetime.datetime | None = None,
        reserva_id: int | None = None,
    ) -> Reserva | None:
        if reserva_id:
            return await self._repo.cancelar_por_id(reserva_id)
        if usuario_sub and espacio_id and fecha_inicio:
            return await self._repo.cancelar_por_evento(
                usuario_sub, espacio_id, fecha_inicio
            )
        return None

