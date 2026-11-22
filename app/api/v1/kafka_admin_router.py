from fastapi import APIRouter, Depends, Path, Response

from app.dto.kafka_admin import (
    PATRON_NOMBRE_TOPICO,
    ActualizarConfiguracionRequest,
    ConsumerGroupResponse,
    CrearTopicoRequest,
    TopicoResponse,
)
from app.middleware.auth_roles import requerir_roles
from app.service import kafka_admin_service

# Cambia la infraestructura de mensajería compartida: solo administrador.
router = APIRouter(
    prefix="/kafka",
    tags=["kafka-admin"],
    dependencies=[Depends(requerir_roles(["admin"]))],
)

_NOMBRE = Path(pattern=PATRON_NOMBRE_TOPICO)


@router.get("/topicos")
async def listar_topicos() -> list[TopicoResponse]:
    return await kafka_admin_service.listar_topicos()


@router.post("/topicos", status_code=201)
async def crear_topico(datos: CrearTopicoRequest) -> TopicoResponse:
    return await kafka_admin_service.crear_topico(datos)


@router.patch("/topicos/{nombre}/configuracion")
async def modificar_configuracion(
    datos: ActualizarConfiguracionRequest, nombre: str = _NOMBRE
) -> TopicoResponse:
    return await kafka_admin_service.modificar_configuracion(nombre, datos)


@router.delete("/topicos/{nombre}", status_code=204)
async def eliminar_topico(nombre: str = _NOMBRE) -> Response:
    await kafka_admin_service.eliminar_topico(nombre)
    return Response(status_code=204)


@router.get("/consumer-groups")
async def listar_consumer_groups() -> list[ConsumerGroupResponse]:
    return await kafka_admin_service.listar_consumer_groups()
