from fastapi import Header, HTTPException


def requerir_roles(roles_permitidos: list[str]):
    """Dependencia de FastAPI para validar roles en header X-Usuario-Roles."""
    def verificador(x_usuario_roles: str = Header(default="")) -> set[str]:
        roles = {r.strip().lower() for r in x_usuario_roles.split(",") if r.strip()}
        if "administrador" in roles:
            roles.add("admin")
        if "admin" in roles:
            roles.add("administrador")
        if not roles.intersection({r.lower() for r in roles_permitidos}):
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
