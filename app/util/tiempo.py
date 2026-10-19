"""Reloj UTC compartido: reserva_service.crear(), expiracion_worker.py y
existe_solapamiento() deben comparar expira_en contra la MISMA base de
tiempo. func.now() de SQLAlchemy compila a CURRENT_TIMESTAMP en Oracle, que
devuelve la hora en la zona de la SESIÓN (la del cliente que conecta, no
UTC) — por eso existe_solapamiento ya no usa func.now(), recibe `ahora`
calculado acá.
"""

import datetime


def ahora_utc() -> datetime.datetime:
    """Hora actual en UTC, sin tzinfo (naive) para comparar contra columnas
    DateTime (sin zona) que ya se guardan en esta misma base."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
