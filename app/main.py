import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from py_eureka_client import eureka_client

from app.api.router import api_router
from app.config.settings import settings
from app.events.compensacion_consumer import consumidor_compensacion
from app.events.outbox_event import relay_outbox
from app.handler.exception_handler import registrar_manejadores_excepciones
from app.middleware.logging_middleware import LoggingMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(aplicacion: FastAPI):
    await eureka_client.init_async(
        eureka_server=settings.eureka_url,
        app_name="ms-espacios-comunes",
        instance_ip=settings.eureka_ip,
        instance_port=settings.eureka_port,
        instance_host="ms-espacios-comunes",
    )
    logger.info("Registrado en Eureka")

    asyncio.create_task(relay_outbox())
    asyncio.create_task(consumidor_compensacion())
    logger.info("Tareas de eventos iniciadas")

    yield


app = FastAPI(
    title="ms-espacios-comunes",
    description="Microservicio de espacios comunes y reservas — Convivo",
    version="0.1.0",
    lifespan=lifespan,
)

registrar_manejadores_excepciones(app)
app.add_middleware(LoggingMiddleware)
app.include_router(api_router)
