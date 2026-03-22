"""add_held_to_allocations

Revision ID: a1b2c3d4e5f6
Revises: c5fc0d538efc
Create Date: 2026-03-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c5fc0d538efc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('device_allocations', sa.Column('held', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('resource_allocations', sa.Column('held', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('resource_allocations', 'held')
    op.drop_column('device_allocations', 'held')
