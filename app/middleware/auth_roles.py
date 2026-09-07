from fastapi import Header, HTTPException


def requerir_roles(roles_permitidos: list[str]):
    """Dependencia de FastAPI para validar roles en header X-Usuario-Roles."""
    def verificador(x_usuario_roles: str = Header(default="")) -> set[str]:
        roles = {r.strip().lower() for r in x_usuario_roles.split(",") if r.strip()}
        if not roles.intersection({r.lower() for r in roles_permitidos}):
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return roles

    return verificador
