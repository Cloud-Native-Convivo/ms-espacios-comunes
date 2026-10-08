import datetime
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exception.espacio_exception import EspacioNoEncontradoException
from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.model.modelos import EventoOutbox, Reserva
from app.repository import espacio_repository
from app.repository import reserva_repository
from app.dto.esquemas import CrearReservaRequest


async def crear(
    sesion: AsyncSession,
    datos: CrearReservaRequest,
    usuario_sub: str,
) -> Reserva:
    if not usuario_sub or not usuario_sub.strip():
        raise ReservaFechaInvalidaException(
            "El identificador de usuario no puede estar vacío"
        )

    ahora = datetime.datetime.now()
    fecha_inicio_cmp = (
        datos.fecha_inicio.replace(tzinfo=None)
        if datos.fecha_inicio.tzinfo
        else datos.fecha_inicio
    )
    fecha_fin_cmp = (
        datos.fecha_fin.replace(tzinfo=None) if datos.fecha_fin.tzinfo else datos.fecha_fin
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

    espacio = await espacio_repository.obtener_por_id(
        sesion, datos.espacio_id, con_bloqueo=True
    )
    if not espacio:
        raise EspacioNoEncontradoException(datos.espacio_id)
    if (espacio.estado or "").strip().lower() != "activo":
        raise ReservaEspacioNoDisponibleException(datos.espacio_id, espacio.estado)
    tarifa_hora = float(espacio.tarifa_hora) if espacio.tarifa_hora else 0.0

    if await reserva_repository.existe_solapamiento(sesion, datos.espacio_id, datos.fecha_inicio, datos.fecha_fin):
        raise ReservaSolapamientoException(
            datos.espacio_id,
            datos.fecha_inicio.isoformat(),
            datos.fecha_fin.isoformat(),
        )

    duracion_segundos = (fecha_fin_cmp - fecha_inicio_cmp).total_seconds()
    duracion_horas = duracion_segundos / 3600.0
    monto_total = round(duracion_horas * tarifa_hora, 2)
    expira_en = ahora + datetime.timedelta(minutes=15)

    reserva = Reserva(
        espacio_id=datos.espacio_id,
        usuario_sub=usuario_sub,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=datos.fecha_fin,
        estado="pendiente_pago",
        monto_total=monto_total,
        expira_en=expira_en,
    )

    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    evt_id = str(uuid.uuid4())
    unidad_id = f"unidad-{usuario_sub}"
    evento = EventoOutbox(
        tipo_evento="reserva_espacio_creada",
        carga_util=json.dumps(
            {
                "event_id": evt_id,
                "eventId": evt_id,
                "tipo": "reserva_espacio_creada",
                "reserva_id": None,
                "reservaId": None,
                "espacio_id": str(datos.espacio_id),
                "espacioId": str(datos.espacio_id),
                "unidad_id": unidad_id,
                "unidadId": unidad_id,
                "usuario_sub": usuario_sub,
                "usuarioSub": usuario_sub,
                "concepto": f"Reserva Espacio {datos.espacio_id}",
                "monto": monto_total,
                "monto_total": monto_total,
                "fecha_inicio": datos.fecha_inicio.isoformat(),
                "fecha_fin": datos.fecha_fin.isoformat(),
                "expira_en": expira_en.isoformat(),
                "timestamp": timestamp_iso,
            }
        ),
    )

    reserva_creada = await reserva_repository.crear(sesion, reserva, evento)
    res_id_str = str(reserva_creada.id) if reserva_creada and reserva_creada.id else "1"
    evento.carga_util = json.dumps(
        {
            "event_id": evt_id,
            "eventId": evt_id,
            "tipo": "reserva_espacio_creada",
            "reserva_id": res_id_str,
            "reservaId": res_id_str,
            "espacio_id": str(datos.espacio_id),
            "espacioId": str(datos.espacio_id),
            "unidad_id": unidad_id,
            "unidadId": unidad_id,
            "usuario_sub": usuario_sub,
            "usuarioSub": usuario_sub,
            "concepto": f"Reserva Espacio {datos.espacio_id}",
            "monto": monto_total,
            "monto_total": monto_total,
            "fecha_inicio": datos.fecha_inicio.isoformat(),
            "fecha_fin": datos.fecha_fin.isoformat(),
            "expira_en": expira_en.isoformat(),
            "timestamp": timestamp_iso,
        }
    )
    return reserva_creada

async def listar_por_usuario(sesion: AsyncSession, usuario_sub: str) -> list[Reserva]:
    if not usuario_sub or not usuario_sub.strip():
        raise ReservaFechaInvalidaException(
            "El identificador de usuario no puede estar vacío"
        )
    return await reserva_repository.obtener_por_usuario(sesion, usuario_sub)

async def listar_todas(sesion: AsyncSession) -> list[Reserva]:
    return await reserva_repository.obtener_todas(sesion)

async def confirmar_pago(sesion: AsyncSession, reserva_id: int) -> Reserva | None:
    return await reserva_repository.confirmar_pago(sesion, reserva_id)

async def cancelar_por_id(sesion: AsyncSession, reserva_id: int) -> Reserva | None:
    return await reserva_repository.cancelar_por_id(sesion, reserva_id)

async def compensar_por_gasto_fallido(
    sesion: AsyncSession,
    usuario_sub: str | None = None,
    espacio_id: int | None = None,
    fecha_inicio: datetime.datetime | None = None,
    reserva_id: int | None = None,
) -> Reserva | None:
    if reserva_id:
        return await reserva_repository.cancelar_por_id(sesion, reserva_id)
    if usuario_sub and espacio_id and fecha_inicio:
        return await reserva_repository.cancelar_por_evento(
            sesion, usuario_sub, espacio_id, fecha_inicio
        )
    return None
