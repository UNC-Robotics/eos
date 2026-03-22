"""drop_allocation_request_tables_add_reservations

Revision ID: c5fc0d538efc
Revises: 8ded42ad5a58
Create Date: 2026-03-14 18:31:05.356409

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers used by Alembic.
revision = 'c5fc0d538efc'
down_revision = '8ded42ad5a58'
branch_labels = None
depends_on = None


def upgrade():
    # Create new reservations table
    op.create_table('reservations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'GRANTED', 'CANCELLED', name='reservationstatus'), nullable=False),
        sa.Column('devices', sa.JSON(), nullable=False),
        sa.Column('resources', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reservations_owner'), 'reservations', ['owner'], unique=False)
    op.create_index(op.f('ix_reservations_status'), 'reservations', ['status'], unique=False)

    # Drop child tables first (FK references to allocation_requests)
    op.drop_index(op.f('idx_alloc_req_devices_lab_name'), table_name='allocation_request_devices')
    op.drop_table('allocation_request_devices')
    op.drop_index(op.f('idx_alloc_req_resources_lab_name'), table_name='allocation_request_resources')
    op.drop_table('allocation_request_resources')

    # Drop parent table
    op.drop_index(op.f('ix_allocation_requests_experiment_name'), table_name='allocation_requests')
    op.drop_index(op.f('ix_allocation_requests_requester'), table_name='allocation_requests')
    op.drop_index(op.f('ix_allocation_requests_status'), table_name='allocation_requests')
    op.drop_table('allocation_requests')

    # Clean up old enum type
    sa.Enum(name='allocationrequeststatus').drop(op.get_bind(), checkfirst=True)


def downgrade():
    # Recreate old enum type
    sa.Enum('PENDING', 'ALLOCATED', 'COMPLETED', 'ABORTED', name='allocationrequeststatus').create(op.get_bind(), checkfirst=True)

    # Recreate parent table first
    op.create_table('allocation_requests',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('requester', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('experiment_name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('priority', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
        sa.Column('timeout', sa.INTEGER(), server_default=sa.text('600'), autoincrement=False, nullable=False),
        sa.Column('reason', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('status', postgresql.ENUM('PENDING', 'ALLOCATED', 'COMPLETED', 'ABORTED', name='allocationrequeststatus'), server_default=sa.text("'PENDING'::allocationrequeststatus"), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('allocated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name'], name=op.f('allocation_requests_experiment_name_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('allocation_requests_pkey'))
    )
    op.create_index(op.f('ix_allocation_requests_status'), 'allocation_requests', ['status'], unique=False)
    op.create_index(op.f('ix_allocation_requests_requester'), 'allocation_requests', ['requester'], unique=False)
    op.create_index(op.f('ix_allocation_requests_experiment_name'), 'allocation_requests', ['experiment_name'], unique=False)

    # Then recreate child tables
    op.create_table('allocation_request_devices',
        sa.Column('request_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('lab_name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], name=op.f('allocation_request_devices_request_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('request_id', 'lab_name', 'name', name=op.f('allocation_request_devices_pkey'))
    )
    op.create_index(op.f('idx_alloc_req_devices_lab_name'), 'allocation_request_devices', ['lab_name'], unique=False)

    op.create_table('allocation_request_resources',
        sa.Column('request_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('lab_name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['allocation_requests.id'], name=op.f('allocation_request_resources_request_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('request_id', 'lab_name', 'name', name=op.f('allocation_request_resources_pkey'))
    )
    op.create_index(op.f('idx_alloc_req_resources_lab_name'), 'allocation_request_resources', ['lab_name'], unique=False)

    # Drop reservations table
    op.drop_index(op.f('ix_reservations_status'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_owner'), table_name='reservations')
    op.drop_table('reservations')
    sa.Enum(name='reservationstatus').drop(op.get_bind(), checkfirst=True)
