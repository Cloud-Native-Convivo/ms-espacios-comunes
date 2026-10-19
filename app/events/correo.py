"""Envío de correos por SMTP (en local, a Mailpit). smtplib es bloqueante:
se ejecuta en un hilo aparte con asyncio.to_thread para no bloquear el loop
de aio_pika.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from app.config.settings import settings


def _enviar_sync(destinatario: str, asunto: str, cuerpo: str, adjunto: tuple[str, bytes] | None) -> None:
    mensaje = EmailMessage()
    mensaje["From"] = settings.mail_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)

    if adjunto is not None:
        nombre_archivo, contenido = adjunto
        mensaje.add_attachment(
            contenido, maintype="application", subtype="pdf", filename=nombre_archivo
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as servidor:
        # Mailpit no usa TLS ni login; Amazon SES (puerto 587) exige ambos.
        if settings.smtp_usuario:
            servidor.starttls()
            servidor.login(settings.smtp_usuario, settings.smtp_clave)
        servidor.send_message(mensaje)


async def enviar_correo(
    destinatario: str, asunto: str, cuerpo: str, adjunto: tuple[str, bytes] | None = None
) -> None:
    await asyncio.to_thread(_enviar_sync, destinatario, asunto, cuerpo, adjunto)
