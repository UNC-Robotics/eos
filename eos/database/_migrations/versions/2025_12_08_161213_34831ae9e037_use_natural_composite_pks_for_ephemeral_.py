"""Use natural composite PKs for ephemeral tables

Revision ID: 34831ae9e037
Revises: 1a76b054d691
Create Date: 2025-12-08 16:12:13.949839

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '34831ae9e037'
down_revision = '1a76b054d691'
branch_labels = None
depends_on = None


def get_devicestatus_column():
    """Return the appropriate status column type based on dialect."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        return sa.Column('status', postgresql.ENUM('ACTIVE', 'INACTIVE', name='devicestatus', create_type=False), nullable=False)
    else:
        return sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', name='devicestatus'), nullable=False)


def upgrade():
    op.drop_table('allocation_request_devices')
    op.drop_table('allocation_request_resources')
    op.drop_table('device_allocations')
    op.drop_table('resource_allocations')
    op.drop_table('devices')
    op.drop_table('resources')
    op.drop_table('specifications')

    op.create_table(
        'devices',
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(255), nullable=False),
        sa.Column('computer', sa.String(255), nullable=False),
        get_devicestatus_column(),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('lab_name', 'name'),
    )

    op.create_table(
        'resources',
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(255), nullable=False),
        sa.Column('lab', sa.String(255), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )
    op.create_index('ix_resources_lab', 'resources', ['lab'])

    op.create_table(
        'specifications',
        sa.Column('spec_type', sa.String(255), nullable=False),
        sa.Column('spec_name', sa.String(255), nullable=False),
        sa.Column('spec_data', sa.JSON(), nullable=False),
        sa.Column('is_loaded', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('package_name', sa.String(255), nullable=False),
        sa.Column('source_path', sa.String(1024), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('spec_type', 'spec_name'),
    )
    op.create_index('idx_spec_type', 'specifications', ['spec_type'])

    op.create_table(
        'device_allocations',
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('owner', sa.String(255), nullable=False),
        sa.Column('experiment_name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('lab_name', 'name'),
        sa.ForeignKeyConstraint(['lab_name', 'name'], ['devices.lab_name', 'devices.name']),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
    )
    op.create_index('ix_device_allocations_experiment_name', 'device_allocations', ['experiment_name'])

    op.create_table(
        'resource_allocations',
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('owner', sa.String(255), nullable=False),
        sa.Column('experiment_name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('name'),
        sa.ForeignKeyConstraint(['name'], ['resources.name']),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
    )
    op.create_index('ix_resource_allocations_experiment_name', 'resource_allocations', ['experiment_name'])

    op.create_table(
        'allocation_request_devices',
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('request_id', 'lab_name', 'name'),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_alloc_req_devices_lab_name', 'allocation_request_devices', ['lab_name'])

    op.create_table(
        'allocation_request_resources',
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('request_id', 'lab_name', 'name'),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_alloc_req_resources_lab_name', 'allocation_request_resources', ['lab_name'])


def downgrade():
    op.drop_table('allocation_request_devices')
    op.drop_table('allocation_request_resources')
    op.drop_table('device_allocations')
    op.drop_table('resource_allocations')
    op.drop_table('devices')
    op.drop_table('resources')
    op.drop_table('specifications')

    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(255), nullable=False),
        sa.Column('computer', sa.String(255), nullable=False),
        get_devicestatus_column(),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_lab_name_device_name', 'devices', ['lab_name', 'name'], unique=True)

    op.create_table(
        'resources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(255), nullable=False),
        sa.Column('lab', sa.String(255), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_resources_name', 'resources', ['name'], unique=True)
    op.create_index('ix_resources_lab', 'resources', ['lab'])

    op.create_table(
        'specifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('spec_type', sa.String(255), nullable=False),
        sa.Column('spec_name', sa.String(255), nullable=False),
        sa.Column('spec_data', sa.JSON(), nullable=False),
        sa.Column('is_loaded', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('package_name', sa.String(255), nullable=False),
        sa.Column('source_path', sa.String(1024), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_spec_type_name', 'specifications', ['spec_type', 'spec_name'], unique=True)
    op.create_index('idx_spec_type', 'specifications', ['spec_type'])

    op.create_table(
        'device_allocations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('owner', sa.String(255), nullable=False),
        sa.Column('experiment_name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['lab_name', 'name'], ['devices.lab_name', 'devices.name']),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
    )
    op.create_index('idx_device_allocation_lab_name_name', 'device_allocations', ['lab_name', 'name'], unique=True)
    op.create_index('ix_device_allocations_experiment_name', 'device_allocations', ['experiment_name'])

    op.create_table(
        'resource_allocations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('owner', sa.String(255), nullable=False),
        sa.Column('experiment_name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['name'], ['resources.name']),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
    )
    op.create_unique_constraint('resource_allocations_name_key', 'resource_allocations', ['name'])
    op.create_index('ix_resource_allocations_experiment_name', 'resource_allocations', ['experiment_name'])

    op.create_table(
        'allocation_request_devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_allocation_request_devices_request_id', 'allocation_request_devices', ['request_id'])
    op.create_index('ix_allocation_request_devices_lab_name', 'allocation_request_devices', ['lab_name'])
    op.create_index('idx_alloc_req_devices_request_lab', 'allocation_request_devices', ['request_id', 'lab_name'])

    op.create_table(
        'allocation_request_resources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('lab_name', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_allocation_request_resources_request_id', 'allocation_request_resources', ['request_id'])
    op.create_index('ix_allocation_request_resources_lab_name', 'allocation_request_resources', ['lab_name'])
    op.create_index('idx_alloc_req_resources_request_lab', 'allocation_request_resources', ['request_id', 'lab_name'])