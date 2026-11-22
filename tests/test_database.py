from app.config.database import motor


def test_motor_verifica_conexion_antes_de_usarla():
    # Sin pre-ping, la primera petición tras reiniciar Oracle se cuelga con una conexión muerta.
    assert motor.sync_engine.pool._pre_ping is True
