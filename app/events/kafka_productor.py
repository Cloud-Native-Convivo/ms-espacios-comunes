"""Configuración del productor Kafka (aiokafka).

acks=all + idempotencia: con min.insync.replicas=2 en los tópicos, un envío
solo se confirma cuando al menos 2 de las 3 réplicas lo tienen, y los
reintentos del productor no duplican mensajes en la partición.
"""

from aiokafka import AIOKafkaProducer
from pydantic import BaseModel

from app.config.settings import settings


def serializar_valor(evento: BaseModel) -> bytes:
    return evento.model_dump_json().encode("utf-8")


def serializar_clave(clave: str) -> bytes:
    return clave.encode("utf-8")


def opciones_productor() -> dict:
    """Parámetros del productor; separados de la construcción para poder testearlos."""
    return {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "client_id": settings.kafka_client_id,
        "acks": "all",
        "enable_idempotence": True,
        "key_serializer": serializar_clave,
        "value_serializer": serializar_valor,
    }


def crear_productor_kafka() -> AIOKafkaProducer:
    """Crea el productor sin conectarlo; el llamador hace start()/stop()."""
    return AIOKafkaProducer(**opciones_productor())
