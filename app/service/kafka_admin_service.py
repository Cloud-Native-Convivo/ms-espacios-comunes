"""Administración de tópicos y consumer groups de Kafka con AIOKafkaAdminClient.

Crear, eliminar y alterar configuración no lanzan excepción ante un error del
broker: devuelven códigos por tópico que aquí se revisan uno a uno.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType
from aiokafka.errors import (
    KafkaConnectionError,
    TopicAlreadyExistsError,
    UnknownTopicOrPartitionError,
    for_code,
)

from app.config.settings import settings
from app.dto.kafka_admin import ConfiguracionTopico, CrearTopicoRequest
from app.dto.kafka_eventos import TOPICO_ALERTAS, TOPICO_HISTORIAL
from app.exception.kafka_admin_exception import KafkaAdminException

TOPICOS_PROTEGIDOS = frozenset({TOPICO_HISTORIAL, TOPICO_ALERTAS})
CLAVES_KAFKA = {
    "retencion_ms": "retention.ms",
    "cleanup_policy": "cleanup.policy",
    "min_insync_replicas": "min.insync.replicas",
}
# config_source de DescribeConfigs v1+: 1 = override dinámico del tópico.
_OVERRIDE_DEL_TOPICO = 1
_INTENTOS_METADATA = 10
_ESPERA_METADATA_S = 0.3
_ESTADO_POR_ERROR = {
    TopicAlreadyExistsError.errno: 409,
    UnknownTopicOrPartitionError.errno: 404,
}


def es_protegido(nombre: str) -> bool:
    """Tópicos del sistema y los internos de Kafka (__consumer_offsets, ...)."""
    return nombre in TOPICOS_PROTEGIDOS or nombre.startswith("__")


@asynccontextmanager
async def _conexion(cliente, cerrar) -> AsyncIterator:
    """Arranca el cliente y lo cierra siempre; Kafka caído se traduce a 503."""
    try:
        await cliente.start()
        yield cliente
    except KafkaConnectionError as error:
        raise KafkaAdminException(503, "Kafka no está disponible") from error
    finally:
        await cerrar()


def _admin():
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-admin",
    )
    return _conexion(admin, admin.close)


def _verificar(topico: str, codigo: int, mensaje: str | None = None) -> None:
    if codigo:
        detalle = mensaje or for_code(codigo).message
        raise KafkaAdminException(
            _ESTADO_POR_ERROR.get(codigo, 400), f"Tópico {topico}: {detalle}"
        )


def _a_kafka(datos: ConfiguracionTopico) -> dict[str, str]:
    """Campos con valor -> nombres y valores (texto) que entiende Kafka."""
    return {
        CLAVES_KAFKA[campo]: str(valor)
        for campo, valor in datos.model_dump(include=set(CLAVES_KAFKA)).items()
        if valor is not None
    }


async def _leer_configuracion(admin, nombres: list[str]) -> dict[str, dict[str, dict]]:
    """Tópico -> {nombre de configuración -> entrada de DescribeConfigs}."""
    respuestas = await admin.describe_configs(
        [ConfigResource(ConfigResourceType.TOPIC, nombre) for nombre in nombres]
    )
    resultado = {}
    for respuesta in respuestas:
        for recurso in respuesta.to_object()["resources"]:
            nombre = recurso["resource_name"]
            _verificar(nombre, recurso["error_code"], recurso["error_message"])
            resultado[nombre] = {e["config_names"]: e for e in recurso["config_entries"]}
    return resultado


async def _describir(admin, nombres: list[str] | None = None) -> list[dict]:
    topicos = [t for t in await admin.describe_topics(nombres) if not t["is_internal"]]
    for topico in topicos:
        _verificar(topico["topic"], topico["error_code"])
    if not topicos:
        return []
    configuracion = await _leer_configuracion(admin, [t["topic"] for t in topicos])
    return sorted(
        (
            {
                "nombre": t["topic"],
                "particiones": len(t["partitions"]),
                "factor_replicacion": len(t["partitions"][0]["replicas"]) if t["partitions"] else 0,
                "protegido": es_protegido(t["topic"]),
                "configuracion": {
                    clave: configuracion[t["topic"]].get(clave, {}).get("config_value")
                    for clave in CLAVES_KAFKA.values()
                },
            }
            for t in topicos
        ),
        key=lambda t: t["nombre"],
    )


async def listar_topicos() -> list[dict]:
    """Tópicos de usuario (sin los internos de Kafka) con su configuración efectiva."""
    async with _admin() as admin:
        return await _describir(admin)


async def crear_topico(datos: CrearTopicoRequest) -> dict:
    """Crea el tópico; 409 si ya existe, 400 si el broker rechaza la configuración."""
    nuevo = NewTopic(
        datos.nombre, datos.particiones, datos.factor_replicacion, topic_configs=_a_kafka(datos)
    )
    async with _admin() as admin:
        respuesta = await admin.create_topics([nuevo])
        for topico, codigo, *mensaje in respuesta.topic_errors:
            _verificar(topico, codigo, mensaje[0] if mensaje else None)
        # El controller ya lo creó, pero la metadata del broker consultado puede
        # tardar unos instantes en conocerlo.
        for _ in range(_INTENTOS_METADATA - 1):
            try:
                return (await _describir(admin, [datos.nombre]))[0]
            except KafkaAdminException as error:
                if error.estado != 404:
                    raise
                await asyncio.sleep(_ESPERA_METADATA_S)
        return (await _describir(admin, [datos.nombre]))[0]


async def modificar_configuracion(nombre: str, datos: ConfiguracionTopico) -> dict:
    """Cambia solo los campos enviados y conserva los demás overrides del tópico.

    AlterConfigs reemplaza todos los overrides del recurso: si se mandara solo
    retention.ms, min.insync.replicas volvería al default del broker. Por eso
    se leen los overrides actuales y se mezclan con los nuevos.
    """
    async with _admin() as admin:
        factor = (await _describir(admin, [nombre]))[0]["factor_replicacion"]
        if (datos.min_insync_replicas or 0) > factor:
            # Kafka lo acepta, pero después rechaza toda escritura con acks=all.
            raise KafkaAdminException(
                400,
                f"min_insync_replicas ({datos.min_insync_replicas}) supera el factor"
                f" de replicación del tópico ({factor})",
            )
        actuales = (await _leer_configuracion(admin, [nombre]))[nombre]
        overrides = {
            clave: entrada["config_value"]
            for clave, entrada in actuales.items()
            if entrada["config_source"] == _OVERRIDE_DEL_TOPICO
            and entrada["config_value"] is not None
        }
        recurso = ConfigResource(
            ConfigResourceType.TOPIC, nombre, configs=overrides | _a_kafka(datos)
        )
        for respuesta in await admin.alter_configs([recurso]):
            for codigo, mensaje, *_ in respuesta.resources:
                _verificar(nombre, codigo, mensaje)
        return (await _describir(admin, [nombre]))[0]


async def eliminar_topico(nombre: str) -> None:
    """Elimina el tópico; los del sistema responden 409 sin llegar a Kafka."""
    if es_protegido(nombre):
        raise KafkaAdminException(
            409, f"El tópico {nombre} es del sistema y no se puede eliminar"
        )
    async with _admin() as admin:
        respuesta = await admin.delete_topics([nombre])
    for topico, codigo, *_ in respuesta.topic_error_codes:
        _verificar(topico, codigo)


async def _offsets_finales(particiones: list[TopicPartition]) -> dict[TopicPartition, int]:
    consumidor = AIOKafkaConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-admin",
        enable_auto_commit=False,
    )
    async with _conexion(consumidor, consumidor.stop):
        return await consumidor.end_offsets(particiones)


async def listar_consumer_groups() -> list[dict]:
    """Cada grupo con su offset confirmado, el final y el lag por partición."""
    async with _admin() as admin:
        existentes = set(await admin.list_topics())
        grupos = sorted(grupo for grupo, *_ in await admin.list_consumer_groups())
        offsets = {
            grupo: {
                tp: om.offset
                for tp, om in (await admin.list_consumer_group_offsets(grupo)).items()
                if tp.topic in existentes  # un tópico eliminado deja offsets huérfanos
            }
            for grupo in grupos
        }
    particiones = sorted({tp for por_grupo in offsets.values() for tp in por_grupo})
    finales = await _offsets_finales(particiones) if particiones else {}
    resultado = []
    for grupo in grupos:
        detalle = [
            {
                "topico": tp.topic,
                "particion": tp.partition,
                "offset_confirmado": offset,
                "offset_final": finales[tp],
                "lag": max(finales[tp] - offset, 0),
            }
            for tp, offset in sorted(offsets[grupo].items())
        ]
        resultado.append(
            {"grupo": grupo, "lag_total": sum(p["lag"] for p in detalle), "particiones": detalle}
        )
    return resultado
