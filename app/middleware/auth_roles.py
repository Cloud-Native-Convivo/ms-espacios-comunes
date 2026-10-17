from fastapi import Header, HTTPException
from app.config.security_config import (
    UsuarioContexto,
    normalizar_roles,
    obtener_contexto_usuario,
    requerir_roles_contexto,
)

__all__ = [
    "UsuarioContexto",
    "normalizar_roles",
    "obtener_contexto_usuario",
    "requerir_roles_contexto",
    "requerir_roles",
    "obtener_usuario_actual",
]


def requerir_roles(roles_permitidos: list[str]):
    """Dependencia de FastAPI para validar roles en header X-Usuario-Roles."""
    permitidos_normalizados = set()
    for r in roles_permitidos:
        permitidos_normalizados.update(normalizar_roles(r))

    def verificador(x_usuario_roles: str = Header(default="")) -> set[str]:
        roles = normalizar_roles(x_usuario_roles)
        if not roles.intersection(permitidos_normalizados):
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return roles

    return verificador


def obtener_usuario_actual(x_usuario_sub: str | None = Header(default=None)) -> str:
    """Extrae y valida que X-Usuario-Sub este presente y no vacio."""
    if not x_usuario_sub or not x_usuario_sub.strip():
        raise HTTPException(
            status_code=401,
            detail="Identificador de usuario faltante o inválido",
        )
    return x_usuario_sub.strip()
