import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.esquemas import EstadisticaEspacioResponse
from app.repository import estadisticas_repository


def _desde(dias: int, hoy: datetime.date | None = None) -> datetime.date:
    """Primer día (UTC) de una ventana de `dias` días que incluye hoy."""
    hoy = hoy or datetime.datetime.now(datetime.UTC).date()
    return hoy - datetime.timedelta(days=dias - 1)


def _respuesta(espacio_id: int, estado: str, fila) -> EstadisticaEspacioResponse:
    return EstadisticaEspacioResponse(
        espacio_id=espacio_id,
        estado=estado,
        disponible=estado == "activo",
        reservas_creadas=int(fila.reservas_creadas or 0) if fila else 0,
        reservas_confirmadas=int(fila.reservas_confirmadas or 0) if fila else 0,
        reservas_canceladas=int(fila.reservas_canceladas or 0) if fila else 0,
        reservas_expiradas=int(fila.reservas_expiradas or 0) if fila else 0,
        horas_confirmadas=float(fila.horas_confirmadas or 0) if fila else 0.0,
    )


async def listar(
    sesion: AsyncSession, condominio_id: int, dias: int
) -> list[EstadisticaEspacioResponse]:
    """Disponibilidad y uso de todos los espacios conocidos del condominio en la ventana."""
    estados = await estadisticas_repository.obtener_estados(sesion, condominio_id)
    contadores = {
        fila.espacio_id: fila
        for fila in await estadisticas_repository.sumar_contadores(
            sesion, condominio_id, _desde(dias)
        )
    }
    return [_respuesta(e.espacio_id, e.estado, contadores.get(e.espacio_id)) for e in estados]


async def preferidos(
    sesion: AsyncSession, condominio_id: int, dias: int, limite: int
) -> list[EstadisticaEspacioResponse]:
    """Espacios con más reservas confirmadas en la ventana (desempate: horas confirmadas).

    Solo entran espacios con al menos una reserva confirmada.
    """
    estados = {
        e.espacio_id: e.estado
        for e in await estadisticas_repository.obtener_estados(sesion, condominio_id)
    }
    filas = await estadisticas_repository.sumar_contadores(sesion, condominio_id, _desde(dias))
    ranking = [f for f in filas if (f.reservas_confirmadas or 0) > 0][:limite]
    return [_respuesta(f.espacio_id, estados.get(f.espacio_id, "activo"), f) for f in ranking]
