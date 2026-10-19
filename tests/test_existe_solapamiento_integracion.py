"""Test de integración contra Oracle real: existe_solapamiento() compara
expira_en (UTC, desde Task E9) contra func.now() (CURRENT_TIMESTAMP, zona de
la SESIÓN de Oracle — no UTC). Ver conversación: en este entorno la sesión
está 3 horas detrás de UTC, así que una reserva recién expirada en UTC
todavía se leía como "no expirada" por hasta 3 horas.

No usa el motor global (mismo problema de tests/conftest.py que el otro test
de integración): construye su propio engine desde .env.

No corre en la suite normal (`-m "not integracion"` en pyproject.toml).
"""

import datetime

import pytest
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.model.modelos import Base, Espacio, Reserva
from app.repository import reserva_repository
from app.util.tiempo import ahora_utc

pytestmark = pytest.mark.integracion

NOMBRE_ESPACIO = "Integracion Test — solapamiento UTC"


def _url_desde_env_real() -> str:
    valores = dotenv_values(".env")
    usuario = valores.get("DB_USERNAME", "admin")
    clave = valores.get("DB_PASSWORD", "")
    host = valores.get("DB_HOST", "localhost")
    puerto = valores.get("DB_PORT", "1521")
    nombre = valores.get("DB_NAME", "freepdb1")
    return f"oracle+oracledb://{usuario}:{clave}@{host}:{puerto}/?service_name={nombre}"


@pytest.fixture
async def sesion_real():
    motor = create_async_engine(_url_desde_env_real())
    try:
        async with motor.begin() as conexion:
            await conexion.run_sync(Base.metadata.create_all)
    except Exception as error:
        await motor.dispose()
        pytest.skip(f"Base de datos no disponible para el test de integración: {error}")

    fabrica_sesiones = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica_sesiones() as sesion:
        espacio = Espacio(condominio_id=1, nombre=NOMBRE_ESPACIO, capacidad=1, estado="activo")
        sesion.add(espacio)
        await sesion.flush()
        espacio_id = espacio.id  # capturado ANTES del rollback: después queda expirado
        yield sesion, espacio_id
        await sesion.rollback()
        await sesion.execute(
            __import__("sqlalchemy").text("DELETE FROM reservas WHERE espacio_id = :e"), {"e": espacio_id}
        )
        await sesion.execute(
            __import__("sqlalchemy").text("DELETE FROM espacios WHERE id = :e"), {"e": espacio_id}
        )
        await sesion.commit()
    await motor.dispose()


async def test_reserva_con_expira_en_vencido_en_utc_no_bloquea_el_horario(sesion_real):
    sesion, espacio_id = sesion_real
    reserva_vencida = Reserva(
        espacio_id=espacio_id,
        usuario_sub="u-vencida",
        fecha_inicio=datetime.datetime(2026, 10, 18, 10, 0, 0),
        fecha_fin=datetime.datetime(2026, 10, 18, 11, 0, 0),
        estado="pendiente_pago",
        monto_total=1000.0,
        expira_en=ahora_utc() - datetime.timedelta(minutes=1),
    )
    sesion.add(reserva_vencida)
    await sesion.commit()

    hay_solapamiento = await reserva_repository.existe_solapamiento(
        sesion,
        espacio_id,
        datetime.datetime(2026, 10, 18, 10, 0, 0),
        datetime.datetime(2026, 10, 18, 11, 0, 0),
        ahora_utc(),
    )

    assert hay_solapamiento is False


async def test_reserva_con_expira_en_vigente_si_bloquea_el_horario(sesion_real):
    sesion, espacio_id = sesion_real
    reserva_vigente = Reserva(
        espacio_id=espacio_id,
        usuario_sub="u-vigente",
        fecha_inicio=datetime.datetime(2026, 10, 18, 12, 0, 0),
        fecha_fin=datetime.datetime(2026, 10, 18, 13, 0, 0),
        estado="pendiente_pago",
        monto_total=1000.0,
        expira_en=ahora_utc() + datetime.timedelta(minutes=10),
    )
    sesion.add(reserva_vigente)
    await sesion.commit()

    hay_solapamiento = await reserva_repository.existe_solapamiento(
        sesion,
        espacio_id,
        datetime.datetime(2026, 10, 18, 12, 0, 0),
        datetime.datetime(2026, 10, 18, 13, 0, 0),
        ahora_utc(),
    )

    assert hay_solapamiento is True
