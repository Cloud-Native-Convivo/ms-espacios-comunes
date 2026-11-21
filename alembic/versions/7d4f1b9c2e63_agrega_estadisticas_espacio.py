"""agrega_estadisticas_espacio

Revision ID: 7d4f1b9c2e63
Revises: 5c2e8d1a7f40
Create Date: 2026-11-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7d4f1b9c2e63'
down_revision: Union[str, Sequence[str], None] = '5c2e8d1a7f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'estadisticas_espacio',
        sa.Column('espacio_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('condominio_id', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('espacio_id'),
    )
    op.create_index(
        'ix_estadisticas_espacio_condominio', 'estadisticas_espacio', ['condominio_id']
    )
    op.create_table(
        'estadisticas_espacio_dia',
        sa.Column('espacio_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('condominio_id', sa.Integer(), nullable=False),
        sa.Column('reservas_creadas', sa.Integer(), nullable=False),
        sa.Column('reservas_confirmadas', sa.Integer(), nullable=False),
        sa.Column('reservas_canceladas', sa.Integer(), nullable=False),
        sa.Column('reservas_expiradas', sa.Integer(), nullable=False),
        sa.Column('horas_confirmadas', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.PrimaryKeyConstraint('espacio_id', 'fecha'),
    )
    op.create_index(
        'ix_estadisticas_dia_condominio_fecha',
        'estadisticas_espacio_dia',
        ['condominio_id', 'fecha'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_estadisticas_dia_condominio_fecha', table_name='estadisticas_espacio_dia')
    op.drop_table('estadisticas_espacio_dia')
    op.drop_index('ix_estadisticas_espacio_condominio', table_name='estadisticas_espacio')
    op.drop_table('estadisticas_espacio')
