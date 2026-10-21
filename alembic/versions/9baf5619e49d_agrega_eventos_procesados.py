"""agrega_eventos_procesados

Revision ID: 9baf5619e49d
Revises: 277f23420440
Create Date: 2026-10-18 00:25:10.458383

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9baf5619e49d'
down_revision: Union[str, Sequence[str], None] = '277f23420440'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'eventos_procesados',
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('consumidor', sa.String(length=100), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('event_id', 'consumidor'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('eventos_procesados')
