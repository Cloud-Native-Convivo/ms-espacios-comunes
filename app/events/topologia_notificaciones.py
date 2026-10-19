"""Declaración de las colas de notificación (correo) y PDF, puerto del
prototipo prototipo-rabbit-residente/topologia.py. Reutiliza los mismos
exchanges que ya declara ms-espacios-comunes — nunca cambiar su tipo/durable
o RabbitMQ rechaza con PRECONDITION_FAILED.

    espacios_events (topic)
      ├── rk reserva_espacio_creada ─┐
      ├── rk reserva_expirada ───────┴─► notificaciones_queue ──(falla)──► espacios_dlx ──► notificaciones_dlq
      └── rk reserva_confirmada ───────► reserva_pdf_queue    ──(falla)──► espacios_dlx ──► reserva_pdf_dlq
"""

import aio_pika

EXCHANGE_EVENTOS = "espacios_events"
EXCHANGE_DLX = "espacios_dlx"

COLA_NOTIFICACIONES = "notificaciones_queue"
COLA_NOTIFICACIONES_DLQ = "notificaciones_dlq"
RK_RESERVA_CREADA = "reserva_espacio_creada"
RK_RESERVA_EXPIRADA = "reserva_expirada"

COLA_PDF = "reserva_pdf_queue"
COLA_PDF_DLQ = "reserva_pdf_dlq"
RK_RESERVA_CONFIRMADA = "reserva_confirmada"


async def declarar_topologia_notificaciones(
    canal: aio_pika.abc.AbstractChannel,
) -> dict[str, aio_pika.abc.AbstractQueue]:
    exchange_eventos = await canal.declare_exchange(
        EXCHANGE_EVENTOS, aio_pika.ExchangeType.TOPIC, durable=True
    )
    exchange_dlx = await canal.declare_exchange(
        EXCHANGE_DLX, aio_pika.ExchangeType.DIRECT, durable=True
    )

    colas: dict[str, aio_pika.abc.AbstractQueue] = {}
    definiciones = [
        (COLA_NOTIFICACIONES, COLA_NOTIFICACIONES_DLQ, [RK_RESERVA_CREADA, RK_RESERVA_EXPIRADA]),
        (COLA_PDF, COLA_PDF_DLQ, [RK_RESERVA_CONFIRMADA]),
    ]

    for nombre_cola, nombre_dlq, routing_keys in definiciones:
        dlq = await canal.declare_queue(nombre_dlq, durable=True)
        await dlq.bind(exchange_dlx, routing_key=nombre_dlq)

        cola = await canal.declare_queue(
            nombre_cola,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_DLX,
                "x-dead-letter-routing-key": nombre_dlq,
            },
        )
        for routing_key in routing_keys:
            await cola.bind(exchange_eventos, routing_key=routing_key)

        colas[nombre_cola] = cola
        colas[nombre_dlq] = dlq

    return colas
