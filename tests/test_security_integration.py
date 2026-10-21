import pytest

from app.config.security_config import UsuarioContexto, normalizar_roles
from app.middleware.auth_roles import obtener_usuario_actual, requerir_roles


def test_auth_roles_reexport_contract():
    assert callable(obtener_usuario_actual)
    assert callable(requerir_roles)
    validador = requerir_roles(["admin"])
    roles = validador("administrador")
    assert "admin" in roles
    assert "administrador" in roles

def test_auth_roles_requerir_roles_insuficientes():
    from fastapi import HTTPException
    validador = requerir_roles(["admin"])
    with pytest.raises(HTTPException) as exc:
        validador("residente")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Permisos insuficientes"
