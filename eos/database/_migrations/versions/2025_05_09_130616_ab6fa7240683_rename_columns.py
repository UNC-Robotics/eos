"""rename dynamic_parameters and optimizer_computer_ip

Revision ID: ab6fa7240683
Revises: 229203e6c7a6
Create Date: 2025-05-09 13:06:16.900011

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers used by Alembic.
revision = "ab6fa7240683"
down_revision = "229203e6c7a6"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("experiments", "dynamic_parameters", new_column_name="parameters")
    op.alter_column("campaigns", "dynamic_parameters", new_column_name="parameters")
    op.alter_column("campaigns", "optimizer_computer_ip", new_column_name="optimizer_ip")


def downgrade():
    op.alter_column("experiments", "parameters", new_column_name="dynamic_parameters")
    op.alter_column("campaigns", "parameters", new_column_name="dynamic_parameters")
    op.alter_column("campaigns", "optimizer_ip", new_column_name="optimizer_computer_ip")
