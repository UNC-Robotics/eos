"""initial

Revision ID: 043566da38f3
Revises: 
Create Date: 2025-10-05 18:44:58.837886

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers used by Alembic.
revision = '043566da38f3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('experiment_type', sa.String(), nullable=False),
        sa.Column('owner', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_experiments', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_concurrent_experiments', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('optimize', sa.Boolean(), nullable=False),
        sa.Column('optimizer_ip', sa.String(), nullable=False, server_default='127.0.0.1'),
        sa.Column('global_parameters', sa.JSON(), nullable=True),
        sa.Column('experiment_parameters', sa.JSON(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('resume', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.Enum('CREATED', 'RUNNING', 'COMPLETED', 'SUSPENDED', 'CANCELLED', 'FAILED', name='campaignstatus'), nullable=False, server_default='CREATED'),
        sa.Column('experiments_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_experiment_names', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('pareto_solutions', sa.JSON(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_campaigns_name', 'campaigns', ['name'], unique=True)

    # Create experiments table
    op.create_table(
        'experiments',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('owner', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('parameters', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('resume', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.Enum('CREATED', 'RUNNING', 'COMPLETED', 'SUSPENDED', 'CANCELLED', 'FAILED', name='experimentstatus'), nullable=False, server_default='CREATED'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_experiments_name', 'experiments', ['name'], unique=True)

    # Create campaign_samples table (depends on campaigns and experiments)
    op.create_table(
        'campaign_samples',
        sa.Column('campaign_name', sa.String(), nullable=False),
        sa.Column('experiment_name', sa.String(), nullable=False),
        sa.Column('inputs', sa.JSON(), nullable=False),
        sa.Column('outputs', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_name'], ['campaigns.name']),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
        sa.PrimaryKeyConstraint('campaign_name', 'experiment_name')
    )

    # Create tasks table (depends on experiments)
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('experiment_name', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('devices', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('input_parameters', sa.JSON(), nullable=True),
        sa.Column('input_resources', sa.JSON(), nullable=True),
        sa.Column('output_parameters', sa.JSON(), nullable=True),
        sa.Column('output_resources', sa.JSON(), nullable=True),
        sa.Column('output_file_names', sa.JSON(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('allocation_timeout', sa.Integer(), nullable=False, server_default='600'),
        sa.Column('meta', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('status', sa.Enum('CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='taskstatus'), nullable=False, server_default='CREATED'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_experiment_name_task_name', 'tasks', ['experiment_name', 'name'], unique=True)

    # Create resources table
    op.create_table(
        'resources',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_resources_name', 'resources', ['name'], unique=True)

    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('lab_name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('computer', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', name='devicestatus'), nullable=False, server_default='ACTIVE'),
        sa.Column('meta', sa.JSON(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_lab_name_device_name', 'devices', ['lab_name', 'name'], unique=True)

    # Create allocation_requests table (depends on experiments)
    op.create_table(
        'allocation_requests',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('requester', sa.String(), nullable=False),
        sa.Column('experiment_name', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('timeout', sa.Integer(), nullable=False, server_default='600'),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('allocations', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('status', sa.Enum('PENDING', 'ALLOCATED', 'COMPLETED', 'ABORTED', name='allocationrequeststatus'), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('allocated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
        sa.PrimaryKeyConstraint('id')
    )

    # Create allocations table (depends on experiments)
    op.create_table(
        'allocations',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('allocation_type', sa.Enum('RESOURCE', 'DEVICE', name='allocationtype'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('lab_name', sa.String(), nullable=True),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('owner', sa.String(), nullable=False),
        sa.Column('experiment_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['experiment_name'], ['experiments.name']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_allocations_allocation_type', 'allocations', ['allocation_type'], unique=False)
    op.create_index('idx_allocation_type_lab_name_name', 'allocations', ['allocation_type', 'lab_name', 'name'], unique=True)


def downgrade():
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_index('idx_allocation_type_lab_name_name', table_name='allocations')
    op.drop_index('ix_allocations_allocation_type', table_name='allocations')
    op.drop_table('allocations')
    
    op.drop_table('allocation_requests')
    
    op.drop_index('idx_lab_name_device_name', table_name='devices')
    op.drop_table('devices')
    
    op.drop_index('ix_resources_name', table_name='resources')
    op.drop_table('resources')
    
    op.drop_index('idx_experiment_name_task_name', table_name='tasks')
    op.drop_table('tasks')
    
    op.drop_table('campaign_samples')
    
    op.drop_index('ix_experiments_name', table_name='experiments')
    op.drop_table('experiments')
    
    op.drop_index('ix_campaigns_name', table_name='campaigns')
    op.drop_table('campaigns')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS allocationtype')
    op.execute('DROP TYPE IF EXISTS allocationrequeststatus')
    op.execute('DROP TYPE IF EXISTS devicestatus')
    op.execute('DROP TYPE IF EXISTS taskstatus')
    op.execute('DROP TYPE IF EXISTS experimentstatus')
    op.execute('DROP TYPE IF EXISTS campaignstatus')
