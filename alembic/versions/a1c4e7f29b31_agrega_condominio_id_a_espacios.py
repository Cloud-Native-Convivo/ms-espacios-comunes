"""agrega_condominio_id_a_espacios

Revision ID: a1c4e7f29b31
Revises: d383e5fb03b6
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e7f29b31'
down_revision: Union[str, Sequence[str], None] = 'd383e5fb03b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('espacios', sa.Column('condominio_id', sa.Integer(), server_default='1', nullable=False))
    op.create_index('ix_espacios_condominio_id', 'espacios', ['condominio_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_espacios_condominio_id', table_name='espacios')
    op.drop_column('espacios', 'condominio_id')
