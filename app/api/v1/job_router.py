import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import obtener_sesion
from app.repository import job_repository

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _parse_payload(val: str | None):
    if not val:
        return None
    try:
        return json.loads(val)
    except Exception:
        return val


@router.get("/{ticket_id}")
async def consultar_job(
    ticket_id: str,
    sesion: AsyncSession = Depends(obtener_sesion),
):
    job = await job_repository.obtener_por_ticket_id(sesion, ticket_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    return {
        "ticket_id": job.ticket_id,
        "modulo": job.modulo,
        "accion": job.accion,
        "estado": job.estado,
        "resultado": _parse_payload(job.resultado),
        "error": _parse_payload(job.error),
        "creado_en": job.creado_en.isoformat() if job.creado_en else None,
        "actualizado_en": job.actualizado_en.isoformat() if job.actualizado_en else None,
    }
