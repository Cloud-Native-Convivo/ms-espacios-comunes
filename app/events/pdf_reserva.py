"""Genera el comprobante de reserva en PDF (en memoria, como bytes)."""

import datetime
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.events.eventos import EventoReserva


def generar_pdf_reserva(evento: EventoReserva) -> bytes:
    buffer = io.BytesIO()
    hoja = canvas.Canvas(buffer, pagesize=A4)
    ancho, alto = A4

    hoja.setFillColor(colors.HexColor("#0F6E56"))
    hoja.rect(0, alto - 3 * cm, ancho, 3 * cm, stroke=0, fill=1)
    hoja.setFillColor(colors.white)
    hoja.setFont("Helvetica-Bold", 20)
    hoja.drawString(2 * cm, alto - 1.8 * cm, "Convivo")
    hoja.setFont("Helvetica", 11)
    hoja.drawString(2 * cm, alto - 2.5 * cm, "Comprobante de reserva de espacio común")

    hoja.setFillColor(colors.black)
    filas = [
        ("N° de reserva", evento.reserva_id),
        ("Residente", evento.nombre_residente),
        ("Correo", evento.email),
        ("Espacio", evento.espacio),
        ("Inicio", evento.fecha_inicio),
        ("Término", evento.fecha_fin),
        ("Monto pagado", f"${evento.monto:,.0f}".replace(",", ".")),
        ("Estado", "Confirmada"),
    ]
    y = alto - 5 * cm
    for etiqueta, valor in filas:
        hoja.setFont("Helvetica-Bold", 11)
        hoja.drawString(2 * cm, y, etiqueta)
        hoja.setFont("Helvetica", 11)
        hoja.drawString(7 * cm, y, str(valor))
        hoja.setStrokeColor(colors.HexColor("#DDDDDD"))
        hoja.line(2 * cm, y - 0.3 * cm, ancho - 2 * cm, y - 0.3 * cm)
        y -= 1 * cm

    hoja.setFont("Helvetica-Oblique", 9)
    hoja.setFillColor(colors.grey)
    emitido = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    hoja.drawString(2 * cm, 2 * cm, f"Emitido el {emitido} · ID de evento {evento.event_id}")

    hoja.showPage()
    hoja.save()
    return buffer.getvalue()
