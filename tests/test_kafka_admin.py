"""Administrador de Kafka: servicio con AIOKafkaAdminClient simulado y endpoints.

Técnica: partición de equivalencia por resultado del broker (ok, ya existe,
no existe, configuración inválida, Kafka caído), tabla de decisión para
eliminar (protegido / interno / normal) y valores límite para
min.insync.replicas frente al factor de replicación (igual válido, mayor no).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiokafka import TopicPartition
from aiokafka.errors import KafkaConnectionError
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.dto.kafka_admin import ActualizarConfiguracionRequest, CrearTopicoRequest
from app.exception.kafka_admin_exception import KafkaAdminException
from app.main import app
from app.service import kafka_admin_service as servicio

TOPICO = "demo.admin.v1"


def _topico(nombre, particiones=3, replicas=3, error=0, interno=False):
    return {
        "topic": nombre,
        "error_code": error,
        "is_internal": interno,
        "partitions": [
            {"partition": p, "replicas": list(range(replicas))} for p in range(particiones)
        ],
    }


def _entrada(nombre, valor, fuente=1):
    return {"config_names": nombre, "config_value": valor, "config_source": fuente}


def _configs(*recursos):
    """recursos: (nombre, [entradas], error_code)."""
    return [
        SimpleNamespace(
            to_object=lambda: {
                "resources": [
                    {
                        "resource_name": n,
                        "error_code": e,
                        "error_message": None,
                        "config_entries": entradas,
                    }
                    for n, entradas, e in recursos
                ]
            }
        )
    ]


@pytest.fixture
def admin():
    a = MagicMock()
    for metodo in (
        "start", "close", "describe_topics", "describe_configs", "create_topics",
        "alter_configs", "delete_topics", "list_topics", "list_consumer_groups",
        "list_consumer_group_offsets",
    ):
        setattr(a, metodo, AsyncMock())
    a.describe_topics.return_value = [_topico(TOPICO)]
    a.describe_configs.return_value = _configs(
        (TOPICO, [_entrada("retention.ms", "86400000"), _entrada("min.insync.replicas", "2")], 0)
    )
    with patch.object(servicio, "AIOKafkaAdminClient", return_value=a):
        yield a


# --- Listar -------------------------------------------------------------------


async def test_listar_excluye_internos_y_marca_protegidos(admin):
    admin.describe_topics.return_value = [
        _topico("espacios.historial.v1"),
        _topico("__consumer_offsets", interno=True),
        _topico(TOPICO),
    ]
    admin.describe_configs.return_value = _configs(
        ("espacios.historial.v1", [_entrada("retention.ms", "7776000000")], 0),
        (TOPICO, [_entrada("cleanup.policy", "compact")], 0),
    )

    topicos = await servicio.listar_topicos()

    assert [t["nombre"] for t in topicos] == ["demo.admin.v1", "espacios.historial.v1"]
    assert [t["protegido"] for t in topicos] == [False, True]
    assert topicos[0]["configuracion"] == {
        "retention.ms": None,
        "cleanup.policy": "compact",
        "min.insync.replicas": None,
    }
    admin.close.assert_awaited_once()


async def test_listar_sin_topicos_no_pide_configuracion(admin):
    admin.describe_topics.return_value = [_topico("__consumer_offsets", interno=True)]
    assert await servicio.listar_topicos() == []
    admin.describe_configs.assert_not_awaited()


async def test_kafka_caido_responde_503_y_cierra_el_cliente(admin):
    admin.start.side_effect = KafkaConnectionError()
    with pytest.raises(KafkaAdminException) as error:
        await servicio.listar_topicos()
    assert error.value.estado == 503
    admin.close.assert_awaited_once()


# --- Crear --------------------------------------------------------------------


async def test_crear_envia_configuracion_y_devuelve_el_topico(admin):
    admin.create_topics.return_value = SimpleNamespace(topic_errors=[(TOPICO, 0, None)])

    topico = await servicio.crear_topico(
        CrearTopicoRequest(nombre=TOPICO, retencion_ms=86400000, min_insync_replicas=2)
    )

    nuevo = admin.create_topics.await_args.args[0][0]
    assert (nuevo.name, nuevo.num_partitions, nuevo.replication_factor) == (TOPICO, 3, 3)
    assert nuevo.topic_configs == {"retention.ms": "86400000", "min.insync.replicas": "2"}
    assert topico["configuracion"]["retention.ms"] == "86400000"


@pytest.mark.parametrize(
    ("codigo", "mensaje", "estado"),
    [(36, "Topic already exists.", 409), (40, None, 400)],
)
async def test_crear_traduce_el_error_del_broker(admin, codigo, mensaje, estado):
    admin.create_topics.return_value = SimpleNamespace(topic_errors=[(TOPICO, codigo, mensaje)])
    with pytest.raises(KafkaAdminException) as error:
        await servicio.crear_topico(CrearTopicoRequest(nombre=TOPICO))
    assert error.value.estado == estado
    assert (mensaje or "INVALID_CONFIG") in str(error.value)


async def test_crear_espera_a_que_la_metadata_conozca_el_topico(admin):
    admin.create_topics.return_value = SimpleNamespace(topic_errors=[(TOPICO, 0, None)])
    admin.describe_topics.side_effect = [
        [_topico(TOPICO, error=3)],
        [_topico(TOPICO, error=3)],
        [_topico(TOPICO)],
    ]
    with patch.object(servicio.asyncio, "sleep", AsyncMock()) as espera:
        topico = await servicio.crear_topico(CrearTopicoRequest(nombre=TOPICO))
    assert topico["nombre"] == TOPICO
    assert espera.await_count == 2


async def test_crear_se_rinde_si_la_metadata_nunca_lo_conoce(admin):
    admin.create_topics.return_value = SimpleNamespace(topic_errors=[(TOPICO, 0, None)])
    admin.describe_topics.return_value = [_topico(TOPICO, error=3)]
    with patch.object(servicio.asyncio, "sleep", AsyncMock()):
        with pytest.raises(KafkaAdminException) as error:
            await servicio.crear_topico(CrearTopicoRequest(nombre=TOPICO))
    assert error.value.estado == 404
    assert admin.describe_topics.await_count == servicio._INTENTOS_METADATA


# --- Modificar ----------------------------------------------------------------


async def test_modificar_conserva_los_demas_overrides(admin):
    # AlterConfigs reemplaza todo: min.insync.replicas (override) debe viajar igual;
    # segment.ms es default del broker (fuente 5) y no se convierte en override.
    admin.describe_configs.return_value = _configs(
        (
            TOPICO,
            [
                _entrada("retention.ms", "86400000"),
                _entrada("min.insync.replicas", "2"),
                _entrada("segment.ms", "604800000", fuente=5),
            ],
            0,
        )
    )
    admin.alter_configs.return_value = [SimpleNamespace(resources=[(0, None, 2, TOPICO)])]

    await servicio.modificar_configuracion(
        TOPICO, ActualizarConfiguracionRequest(retencion_ms=3600000)
    )

    recurso = admin.alter_configs.await_args.args[0][0]
    assert recurso.name == TOPICO
    assert recurso.configs == {"retention.ms": "3600000", "min.insync.replicas": "2"}


@pytest.mark.parametrize(("isr", "permitido"), [(3, True), (4, False)])
async def test_modificar_isr_frente_al_factor_de_replicacion(admin, isr, permitido):
    admin.alter_configs.return_value = [SimpleNamespace(resources=[(0, None, 2, TOPICO)])]
    # El DTO limita a 3 brokers; aquí se prueba la regla del servicio con un factor 3.
    datos = ActualizarConfiguracionRequest.model_construct(
        retencion_ms=None, cleanup_policy=None, min_insync_replicas=isr
    )
    if permitido:
        await servicio.modificar_configuracion(TOPICO, datos)
        admin.alter_configs.assert_awaited_once()
    else:
        with pytest.raises(KafkaAdminException) as error:
            await servicio.modificar_configuracion(TOPICO, datos)
        assert error.value.estado == 400
        admin.alter_configs.assert_not_awaited()


async def test_modificar_topico_inexistente_es_404(admin):
    admin.describe_topics.return_value = [_topico("no.existe", error=3)]
    with pytest.raises(KafkaAdminException) as error:
        await servicio.modificar_configuracion(
            "no.existe", ActualizarConfiguracionRequest(retencion_ms=1000)
        )
    assert error.value.estado == 404
    admin.alter_configs.assert_not_awaited()


async def test_modificar_rechazado_por_el_broker_es_400(admin):
    admin.alter_configs.return_value = [
        SimpleNamespace(resources=[(40, "Invalid value -5 for retention.ms", 2, TOPICO)])
    ]
    with pytest.raises(KafkaAdminException) as error:
        await servicio.modificar_configuracion(
            TOPICO, ActualizarConfiguracionRequest(cleanup_policy="compact")
        )
    assert error.value.estado == 400
    assert "Invalid value" in str(error.value)


# --- Eliminar -----------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre", ["espacios.historial.v1", "espacios.alertas.v1", "__consumer_offsets"]
)
async def test_eliminar_protegido_es_409_sin_llegar_a_kafka(admin, nombre):
    with pytest.raises(KafkaAdminException) as error:
        await servicio.eliminar_topico(nombre)
    assert error.value.estado == 409
    admin.start.assert_not_awaited()


@pytest.mark.parametrize(("codigo", "estado"), [(0, None), (3, 404)])
async def test_eliminar_topico_normal(admin, codigo, estado):
    admin.delete_topics.return_value = SimpleNamespace(topic_error_codes=[(TOPICO, codigo)])
    if estado is None:
        await servicio.eliminar_topico(TOPICO)
    else:
        with pytest.raises(KafkaAdminException) as error:
            await servicio.eliminar_topico(TOPICO)
        assert error.value.estado == estado
    admin.delete_topics.assert_awaited_once_with([TOPICO])


# --- Consumer groups ----------------------------------------------------------


async def test_consumer_groups_calcula_lag_e_ignora_topicos_eliminados(admin):
    p0, p1 = TopicPartition("espacios.historial.v1", 0), TopicPartition("espacios.historial.v1", 1)
    huerfana = TopicPartition("ya.no.existe", 0)
    admin.list_topics.return_value = ["espacios.historial.v1"]
    admin.list_consumer_groups.return_value = [("grupo-b", "consumer"), ("grupo-a", "consumer")]
    admin.list_consumer_group_offsets.side_effect = lambda grupo: {
        "grupo-a": {p0: SimpleNamespace(offset=10), p1: SimpleNamespace(offset=4)},
        "grupo-b": {huerfana: SimpleNamespace(offset=1)},
    }[grupo]
    consumidor = MagicMock(start=AsyncMock(), stop=AsyncMock())
    consumidor.end_offsets = AsyncMock(return_value={p0: 12, p1: 4})

    with patch.object(servicio, "AIOKafkaConsumer", return_value=consumidor):
        grupos = await servicio.listar_consumer_groups()

    assert [g["grupo"] for g in grupos] == ["grupo-a", "grupo-b"]
    assert grupos[0]["lag_total"] == 2
    assert [(p["particion"], p["lag"]) for p in grupos[0]["particiones"]] == [(0, 2), (1, 0)]
    assert grupos[1] == {"grupo": "grupo-b", "lag_total": 0, "particiones": []}
    consumidor.end_offsets.assert_awaited_once_with([p0, p1])
    consumidor.stop.assert_awaited_once()


async def test_consumer_groups_sin_offsets_no_abre_consumidor(admin):
    admin.list_topics.return_value = []
    admin.list_consumer_groups.return_value = []
    with patch.object(servicio, "AIOKafkaConsumer") as clase:
        assert await servicio.listar_consumer_groups() == []
    clase.assert_not_called()


# --- DTO ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "datos",
    [
        {"nombre": "con espacio"},
        {"nombre": "x" * 250},
        {"nombre": TOPICO, "factor_replicacion": 1, "min_insync_replicas": 2},
        {"nombre": TOPICO, "factor_replicacion": 4},
        {"nombre": TOPICO, "cleanup_policy": "borrar"},
    ],
)
def test_crear_request_invalido(datos):
    with pytest.raises(ValidationError):
        CrearTopicoRequest(**datos)


def test_actualizar_request_exige_al_menos_un_campo():
    with pytest.raises(ValidationError):
        ActualizarConfiguracionRequest(retencion_ms=None)


# --- Endpoints ----------------------------------------------------------------

ADMIN = {"X-Usuario-Roles": "admin"}
DESCRIPCION = {
    "nombre": TOPICO,
    "particiones": 3,
    "factor_replicacion": 3,
    "protegido": False,
    "configuracion": {"retention.ms": "3600000"},
}
LLAMADAS = [
    ("GET", "/api/v1/kafka/topicos", None),
    ("POST", "/api/v1/kafka/topicos", {"nombre": TOPICO}),
    ("PATCH", f"/api/v1/kafka/topicos/{TOPICO}/configuracion", {"retencion_ms": 3600000}),
    ("DELETE", f"/api/v1/kafka/topicos/{TOPICO}", None),
    ("GET", "/api/v1/kafka/consumer-groups", None),
]


@pytest_asyncio.fixture
async def cliente():
    simulado = AsyncMock()
    simulado.listar_topicos.return_value = [DESCRIPCION]
    simulado.crear_topico.return_value = DESCRIPCION
    simulado.modificar_configuracion.return_value = DESCRIPCION
    simulado.eliminar_topico.return_value = None
    simulado.listar_consumer_groups.return_value = []
    with patch("app.api.v1.kafka_admin_router.kafka_admin_service", simulado):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, simulado


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), LLAMADAS)
@pytest.mark.parametrize("roles", ["conserje", "residente", ""])
async def test_endpoints_solo_admin(cliente, metodo, ruta, cuerpo, roles):
    c, simulado = cliente
    r = await c.request(metodo, ruta, json=cuerpo, headers={"X-Usuario-Roles": roles})
    assert r.status_code == 403
    assert simulado.method_calls == []


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "estado"),
    [(*llamada, estado) for llamada, estado in zip(LLAMADAS, [200, 201, 200, 204, 200])],
)
async def test_endpoints_con_admin(cliente, metodo, ruta, cuerpo, estado):
    c, _ = cliente
    r = await c.request(metodo, ruta, json=cuerpo, headers=ADMIN)
    assert r.status_code == estado


async def test_patch_pasa_nombre_y_campos(cliente):
    c, simulado = cliente
    await c.patch(
        f"/api/v1/kafka/topicos/{TOPICO}/configuracion",
        json={"cleanup_policy": "compact"},
        headers=ADMIN,
    )
    nombre, datos = simulado.modificar_configuracion.await_args.args
    assert nombre == TOPICO
    assert datos.cleanup_policy == "compact"


async def test_patch_sin_campos_es_422(cliente):
    c, simulado = cliente
    r = await c.patch(f"/api/v1/kafka/topicos/{TOPICO}/configuracion", json={}, headers=ADMIN)
    assert r.status_code == 422
    simulado.modificar_configuracion.assert_not_awaited()


async def test_error_del_servicio_sale_con_su_codigo(cliente):
    c, simulado = cliente
    simulado.eliminar_topico.side_effect = KafkaAdminException(409, "es del sistema")
    r = await c.delete("/api/v1/kafka/topicos/espacios.alertas.v1", headers=ADMIN)
    assert r.status_code == 409
    assert r.json() == {"detail": "es del sistema"}
