"""agrega_usuario_email_a_reserva

Revision ID: 277f23420440
Revises: a1c4e7f29b31
Create Date: 2026-10-18 00:21:21.998377

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '277f23420440'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7f29b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reservas', sa.Column('usuario_email', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reservas', 'usuario_email')
