from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import main


async def _tarea_inmediata():
    return None


def _motor(falla: bool):
    conexion = AsyncMock()
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(side_effect=RuntimeError("oracle caido") if falla else None, return_value=conexion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    motor = MagicMock()
    motor.begin = MagicMock(return_value=contexto)
    return motor, conexion


@pytest.mark.parametrize("eureka_falla", [False, True])
async def test_lifespan_registra_eureka_crea_tablas_y_detiene_tareas(eureka_falla):
    motor, conexion = _motor(falla=False)
    eureka = MagicMock()
    eureka.init_async = AsyncMock(side_effect=RuntimeError("sin eureka") if eureka_falla else None)
    eureka.stop_async = AsyncMock(side_effect=RuntimeError("ya detenido") if eureka_falla else None)
    with (
        patch.object(main.settings, "eureka_url", "http://eureka"),
        patch.object(main, "eureka_client", eureka),
        patch.object(main, "motor", motor),
        patch.object(main, "relay_outbox", _tarea_inmediata),
        patch.object(main, "consumidor_compensacion", _tarea_inmediata),
        patch.object(main, "worker_expiracion", _tarea_inmediata),
    ):
        async with main.lifespan(main.app):
            pass

    eureka.init_async.assert_awaited_once()
    eureka.stop_async.assert_awaited_once()
    conexion.run_sync.assert_awaited_once()


async def test_lifespan_sin_eureka_y_con_base_caida_igual_arranca():
    motor, _ = _motor(falla=True)
    eureka = MagicMock()
    with (
        patch.object(main.settings, "eureka_url", ""),
        patch.object(main, "eureka_client", eureka),
        patch.object(main, "motor", motor),
        patch.object(main, "relay_outbox", _tarea_inmediata),
        patch.object(main, "consumidor_compensacion", _tarea_inmediata),
        patch.object(main, "worker_expiracion", _tarea_inmediata),
    ):
        async with main.lifespan(main.app):
            pass
    eureka.init_async.assert_not_called()
