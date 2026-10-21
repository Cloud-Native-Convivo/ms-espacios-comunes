from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.model.evento_procesado import EventoProcesado
from app.repository.idempotencia_repository import (
    COMPLETADO,
    EN_CURSO,
    NUEVO,
    completar,
    liberar,
    reclamar,
)


def _savepoint(lanza: Exception | None = None):
    """Simula sesion.begin_nested(): si `lanza` no es None, __aexit__ deja
    que la excepcion se propague (como el SAVEPOINT real de SQLAlchemy)."""
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=None)
    contexto.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=contexto)


@pytest.fixture
def mock_sesion():
    sesion = AsyncMock()
    sesion.begin_nested = _savepoint()
    return sesion


async def test_reclamar_nuevo_evento(mock_sesion):
    resultado = await reclamar(mock_sesion, "e1", "worker_a")
    assert resultado == NUEVO
    mock_sesion.add.assert_called_once()
    mock_sesion.commit.assert_awaited_once()


async def test_reclamar_evento_en_curso_sin_retomar(mock_sesion):
    mock_sesion.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    mock_sesion.get = AsyncMock(
        return_value=EventoProcesado(event_id="e1", consumidor="worker_a", estado=EN_CURSO)
    )

    resultado = await reclamar(mock_sesion, "e1", "worker_a")

    assert resultado == EN_CURSO


async def test_reclamar_evento_en_curso_con_retomar(mock_sesion):
    mock_sesion.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    mock_sesion.get = AsyncMock(
        return_value=EventoProcesado(event_id="e2", consumidor="worker_a", estado=EN_CURSO)
    )

    resultado = await reclamar(mock_sesion, "e2", "worker_a", retomar_en_curso=True)

    assert resultado == NUEVO


async def test_reclamar_evento_completado_nunca_se_retoma(mock_sesion):
    mock_sesion.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    mock_sesion.get = AsyncMock(
        return_value=EventoProcesado(event_id="e3", consumidor="worker_a", estado=COMPLETADO)
    )

    resultado = await reclamar(mock_sesion, "e3", "worker_a", retomar_en_curso=True)

    assert resultado == COMPLETADO


async def test_reclamar_duplicado_usa_savepoint_y_no_hace_rollback_de_toda_la_sesion(mock_sesion):
    """El rollback de un duplicado debe deshacer solo el INSERT fallido (SAVEPOINT),
    nunca toda la sesión — si no, se perdería cualquier otro trabajo pendiente
    en la misma sesión (ver consumidor_notificaciones_base.py, que reusa la
    sesión para completar/liberar después de reclamar)."""
    mock_sesion.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    mock_sesion.get = AsyncMock(
        return_value=EventoProcesado(event_id="e4", consumidor="worker_a", estado=EN_CURSO)
    )

    await reclamar(mock_sesion, "e4", "worker_a")

    mock_sesion.begin_nested.assert_called_once()
    mock_sesion.rollback.assert_not_awaited()


async def test_completar_marca_estado(mock_sesion):
    registro = EventoProcesado(event_id="e1", consumidor="w", estado=EN_CURSO)
    mock_sesion.get = AsyncMock(return_value=registro)

    await completar(mock_sesion, "e1", "w")

    assert registro.estado == COMPLETADO
    mock_sesion.commit.assert_awaited_once()


async def test_liberar_borra_si_en_curso(mock_sesion):
    registro = EventoProcesado(event_id="e1", consumidor="w", estado=EN_CURSO)
    mock_sesion.get = AsyncMock(return_value=registro)

    await liberar(mock_sesion, "e1", "w")

    mock_sesion.delete.assert_awaited_once_with(registro)
    mock_sesion.commit.assert_awaited_once()


async def test_liberar_no_hace_nada_si_ya_completado(mock_sesion):
    registro = EventoProcesado(event_id="e1", consumidor="w", estado=COMPLETADO)
    mock_sesion.get = AsyncMock(return_value=registro)

    await liberar(mock_sesion, "e1", "w")

    mock_sesion.delete.assert_not_awaited()
