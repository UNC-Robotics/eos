"""rename_specifications_to_definitions

Revision ID: b459a15d494d
Revises: 34831ae9e037
Create Date: 2025-12-27 15:48:05.543058

"""
from alembic import op


# revision identifiers used by Alembic.
revision = 'b459a15d494d'
down_revision = '34831ae9e037'
branch_labels = None
depends_on = None


def upgrade():
    # Rename columns first (while table still has old name)
    op.alter_column('specifications', 'spec_type', new_column_name='type')
    op.alter_column('specifications', 'spec_name', new_column_name='name')
    op.alter_column('specifications', 'spec_data', new_column_name='data')

    # Drop old index and create new one with updated name
    op.drop_index('idx_spec_type', table_name='specifications')
    op.create_index('idx_definitions_type', 'specifications', ['type'], unique=False)

    # Rename table
    op.rename_table('specifications', 'definitions')


def downgrade():
    # Rename table back
    op.rename_table('definitions', 'specifications')

    # Drop new index and recreate old one
    op.drop_index('idx_definitions_type', table_name='specifications')
    op.create_index('idx_spec_type', 'specifications', ['type'], unique=False)

    # Rename columns back
    op.alter_column('specifications', 'type', new_column_name='spec_type')
    op.alter_column('specifications', 'name', new_column_name='spec_name')
    op.alter_column('specifications', 'data', new_column_name='spec_data')
