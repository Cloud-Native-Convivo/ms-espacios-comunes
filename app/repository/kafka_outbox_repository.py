from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.modelos import EventoOutboxKafka


async def obtener_pendientes(sesion: AsyncSession) -> list[EventoOutboxKafka]:
    """Eventos aún no publicados, en orden de inserción (id), bloqueando solo los propios.

    Nota: sin LIMIT a propósito. En Oracle, LIMIT + FOR UPDATE se compila como
    subconsulta y falla con ORA-02014; un backlog grande se envía en un solo lote.
    """
    consulta = (
        select(EventoOutboxKafka)
        .where(EventoOutboxKafka.procesado == False)  # noqa: E712
        .order_by(EventoOutboxKafka.id)
        .with_for_update(skip_locked=True)
    )
    resultado = await sesion.execute(consulta)
    return list(resultado.scalars().all())
