import json

import pytest

from app.events.eventos import EventoInvalido, leer_evento

BASE = {"event_id": "abc-123", "reserva_id": "42", "email": "residente@convivo.cl", "monto": 20000}


def test_lee_evento_snake_case():
    evento = leer_evento(json.dumps(BASE).encode())
    assert evento.event_id == "abc-123"
    assert evento.reserva_id == "42"
    assert evento.monto == 20000


def test_lee_evento_camel_case():
    datos = {"eventId": "x1", "reservaId": 7, "usuarioEmail": "a@b.cl"}
    evento = leer_evento(json.dumps(datos).encode())
    assert (evento.event_id, evento.reserva_id, evento.email) == ("x1", "7", "a@b.cl")


def test_json_roto_es_invalido():
    with pytest.raises(EventoInvalido):
        leer_evento(b"{no es json")


@pytest.mark.parametrize("campo", ["event_id", "reserva_id", "email"])
def test_falta_campo_obligatorio(campo):
    datos = {k: v for k, v in BASE.items() if k != campo}
    with pytest.raises(EventoInvalido):
        leer_evento(json.dumps(datos).encode())


def test_fechas_legibles():
    datos = dict(BASE, fecha_inicio="2026-10-24T18:00:00Z", fecha_fin="no-es-fecha")
    evento = leer_evento(json.dumps(datos).encode())
    assert evento.fecha_inicio == "24-10-2026 18:00"
    assert evento.fecha_fin == "no-es-fecha"
