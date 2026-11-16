import datetime
import json

from app.model.modelos import Espacio, Reserva
from app.service.reserva_service import payload_reserva


def _reserva(espacio_id: int = 7) -> Reserva:
    return Reserva(
        id=42,
        espacio_id=espacio_id,
        usuario_sub="sub-1",
        fecha_inicio=datetime.datetime(2026, 12, 10, 18, 30),
        fecha_fin=datetime.datetime(2026, 12, 10, 20, 30),
        estado="pendiente_pago",
        monto_total=10000,
    )


def test_el_concepto_del_gasto_lleva_el_espacio_y_la_fecha():
    espacio = Espacio(id=7, nombre="Quincho Norte", condominio_id=1, capacidad=10, tarifa_hora=5000)
    datos = json.loads(payload_reserva(_reserva(), espacio, "reserva_espacio_creada", "evt-1"))

    assert datos["concepto"] == "Reserva Quincho Norte el 10/12/2026 a las 18:30"


def test_sin_espacio_cargado_el_concepto_usa_su_identificador():
    datos = json.loads(payload_reserva(_reserva(espacio_id=7), None, "reserva_espacio_creada", "evt-1"))

    assert datos["concepto"] == "Reserva 7 el 10/12/2026 a las 18:30"
