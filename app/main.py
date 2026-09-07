import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from py_eureka_client import eureka_client

from app.api.router import api_router
from app.config.database import motor
from app.config.settings import settings
from app.events.compensacion_consumer import consumidor_compensacion
from app.events.expiracion_worker import worker_expiracion
from app.events.outbox_event import relay_outbox
from app.handler.exception_handler import registrar_manejadores_excepciones
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.security_middleware import SecurityHeadersMiddleware
from app.model.modelos import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(aplicacion: FastAPI):
    if settings.eureka_url:
        try:
            await eureka_client.init_async(
                eureka_server=settings.eureka_url,
                app_name="ms-espacios-comunes",
                instance_ip=settings.eureka_ip,
                instance_port=settings.eureka_port,
                instance_host="ms-espacios-comunes",
            )
            logger.info("Registrado en Eureka")
        except Exception as error:
            logger.warning("Eureka no disponible (%s) — continuando", error)

    try:
        async with motor.begin() as conexion:
            await conexion.run_sync(Base.metadata.create_all)
        logger.info("Tablas de base de datos verificadas")
    except Exception as error:
        logger.warning("Error inicializando tablas en base de datos: %s", error)

    tarea_outbox = asyncio.create_task(relay_outbox())
    tarea_compensacion = asyncio.create_task(consumidor_compensacion())
    tarea_expiracion = asyncio.create_task(worker_expiracion())
    logger.info("Tareas de eventos e expiración iniciadas")

    try:
        yield
    finally:
        logger.info("Deteniendo tareas de background...")
        tarea_outbox.cancel()
        tarea_compensacion.cancel()
        tarea_expiracion.cancel()
        await asyncio.gather(
            tarea_outbox,
            tarea_compensacion,
            tarea_expiracion,
            return_exceptions=True,
        )
        if settings.eureka_url:
            try:
                await eureka_client.stop_async()
            except Exception:
                pass
        logger.info("Tareas de background finalizadas limpiamente")



app = FastAPI(
    title="ms-espacios-comunes",
    description="Microservicio de espacios comunes y reservas — Convivo",
    version="0.2.1",
    lifespan=lifespan,
)


registrar_manejadores_excepciones(app)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)
app.include_router(api_router)

