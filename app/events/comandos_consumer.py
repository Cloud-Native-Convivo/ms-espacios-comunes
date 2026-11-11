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
COLA_COMANDOS_DLQ = "espacios_comandos_dlq"
EXCHANGE_DLX = "espacios_dlx"


def _id_positivo(comando: dict, campo: str) -> int:
    """Lee un id de primer nivel del comando; falta o no es entero > 0 -> ValueError."""
    valor = comando.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(f"'{campo}' es obligatorio y debe ser un entero positivo")
    return valor


async def _ejecutar_accion(sesion, comando: dict) -> dict:
    """Aplica la accion del comando y devuelve el resultado que ve el cliente."""
    accion = comando.get("accion", "")
    payload = comando.get("payload") or {}

    if accion == "CREAR_RESERVA":
        req = CrearReservaRequest(**payload)
        reserva = await reserva_service.crear(
            sesion,
            req,
            usuario_sub=comando.get("usuario_id", ""),
            usuario_email=comando.get("usuario_email"),
        )
        return {
            "id": getattr(reserva, "id", None),
            "espacio_id": getattr(reserva, "espacio_id", None),
            "usuario_sub": getattr(reserva, "usuario_sub", None),
            "estado": getattr(reserva, "estado", None),
            "monto_total": float(getattr(reserva, "monto_total", 0.0) or 0.0),
        }
    if accion == "CANCELAR_RESERVA":
        reserva_id = int(payload.get("reserva_id", 0))
        reserva = await reserva_service.cancelar_por_id(sesion, reserva_id)
        return {
            "id": getattr(reserva, "id", None) if reserva else reserva_id,
            "estado": getattr(reserva, "estado", "cancelada") if reserva else "cancelada",
        }
    if accion == "CREAR_ESPACIO":
        # El condominio del comando (lo fija el bff) manda sobre el del payload.
        if comando.get("condominio_id") is not None:
            payload = {**payload, "condominio_id": comando["condominio_id"]}
        espacio = await espacio_service.crear(sesion, CrearEspacioRequest(**payload))
        return {
            "id": getattr(espacio, "id", None),
            "nombre": getattr(espacio, "nombre", None),
        }
    if accion in ("ACTUALIZAR_ESPACIO", "MODIFICAR_ESPACIO"):
        # PUT y PATCH comparten rama: todos los campos de la request son opcionales.
        espacio_id = _id_positivo(comando, "espacio_id")
        condominio_id = _id_positivo(comando, "condominio_id")
        espacio = await espacio_service.actualizar(
            sesion, espacio_id, condominio_id, ActualizarEspacioRequest(**payload)
        )
        return {
            "id": getattr(espacio, "id", None),
            "nombre": getattr(espacio, "nombre", None),
        }
    if accion == "ELIMINAR_ESPACIO":
        espacio_id = _id_positivo(comando, "espacio_id")
        condominio_id = _id_positivo(comando, "condominio_id")
        # El servicio inactiva el espacio si tiene reservas en vez de borrarlo.
        desenlace = await espacio_service.eliminar(sesion, espacio_id, condominio_id)
        return {
            "espacio_id": espacio_id,
            "eliminado": desenlace == "eliminado",
            "resultado": desenlace,
        }
    raise ValueError(f"Acción no reconocida: {accion}")


def _describir_error(exc: Exception) -> dict:
    """Clasifica la excepcion; el detalle interno no sale al cliente."""
    if isinstance(exc, ReservaSolapamientoException):
        return {"codigo": "CONFLICTO_SOLAPAMIENTO", "mensaje": str(exc), "status_code": 409}
    if isinstance(
        exc,
        (
            ReservaEspacioNoDisponibleException,
            ReservaFechaInvalidaException,
            ValidationError,
            ValueError,
        ),
    ):
        return {"codigo": "VALIDACION_NEGOCIO", "mensaje": str(exc), "status_code": 400}
    if isinstance(exc, EspacioNoEncontradoException):
        return {"codigo": "NO_ENCONTRADO", "mensaje": str(exc), "status_code": 404}
    return {
        "codigo": "ERROR_INTERNO",
        "mensaje": "Error interno al procesar la solicitud",
        "status_code": 500,
    }


async def procesar_comando_mutacion(sesion, comando: dict):
    ticket_id = comando.get("ticket_id")

    job = await job_repository.obtener_por_ticket_id(sesion, ticket_id)
    if not job:
        job = SolicitudJob(
            ticket_id=ticket_id,
            modulo=comando.get("modulo", "ESPACIOS"),
            accion=comando.get("accion", ""),
            usuario_id=comando.get("usuario_id", ""),
            estado="PROCESANDO",
        )
        await job_repository.guardar_job(sesion, job)
    else:
        job.estado = "PROCESANDO"
        await sesion.flush()
    # El job se confirma antes de ejecutar la accion: si la accion falla, su
    # rollback no puede llevarse el job y el estado FALLIDO siempre se guarda.
    await sesion.commit()

    try:
        resultado = await _ejecutar_accion(sesion, comando)
        job.estado = "COMPLETADO"
        job.resultado = json.dumps(resultado)
        job.error = None
        await sesion.commit()
    except Exception as exc:
        await sesion.rollback()
        error_info = _describir_error(exc)
        if error_info["status_code"] == 500:
            logger.exception("Comando [%s] fallo con error interno", ticket_id)
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

    exchange_dlx = await canal.declare_exchange(
        EXCHANGE_DLX, aio_pika.ExchangeType.DIRECT, durable=True
    )
    cola_dlq = await canal.declare_queue(COLA_COMANDOS_DLQ, durable=True)
    await cola_dlq.bind(exchange_dlx, routing_key=COLA_COMANDOS_DLQ)

    cola = await canal.declare_queue(
        COLA_COMANDOS,
        durable=True,
        arguments={
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": COLA_COMANDOS_DLQ,
        },
    )
    await cola.consume(procesar_mensaje_comando)
    logger.info("Consumidor RabbitMQ activo en cola '%s' (con DLX '%s')", COLA_COMANDOS, EXCHANGE_DLX)

    try:
        await asyncio.Future()
    finally:
        await conexion.close()
