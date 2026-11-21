import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaProducer
from pydantic import ValidationError

from app.dto.kafka_eventos import (
    TOPICO_ALERTAS,
    TOPICO_HISTORIAL,
    AlertaEspacioV1,
    DatosEventoEspacio,
    EventoEspacioV1,
)
from app.events.kafka_productor import (
    crear_productor_kafka,
    opciones_productor,
    serializar_clave,
    serializar_valor,
)


def _evento(**cambios) -> EventoEspacioV1:
    base = {"tipo": "RESERVA_CREADA", "condominio_id": 1, "espacio_id": 7, "reserva_id": 42}
    return EventoEspacioV1(**(base | cambios))


def _alerta(**cambios) -> AlertaEspacioV1:
    base = {
        "tipo": "RESERVA_POR_EXPIRAR",
        "severidad": "advertencia",
        "condominio_id": 3,
        "espacio_id": 7,
        "mensaje": "Tu reserva expira en 1 hora",
    }
    return AlertaEspacioV1(**(base | cambios))


def test_nombres_de_topicos():
    assert TOPICO_HISTORIAL == "espacios.historial.v1"
    assert TOPICO_ALERTAS == "espacios.alertas.v1"


def test_evento_completa_defaults_y_clave_es_espacio_id():
    evento = _evento()
    assert evento.version == 1
    assert evento.ocurrido_en.tzinfo is UTC
    assert evento.datos == DatosEventoEspacio()
    assert evento.clave == "7"


def test_evento_normaliza_fecha_a_utc():
    chile = timezone(timedelta(hours=-3))
    evento = _evento(ocurrido_en=datetime(2026, 11, 20, 21, 0, tzinfo=chile))
    assert evento.ocurrido_en == datetime(2026, 11, 21, 0, 0, tzinfo=UTC)
    assert evento.ocurrido_en.utcoffset() == timedelta(0)


def test_evento_rechaza_fecha_sin_zona_horaria():
    with pytest.raises(ValidationError):
        _evento(ocurrido_en=datetime(2026, 11, 20, 21, 0))


@pytest.mark.parametrize(
    "cambio",
    [
        {"tipo": "RESERVA_PAGADA"},
        {"version": 2},
        {"unidad_id": 5},
        {"espacio_id": "no-es-numero"},
    ],
)
def test_evento_rechaza_datos_fuera_de_contrato(cambio):
    with pytest.raises(ValidationError):
        _evento(**cambio)


def test_evento_es_inmutable():
    evento = _evento()
    with pytest.raises(ValidationError):
        evento.espacio_id = 8


def test_evento_ida_y_vuelta_json():
    evento = _evento(
        actor_sub="sub-123",
        datos={"estado_anterior": "pendiente", "estado_nuevo": "confirmada", "monto": 15000.0},
    )
    leido = EventoEspacioV1.model_validate_json(serializar_valor(evento))
    assert leido == evento


def test_alerta_clave_es_condominio_id():
    assert _alerta().clave == "3"


def test_alerta_acepta_origen_event_id():
    origen = uuid4()
    alerta = _alerta(origen_event_id=origen, destinatario_sub="sub-9", reserva_id=42)
    leida = AlertaEspacioV1.model_validate_json(serializar_valor(alerta))
    assert leida.origen_event_id == origen


@pytest.mark.parametrize(
    "cambio",
    [{"severidad": "critica"}, {"mensaje": ""}, {"tipo": "ESPACIO_CREADO"}],
)
def test_alerta_rechaza_datos_fuera_de_contrato(cambio):
    with pytest.raises(ValidationError):
        _alerta(**cambio)


def test_serializadores_producen_json_utf8():
    evento = _evento(datos={"estado_nuevo": "en_mantención"})
    cuerpo = json.loads(serializar_valor(evento).decode("utf-8"))
    assert cuerpo["tipo"] == "RESERVA_CREADA"
    assert cuerpo["event_id"] == str(evento.event_id)
    assert cuerpo["datos"]["estado_nuevo"] == "en_mantención"
    assert serializar_clave("7") == b"7"


def test_opciones_productor_garantizan_entrega():
    opciones = opciones_productor()
    assert opciones["acks"] == "all"
    assert opciones["enable_idempotence"] is True
    assert opciones["client_id"] == "ms-espacios-comunes"
    assert opciones["bootstrap_servers"]


async def test_crear_productor_no_conecta_y_acepta_las_opciones():
    # aiokafka valida en el constructor que la idempotencia vaya con acks=all.
    productor = crear_productor_kafka()
    assert isinstance(productor, AIOKafkaProducer)
