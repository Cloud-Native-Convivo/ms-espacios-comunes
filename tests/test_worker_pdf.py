import json
from unittest.mock import AsyncMock, patch

from app.events.eventos import leer_evento
from app.events.worker_pdf import manejar_confirmacion

BASE = {"event_id": "e1", "reserva_id": "42", "email": "a@b.cl", "monto": 20000, "tipo": "reserva_confirmada"}


async def test_manejar_confirmacion_genera_pdf_y_envia_correo_con_adjunto(tmp_path, monkeypatch):
    monkeypatch.setattr("app.events.worker_pdf.CARPETA_PDFS", str(tmp_path))
    evento = leer_evento(json.dumps(BASE).encode())
    with patch("app.events.worker_pdf.enviar_correo", new=AsyncMock()) as enviar:
        await manejar_confirmacion(evento)
    enviar.assert_awaited_once()
    args, kwargs = enviar.await_args
    assert args[0] == "a@b.cl"
    assert kwargs["adjunto"][0] == "reserva_42.pdf"
    assert kwargs["adjunto"][1].startswith(b"%PDF")
