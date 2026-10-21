from app.events.eventos import EventoReserva
from app.events.pdf_reserva import generar_pdf_reserva


def test_pdf_generado_es_un_pdf_valido():
    evento = EventoReserva(
        event_id="e1",
        tipo="reserva_confirmada",
        reserva_id="42",
        email="residente@convivo.cl",
        nombre_residente="residente",
        espacio="Quincho",
        fecha_inicio="24-10-2026 18:00",
        fecha_fin="24-10-2026 20:00",
        monto=20000.0,
    )
    pdf = generar_pdf_reserva(evento)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
