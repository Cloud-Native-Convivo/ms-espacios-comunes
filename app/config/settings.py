import logging
import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://localhost:8888")
_APLICACION = "ms-espacios-comunes"
_PERFIL = "native"
_ESQUEMAS_PERMITIDOS = {"http", "https"}

_MAPA_CLAVES = {
    "server.port": "PUERTO",
    "db.host": "DB_HOST",
    "db.port": "DB_PORT",
    "db.name": "DB_NAME",
    "db.username": "DB_USERNAME",
    "rabbitmq.host": "RABBITMQ_HOST",
    "rabbitmq.port": "RABBITMQ_PORT",
    "rabbitmq.usuario": "RABBITMQ_USUARIO",
    "eureka.url": "EUREKA_URL",
    "eureka.ip": "EUREKA_IP",
    "eureka.port": "EUREKA_PORT",
    "modo-debug": "MODO_DEBUG",
    "cors.origins": "CORS_ORIGINS",
}


def cargar_configuracion_remota(url_base: str = CONFIG_SERVER_URL) -> None:
    """Completa variables de entorno con lo servido por config-server, sin pisar env/.env locales.

    Precedencia: variable de entorno real > .env local > config-server > default del modelo.
    Best-effort — config-server puede no estar levantado en dev (sin auth propia, ver
    config-server/AGENTS.md §10); un fallo de red no impide el arranque.
    """
    load_dotenv()  # asegura que .env ya esté en os.environ antes de comparar

    esquema = urlparse(url_base).scheme
    if esquema not in _ESQUEMAS_PERMITIDOS:
        logger.warning("CONFIG_SERVER_URL con esquema no permitido (%s) — se ignora", esquema)
        return

    try:
        respuesta = httpx.get(f"{url_base}/{_APLICACION}/{_PERFIL}", timeout=3.0)
        respuesta.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("config-server no disponible (%s) — usando configuración local", error)
        return

    for fuente in respuesta.json().get("propertySources", []):
        for clave, valor in fuente.get("source", {}).items():
            variable = _MAPA_CLAVES.get(clave)
            if variable and variable not in os.environ:
                os.environ[variable] = str(valor)


cargar_configuracion_remota()


class Settings(BaseSettings):
    database_url: str | None = None

    # --- Base de datos Oracle ---
    db_host: str = "localhost"
    db_port: int = 1521
    db_name: str = "freepdb1"
    db_username: str = "admin"
    db_password: str = "oracle_password"


    # --- RabbitMQ ---
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_usuario: str = "guest"
    rabbitmq_contrasena: str = "guest"

    # --- Eureka ---
    eureka_url: str = "http://localhost:8761/eureka/"
    eureka_ip: str = "127.0.0.1"
    eureka_port: int = 8082

    # --- Servidor ---
    puerto: int = 8082
    modo_debug: bool = False
    config_server_url: str = CONFIG_SERVER_URL

    # --- CORS ---
    cors_origins: list[str] | str = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parsear_cors_origins(cls, v):
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    import json

                    parsed = json.loads(v_stripped)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
            return [origen.strip() for origen in v.split(",") if origen.strip()]
        if isinstance(v, list):
            return [str(origen).strip() for origen in v if str(origen).strip()]
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


    @property
    def url_base_datos(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"oracle+oracledb://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/?service_name={self.db_name}"
        )


settings = Settings()
