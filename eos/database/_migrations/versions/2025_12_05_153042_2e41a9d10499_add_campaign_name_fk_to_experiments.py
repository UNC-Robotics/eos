"""Add campaign FK to experiments

Revision ID: 2e41a9d10499
Revises: cdfd9928697a
Create Date: 2025-12-05 15:30:42.074806

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers used by Alembic.
revision = '2e41a9d10499'
down_revision = 'cdfd9928697a'
branch_labels = None
depends_on = None




def upgrade():
    op.drop_column('campaigns', 'current_experiment_names')
    op.add_column('experiments', sa.Column('campaign', sa.String(), nullable=True))
    op.create_index(op.f('ix_experiments_campaign'), 'experiments', ['campaign'], unique=False)
    op.create_foreign_key('fk_experiments_campaign', 'experiments', 'campaigns', ['campaign'], ['name'])


def downgrade():
    op.drop_constraint('fk_experiments_campaign', 'experiments', type_='foreignkey')
    op.drop_index(op.f('ix_experiments_campaign'), table_name='experiments')
    op.drop_column('experiments', 'campaign')
    op.add_column('campaigns', sa.Column('current_experiment_names', postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'[]'::json"), autoincrement=False, nullable=False))
