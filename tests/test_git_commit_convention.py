"""Validador de convención Gitmoji + Conventional Commits para ms-espacios-comunes.
Alineado con pr-quality.yml y AGENTS.md §11.2.
"""
import re
import pytest

GITMOJI_CONVENTIONAL_PATTERN = re.compile(
    r"^(?::\w+:|[^\w\s:]\S*)\s(\w*)(?:\(([\w$.\-*/ ]*)\))?!?:\s(.*)$"
)

ALLOWED_TYPES = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
}


def is_valid_commit_message(message: str) -> bool:
    if not message or not message.strip():
        return False
    first_line = message.strip().split("\n")[0].strip()
    match = GITMOJI_CONVENTIONAL_PATTERN.match(first_line)
    if not match:
        return False
    commit_type = match.group(1)
    return commit_type in ALLOWED_TYPES


@pytest.mark.parametrize(
    "msg",
    [
        ":sparkles: feat: crear endpoint de reservas",
        "✨ feat(reservas): validar solapamiento de horarios",
        ":lock: fix(auth): validar rol conserje en aprobacion",
        ":memo: docs(readme): documentar verificacion local",
        ":white_check_mark: test(reservas): cubrir casos de conflicto",
        "🐛 fix(eventos): outbox routing key corregida",
        ":wrench: chore(deps): actualizar librerias menores",
    ],
)
def test_valid_commit_messages(msg: str):
    assert is_valid_commit_message(msg) is True


@pytest.mark.parametrize(
    "msg",
    [
        "fix: sin gitmoji al inicio",
        ":sparkles: sin tipo convencional",
        "WIP prueba rapida",
        ":sparkles: invalid_type(modulo): descripcion",
        "feat: solo texto",
        "",
    ],
)
def test_invalid_commit_messages(msg: str):
    assert is_valid_commit_message(msg) is False
