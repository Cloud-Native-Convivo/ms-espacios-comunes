"""agrega_eventos_outbox_kafka

Revision ID: 5c2e8d1a7f40
Revises: 9baf5619e49d
Create Date: 2026-11-20 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5c2e8d1a7f40'
down_revision: Union[str, Sequence[str], None] = '9baf5619e49d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'eventos_outbox_kafka',
        sa.Column('id', sa.Integer(), sa.Identity(start=1), nullable=False),
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('topico', sa.String(length=100), nullable=False),
        sa.Column('clave', sa.String(length=100), nullable=False),
        sa.Column('carga_util', sa.Text(), nullable=False),
        sa.Column('procesado', sa.Boolean(), nullable=False),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id'),
    )
    op.create_index(
        'ix_eventos_outbox_kafka_procesado', 'eventos_outbox_kafka', ['procesado', 'id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_eventos_outbox_kafka_procesado', table_name='eventos_outbox_kafka')
    op.drop_table('eventos_outbox_kafka')
