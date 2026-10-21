from sqlalchemy.ext.asyncio import AsyncSession

from app.model.solicitud_job import SolicitudJob


async def guardar_job(sesion: AsyncSession, job: SolicitudJob) -> SolicitudJob:
    sesion.add(job)
    await sesion.flush()
    return job


async def obtener_por_ticket_id(
    sesion: AsyncSession, ticket_id: str
) -> SolicitudJob | None:
    return await sesion.get(SolicitudJob, ticket_id)


async def actualizar_estado_job(
    sesion: AsyncSession,
    ticket_id: str,
    estado: str,
    resultado: str | None = None,
    error: str | None = None,
) -> SolicitudJob | None:
    job = await obtener_por_ticket_id(sesion, ticket_id)
    if job:
        job.estado = estado
        if resultado is not None:
            job.resultado = resultado
        if error is not None:
            job.error = error
        await sesion.flush()
    return job
