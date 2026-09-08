import os
from unittest.mock import Mock

import httpx
import pytest

from app.config.settings import cargar_configuracion_remota


@pytest.fixture(autouse=True)
def limpiar_env(monkeypatch):
    for variable in ("DB_HOST", "PUERTO", "MODO_DEBUG", "CORS_ORIGINS"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr("app.config.settings.load_dotenv", Mock())


def test_esquema_no_permitido_no_hace_peticion(monkeypatch):
    llamada = Mock()
    monkeypatch.setattr("app.config.settings.httpx.get", llamada)

    cargar_configuracion_remota(url_base="file:///etc/passwd")

    llamada.assert_not_called()


def test_config_server_caido_no_lanza_excepcion(monkeypatch):
    def falla(*args, **kwargs):
        raise httpx.ConnectError("sin conexión")

    monkeypatch.setattr("app.config.settings.httpx.get", falla)

    cargar_configuracion_remota(url_base="http://localhost:8888")  # no debe lanzar


def test_completa_solo_variables_ausentes(monkeypatch):
    monkeypatch.setenv("DB_HOST", "ya-definido-local")

    respuesta = Mock()
    respuesta.raise_for_status = Mock()
    respuesta.json.return_value = {
        "propertySources": [
            {
                "source": {
                    "db.host": "host-remoto",
                    "server.port": 9999,
                    "clave.no-mapeada": "se-ignora",
                }
            }
        ]
    }
    monkeypatch.setattr("app.config.settings.httpx.get", Mock(return_value=respuesta))

    cargar_configuracion_remota(url_base="http://localhost:8888")

    assert os.environ["DB_HOST"] == "ya-definido-local"  # no la pisa
    assert os.environ["PUERTO"] == "9999"  # completa la ausente


def test_parsear_cors_origins_desde_string(monkeypatch):
    from app.config.settings import Settings

    monkeypatch.setenv("CORS_ORIGINS", "http://app.convivo.cl, https://admin.convivo.cl ")
    config = Settings()
    assert config.cors_origins == ["http://app.convivo.cl", "https://admin.convivo.cl"]


def test_cors_origins_por_defecto():
    from app.config.settings import Settings

    config = Settings()
    assert "http://localhost:4200" in config.cors_origins
    assert "http://127.0.0.1:4200" in config.cors_origins


def test_parsear_cors_origins_desde_json_array(monkeypatch):
    from app.config.settings import Settings

    monkeypatch.setenv("CORS_ORIGINS", '["http://app.convivo.cl", "https://admin.convivo.cl"]')
    config = Settings()
    assert config.cors_origins == ["http://app.convivo.cl", "https://admin.convivo.cl"]


def test_parsear_cors_origins_desde_string_vacio(monkeypatch):
    from app.config.settings import Settings

    monkeypatch.setenv("CORS_ORIGINS", "")
    config = Settings()
    assert config.cors_origins == []
