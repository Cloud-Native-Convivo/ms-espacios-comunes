"""Test de integración contra la base de datos real del proyecto (Oracle,
ver docker-compose.yml). No usa aiosqlite ni ningún motor propio de test:
reutiliza app.config.database (el mismo motor que usa la app).

No corre en la suite normal (`pytest tests/`, ver pyproject.toml
`-m "not integracion"`). Para correrlo con la base levantada:

    docker compose up -d oracle-espacios
    pytest -m integracion tests/test_idempotencia_repository_integracion.py

Si la base no está disponible, se salta automáticamente.
"""

import pytest
from sqlalchemy import text

from app.config.database import fabrica_sesiones, motor
from app.model.modelos import Base, Espacio
from app.repository.idempotencia_repository import EN_CURSO, NUEVO, reclamar

pytestmark = pytest.mark.integracion

PREFIJO_EVENT_ID = "evt-integracion-reclamar"
CONSUMIDOR = "test-integracion-worker"
NOMBRE_ESPACIO = "Integracion Test — reclamar no pierde trabajo pendiente"


@pytest.fixture
async def sesion_real():
    try:
        async with motor.begin() as conexion:
            await conexion.run_sync(Base.metadata.create_all)
    except Exception as error:
        pytest.skip(f"Base de datos no disponible para el test de integración: {error}")

    async with fabrica_sesiones() as sesion:
        yield sesion
        await sesion.rollback()
        await sesion.execute(text("DELETE FROM eventos_procesados WHERE consumidor = :c"), {"c": CONSUMIDOR})
        await sesion.execute(text("DELETE FROM espacios WHERE nombre = :n"), {"n": NOMBRE_ESPACIO})
        await sesion.commit()


async def test_reclamar_duplicado_no_pierde_otro_trabajo_pendiente_en_la_misma_sesion(sesion_real):
    event_id = f"{PREFIJO_EVENT_ID}-1"

    # Primera copia: gana la reserva del event_id y la deja commiteada.
    resultado_1 = await reclamar(sesion_real, event_id, CONSUMIDOR)
    assert resultado_1 == NUEVO

    # Trabajo pendiente en la MISMA sesión, todavía sin commitear.
    espacio = Espacio(condominio_id=1, nombre=NOMBRE_ESPACIO, capacidad=1, estado="activo")
    sesion_real.add(espacio)
    await sesion_real.flush()
    assert espacio.id is not None  # el INSERT ya corrió, solo falta el commit

    # Segunda copia del mismo evento: IntegrityError real de Oracle sobre la
    # llave primaria. Con SAVEPOINT, esto NO debe deshacer `espacio`.
    resultado_2 = await reclamar(sesion_real, event_id, CONSUMIDOR)
    assert resultado_2 == EN_CURSO

    # El espacio pendiente sigue vivo en la sesión y se puede commitear.
    await sesion_real.commit()
    assert espacio.id is not None
