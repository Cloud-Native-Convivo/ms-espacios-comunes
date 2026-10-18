import pytest
from fastapi import HTTPException

from app.config.security_config import (
    UsuarioContexto,
    normalizar_roles,
    obtener_contexto_usuario,
    requerir_roles_contexto,
)


def test_normalizar_roles_bidireccional():
    assert "admin" in normalizar_roles("administrador")
    assert "administrador" in normalizar_roles("admin")
    assert "residente" in normalizar_roles("  Residente , Admin  ")

def test_usuario_contexto_helpers():
    ctx = UsuarioContexto(usuario_sub="user-1", roles={"residente", "admin", "administrador"})
    assert ctx.es_admin() is True
    assert ctx.es_residente() is True
    assert ctx.es_conserje() is False
    assert ctx.tiene_rol("admin") is True

def test_obtener_contexto_usuario_exito():
    ctx = obtener_contexto_usuario(
        x_usuario_sub="sub-123",
        x_usuario_roles="residente",
        x_usuario_unidad="101-A",
        x_correlation_id="corr-xyz",
        x_condominio_id=5,
    )
    assert ctx.usuario_sub == "sub-123"
    assert "residente" in ctx.roles
    assert ctx.unidad_id == "101-A"
    assert ctx.condominio_id == 5
    assert ctx.correlation_id == "corr-xyz"

def test_obtener_contexto_usuario_sin_sub_retorna_401():
    with pytest.raises(HTTPException) as exc:
        obtener_contexto_usuario(x_usuario_sub=None)
    assert exc.value.status_code == 401
    assert "faltante o inválido" in exc.value.detail

def test_obtener_contexto_usuario_sub_espacios_retorna_401():
    with pytest.raises(HTTPException) as exc:
        obtener_contexto_usuario(x_usuario_sub="   ")
    assert exc.value.status_code == 401

def test_requerir_roles_contexto_deniega_403():
    verificador = requerir_roles_contexto(["admin"])
    ctx_residente = UsuarioContexto(usuario_sub="u1", roles={"residente"})
    with pytest.raises(HTTPException) as exc:
        verificador(ctx_residente)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Permisos insuficientes"

def test_requerir_roles_contexto_permite_acceso():
    verificador = requerir_roles_contexto(["admin"])
    ctx_admin = UsuarioContexto(usuario_sub="u1", roles={"administrador", "admin"})
    assert verificador(ctx_admin) == ctx_admin
