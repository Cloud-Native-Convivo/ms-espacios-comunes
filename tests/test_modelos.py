from app.model.modelos import Reserva


def test_reserva_acepta_usuario_email_opcional():
    reserva = Reserva(
        espacio_id=1,
        usuario_sub="sub-1",
        fecha_inicio="2026-10-15T10:00:00",
        fecha_fin="2026-10-15T11:00:00",
        usuario_email="ana@convivo.cl",
    )
    assert reserva.usuario_email == "ana@convivo.cl"


def test_reserva_usuario_email_es_opcional():
    reserva = Reserva(
        espacio_id=1,
        usuario_sub="sub-1",
        fecha_inicio="2026-10-15T10:00:00",
        fecha_fin="2026-10-15T11:00:00",
    )
    assert reserva.usuario_email is None
