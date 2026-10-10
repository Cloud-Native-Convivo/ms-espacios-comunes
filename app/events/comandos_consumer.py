import asyncio
import json
import logging

import aio_pika
from pydantic import ValidationError
from tenacity import before_sleep_log, retry, wait_fixed

from app.config.database import fabrica_sesiones
from app.config.settings import settings
from app.dto.esquemas import (
    ActualizarEspacioRequest,
    CrearEspacioRequest,
    CrearReservaRequest,
)
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.exception.reserva_exception import (
    ReservaEspacioNoDisponibleException,
    ReservaFechaInvalidaException,
    ReservaSolapamientoException,
)
from app.model.solicitud_job import SolicitudJob
from app.repository import job_repository
from app.service import espacio_service, reserva_service

logger = logging.getLogger(__name__)

COLA_COMANDOS = "espacios_comandos_queue"


async def procesar_comando_mutacion(sesion, comando: dict):
    ticket_id = comando.get("ticket_id")
    modulo = comando.get("modulo", "ESPACIOS")
    accion = comando.get("accion", "")
    usuario_id = comando.get("usuario_id", "")
    rol = comando.get("rol", "")
    payload = comando.get("payload") or {}

    job = await job_repository.obtener_por_ticket_id(sesion, ticket_id)
    if not job:
        job = SolicitudJob(
            ticket_id=ticket_id,
            modulo=modulo,
            accion=accion,
            usuario_id=usuario_id,
            estado="PROCESANDO",
        )
        await job_repository.guardar_job(sesion, job)
    else:
        job.estado = "PROCESANDO"
        await sesion.flush()

    try:
        resultado = None
        if accion == "CREAR_RESERVA":
            req = CrearReservaRequest(**payload)
            reserva = await reserva_service.crear(sesion, req, usuario_sub=usuario_id)
            resultado = {
                "id": getattr(reserva, "id", None),
                "espacio_id": getattr(reserva, "espacio_id", None),
                "usuario_sub": getattr(reserva, "usuario_sub", None),
                "estado": getattr(reserva, "estado", None),
                "monto_total": float(getattr(reserva, "monto_total", 0.0) or 0.0),
            }
        elif accion == "CANCELAR_RESERVA":
            reserva_id = int(payload.get("reserva_id", 0))
            reserva = await reserva_service.cancelar_por_id(sesion, reserva_id)
            resultado = {
                "id": getattr(reserva, "id", None) if reserva else reserva_id,
                "estado": getattr(reserva, "estado", "cancelada") if reserva else "cancelada",
            }

        elif accion == "CREAR_ESPACIO":
            req = CrearEspacioRequest(**payload)
            espacio = await espacio_service.crear(sesion, req)
            resultado = {
                "id": getattr(espacio, "id", None),
                "nombre": getattr(espacio, "nombre", None),
            }
        elif accion == "ACTUALIZAR_ESPACIO":
            espacio_id = payload.get("espacio_id")
            req = ActualizarEspacioRequest(**payload)
            espacio = await espacio_service.actualizar(sesion, espacio_id, req)
            resultado = {
                "id": getattr(espacio, "id", None),
                "nombre": getattr(espacio, "nombre", None),
            }
        elif accion == "ELIMINAR_ESPACIO":
            espacio_id = payload.get("espacio_id")
            await espacio_service.eliminar(sesion, espacio_id)
            resultado = {"espacio_id": espacio_id, "eliminado": True}
        else:
            raise ValueError(f"Acción no reconocida: {accion}")

        job.estado = "COMPLETADO"
        job.resultado = json.dumps(resultado)
        job.error = None
        await sesion.commit()
    except ReservaSolapamientoException as exc:
        await sesion.rollback()
        error_info = {
            "codigo": "CONFLICTO_SOLAPAMIENTO",
            "mensaje": str(exc),
            "status_code": 409,
        }
        await job_repository.actualizar_estado_job(
            sesion, ticket_id, estado="FALLIDO", error=json.dumps(error_info)
        )
        await sesion.commit()
    except (
        ReservaEspacioNoDisponibleException,
        ReservaFechaInvalidaException,
        ValidationError,
        ValueError,
    ) as exc:
        await sesion.rollback()
        error_info = {
            "codigo": "VALIDACION_NEGOCIO",
            "mensaje": str(exc),
            "status_code": 400,
        }
        await job_repository.actualizar_estado_job(
            sesion, ticket_id, estado="FALLIDO", error=json.dumps(error_info)
        )
        await sesion.commit()
    except EspacioNoEncontradoException as exc:
        await sesion.rollback()
        error_info = {
            "codigo": "NO_ENCONTRADO",
            "mensaje": str(exc),
            "status_code": 404,
        }
        await job_repository.actualizar_estado_job(
            sesion, ticket_id, estado="FALLIDO", error=json.dumps(error_info)
        )
        await sesion.commit()
    except Exception as exc:
        await sesion.rollback()
        error_info = {
            "codigo": "ERROR_INTERNO",
            "mensaje": str(exc),
            "status_code": 500,
        }
        await job_repository.actualizar_estado_job(
            sesion, ticket_id, estado="FALLIDO", error=json.dumps(error_info)
        )
        await sesion.commit()


async def procesar_mensaje_comando(mensaje: aio_pika.IncomingMessage):
    try:
        comando = json.loads(mensaje.body.decode())
    except Exception as error_json:
        logger.exception(
            "Mensaje corrupto en cola de comandos (descartado): %s", error_json
        )
        await mensaje.ack()
        return

    try:
        async with mensaje.process(requeue=False):
            async with fabrica_sesiones() as sesion:
                await procesar_comando_mutacion(sesion, comando)
    except Exception as error_proc:
        logger.exception("Error operacional procesando comando: %s", error_proc)


@retry(wait=wait_fixed(10), before_sleep=before_sleep_log(logger, logging.ERROR))
async def consumidor_comandos():
    conexion = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_usuario,
        password=settings.rabbitmq_contrasena,
    )
    canal = await conexion.channel()
    await canal.set_qos(prefetch_count=5)
    cola = await canal.declare_queue(COLA_COMANDOS, durable=True)
    await cola.consume(procesar_mensaje_comando)
    logger.info("Consumidor RabbitMQ activo en cola '%s'", COLA_COMANDOS)

    try:
        await asyncio.Future()
    finally:
        await conexion.close()
