"""Lecturas del modelo de estadísticas que proyecta app/events/kafka_estadisticas.py."""

import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import EstadisticaEspacio, EstadisticaEspacioDia


async def obtener_estados(sesion: AsyncSession, condominio_id: int) -> list[EstadisticaEspacio]:
    """Estado proyectado de cada espacio del condominio."""
    consulta = (
        select(EstadisticaEspacio)
        .where(EstadisticaEspacio.condominio_id == condominio_id)
        .order_by(EstadisticaEspacio.espacio_id)
    )
    resultado = await sesion.execute(consulta)
    return list(resultado.scalars().all())


async def sumar_contadores(
    sesion: AsyncSession, condominio_id: int, desde: datetime.date
) -> list:
    """Contadores sumados por espacio desde `desde` (inclusive), ordenados por
    reservas confirmadas y luego por horas confirmadas, de mayor a menor."""
    confirmadas = func.sum(EstadisticaEspacioDia.reservas_confirmadas).label("reservas_confirmadas")
    horas = func.sum(EstadisticaEspacioDia.horas_confirmadas).label("horas_confirmadas")
    consulta = (
        select(
            EstadisticaEspacioDia.espacio_id,
            func.sum(EstadisticaEspacioDia.reservas_creadas).label("reservas_creadas"),
            confirmadas,
            func.sum(EstadisticaEspacioDia.reservas_canceladas).label("reservas_canceladas"),
            func.sum(EstadisticaEspacioDia.reservas_expiradas).label("reservas_expiradas"),
            horas,
        )
        .where(
            EstadisticaEspacioDia.condominio_id == condominio_id,
            EstadisticaEspacioDia.fecha >= desde,
        )
        .group_by(EstadisticaEspacioDia.espacio_id)
        .order_by(confirmadas.desc(), horas.desc(), EstadisticaEspacioDia.espacio_id)
    )
    resultado = await sesion.execute(consulta)
    return list(resultado.all())
