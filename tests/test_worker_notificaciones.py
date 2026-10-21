import json

import pytest

from app.events.eventos import EventoInvalido, leer_evento
from app.events.worker_notificaciones import armar_correo

BASE = {"event_id": "e1", "reserva_id": "42", "email": "a@b.cl", "monto": 20000}


def test_correo_en_proceso():
    evento = leer_evento(json.dumps(dict(BASE, tipo="reserva_espacio_creada")).encode())
    asunto, cuerpo = armar_correo(evento)
    assert "EN PROCESO" in cuerpo
    assert "42" in asunto


def test_correo_expirada():
    evento = leer_evento(json.dumps(dict(BASE, tipo="reserva_expirada")).encode())
    asunto, cuerpo = armar_correo(evento)
    assert "expiró" in asunto
    assert "15 minutos" in cuerpo


def test_tipo_desconocido_es_invalido():
    evento = leer_evento(json.dumps(dict(BASE, tipo="algo_raro")).encode())
    with pytest.raises(EventoInvalido):
        armar_correo(evento)
