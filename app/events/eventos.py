"""Lectura y validación del JSON de los eventos de reserva (puerto del
prototipo prototipo-rabbit-residente/eventos.py). Si falta un campo
obligatorio, EventoInvalido: reintentar no lo arregla, va directo a la DLQ.
Acepta snake_case y camelCase porque el outbox de espacios publica ambos.
"""

import datetime
import json
from dataclasses import dataclass


def formatear_fecha(valor: str) -> str:
    try:
        return datetime.datetime.fromisoformat(valor.replace("Z", "+00:00")).strftime("%d-%m-%Y %H:%M")
    except (ValueError, AttributeError):
        return valor


class EventoInvalido(Exception):
    """El mensaje no se puede procesar nunca (JSON roto o datos faltantes)."""


def _campo(datos: dict, *nombres: str, obligatorio: bool = True, defecto=None):
    for nombre in nombres:
        valor = datos.get(nombre)
        if valor not in (None, ""):
            return valor
    if obligatorio:
        raise EventoInvalido(f"Falta el campo obligatorio '{nombres[0]}'")
    return defecto


@dataclass
class EventoReserva:
    event_id: str
    tipo: str
    reserva_id: str
    email: str
    nombre_residente: str
    espacio: str
    fecha_inicio: str
    fecha_fin: str
    monto: float


def leer_evento(cuerpo: bytes) -> EventoReserva:
    try:
        datos = json.loads(cuerpo)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise EventoInvalido(f"JSON inválido: {error}") from error

    if not isinstance(datos, dict):
        raise EventoInvalido("El mensaje no es un objeto JSON")

    try:
        monto = float(_campo(datos, "monto", "monto_total", "montoTotal", obligatorio=False, defecto=0))
    except (TypeError, ValueError) as error:
        raise EventoInvalido("El monto no es un número") from error

    return EventoReserva(
        event_id=str(_campo(datos, "event_id", "eventId")),
        tipo=str(_campo(datos, "tipo", "tipo_evento", obligatorio=False, defecto="")),
        reserva_id=str(_campo(datos, "reserva_id", "reservaId")),
        email=str(_campo(datos, "email", "usuario_email", "usuarioEmail")),
        nombre_residente=str(_campo(datos, "nombre_residente", "nombreResidente", obligatorio=False, defecto="residente")),
        espacio=str(_campo(datos, "espacio_nombre", "espacioNombre", "espacio_id", "espacioId", obligatorio=False, defecto="-")),
        fecha_inicio=formatear_fecha(str(_campo(datos, "fecha_inicio", "fechaInicio", obligatorio=False, defecto="-"))),
        fecha_fin=formatear_fecha(str(_campo(datos, "fecha_fin", "fechaFin", obligatorio=False, defecto="-"))),
        monto=monto,
    )
