import datetime
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.esquemas import CrearReservaRequest
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.model.modelos import EventoOutbox, Espacio, Reserva
from app.repository import espacio_repository, reserva_repository
from app.util.tiempo import ahora_utc


def payload_reserva(
    reserva: Reserva,
    espacio: Espacio | None,
    tipo: str,
    event_id: str,
) -> str:
    """Payload común a reserva_espacio_creada / reserva_confirmada / reserva_expirada.

    Mantiene snake_case y camelCase (ms-gastos-comunes acepta ambos via
    @JsonAlias) y conserva todos los campos que ya existían, para no romper
    ReservaEspacioCreadaEvent del lado de gastos.
    """
    espacio_nombre = espacio.nombre if espacio else str(reserva.espacio_id)
    unidad_id = f"unidad-{reserva.usuario_sub}"
    return json.dumps(
        {
            "event_id": event_id,
            "eventId": event_id,
            "tipo": tipo,
            "reserva_id": str(reserva.id) if reserva.id else None,
            "reservaId": str(reserva.id) if reserva.id else None,
            "espacio_id": str(reserva.espacio_id),
            "espacioId": str(reserva.espacio_id),
            "espacio_nombre": espacio_nombre,
            "espacioNombre": espacio_nombre,
            "unidad_id": unidad_id,
            "unidadId": unidad_id,
            "usuario_sub": reserva.usuario_sub,
            "usuarioSub": reserva.usuario_sub,
            "email": reserva.usuario_email or "",
            "concepto": f"Reserva Espacio {reserva.espacio_id}",
            "monto": float(reserva.monto_total),
            "monto_total": float(reserva.monto_total),
            "fecha_inicio": reserva.fecha_inicio.isoformat(),
            "fecha_fin": reserva.fecha_fin.isoformat(),
            "expira_en": reserva.expira_en.isoformat() if reserva.expira_en else None,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )


async def crear(
    sesion: AsyncSession,
    datos: CrearReservaRequest,
    usuario_sub: str,
    usuario_email: str | None = None,
) -> Reserva:
    if not usuario_sub or not usuario_sub.strip():
        raise ReservaFechaInvalidaException(
            "El identificador de usuario no puede estar vacío"
        )

    # Hora local, sin cambios respecto al comportamiento anterior: solo se usa
    # para validar fecha_inicio/fecha_fin (nunca se guardan ni se devuelven
    # distinto). El UTC queda acotado a expira_en (ver más abajo), que es lo
    # único que compara expiracion_worker.py.
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

    # Mismo ahora_utc() para existe_solapamiento y para expira_en más abajo:
    # las dos comparaciones deben usar exactamente el mismo reloj (ver
    # app/util/tiempo.py) — nunca func.now(), que en Oracle devuelve la hora
    # de la zona de la SESIÓN, no UTC.
    ahora_utc_actual = ahora_utc()
    if await reserva_repository.existe_solapamiento(
        sesion, datos.espacio_id, datos.fecha_inicio, datos.fecha_fin, ahora_utc_actual
    ):
        raise ReservaSolapamientoException(
            datos.espacio_id,
            datos.fecha_inicio.isoformat(),
            datos.fecha_fin.isoformat(),
        )

    duracion_segundos = (fecha_fin_cmp - fecha_inicio_cmp).total_seconds()
    duracion_horas = duracion_segundos / 3600.0
    monto_total = round(duracion_horas * tarifa_hora, 2)
    expira_en = ahora_utc_actual + datetime.timedelta(minutes=15)

    reserva = Reserva(
        espacio_id=datos.espacio_id,
        usuario_sub=usuario_sub,
        usuario_email=usuario_email,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=datos.fecha_fin,
        estado="pendiente_pago",
        monto_total=monto_total,
        expira_en=expira_en,
    )

    evt_id = str(uuid.uuid4())
    evento = EventoOutbox(
        tipo_evento="reserva_espacio_creada",
        carga_util=payload_reserva(reserva, espacio, "reserva_espacio_creada", evt_id),
    )

    reserva_creada = await reserva_repository.crear(sesion, reserva, evento)
    # reserva_repository.crear devuelve el mismo objeto que recibe (ya con el
    # id asignado tras el flush) — se reconstruye desde `reserva`, no desde
    # `reserva_creada`, para no depender de que el valor de retorno conserve
    # los mismos campos (un mock de test puede sustituirlo por otro objeto).
    evento.carga_util = payload_reserva(reserva, espacio, "reserva_espacio_creada", evt_id)
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
