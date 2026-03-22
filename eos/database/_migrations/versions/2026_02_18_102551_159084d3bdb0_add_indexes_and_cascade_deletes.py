"""add_indexes_and_cascade_deletes

Revision ID: 159084d3bdb0
Revises: 9e17cc7d66ae
Create Date: 2026-02-18 10:25:51.604577

"""
from alembic import op


# revision identifiers used by Alembic.
revision = '159084d3bdb0'
down_revision = '9e17cc7d66ae'
branch_labels = None
depends_on = None


def upgrade():
    # --- New indexes ---
    op.create_index('ix_campaigns_owner', 'campaigns', ['owner'], unique=False)
    op.create_index('ix_campaigns_created_at', 'campaigns', ['created_at'], unique=False)
    op.create_index('ix_experiments_owner', 'experiments', ['owner'], unique=False)
    op.create_index('ix_experiments_created_at', 'experiments', ['created_at'], unique=False)
    op.create_index('ix_tasks_created_at', 'tasks', ['created_at'], unique=False)
    op.create_index('ix_device_allocations_owner', 'device_allocations', ['owner'], unique=False)
    op.create_index('ix_resource_allocations_owner', 'resource_allocations', ['owner'], unique=False)

    # --- Add ON DELETE CASCADE to foreign keys ---

    # experiments.campaign -> campaigns.name
    op.drop_constraint('fk_experiments_campaign', 'experiments', type_='foreignkey')
    op.create_foreign_key('fk_experiments_campaign', 'experiments', 'campaigns', ['campaign'], ['name'], ondelete='CASCADE')

    # campaign_samples.campaign_name -> campaigns.name
    op.drop_constraint('campaign_samples_campaign_name_fkey', 'campaign_samples', type_='foreignkey')
    op.create_foreign_key('campaign_samples_campaign_name_fkey', 'campaign_samples', 'campaigns', ['campaign_name'], ['name'], ondelete='CASCADE')

    # campaign_samples.experiment_name -> experiments.name
    op.drop_constraint('campaign_samples_experiment_name_fkey', 'campaign_samples', type_='foreignkey')
    op.create_foreign_key('campaign_samples_experiment_name_fkey', 'campaign_samples', 'experiments', ['experiment_name'], ['name'], ondelete='CASCADE')

    # allocation_requests.experiment_name -> experiments.name
    op.drop_constraint('allocation_requests_experiment_name_fkey', 'allocation_requests', type_='foreignkey')
    op.create_foreign_key('allocation_requests_experiment_name_fkey', 'allocation_requests', 'experiments', ['experiment_name'], ['name'], ondelete='CASCADE')

    # device_allocations.experiment_name -> experiments.name
    op.drop_constraint('device_allocations_experiment_name_fkey', 'device_allocations', type_='foreignkey')
    op.create_foreign_key('device_allocations_experiment_name_fkey', 'device_allocations', 'experiments', ['experiment_name'], ['name'], ondelete='CASCADE')

    # resource_allocations.experiment_name -> experiments.name
    op.drop_constraint('resource_allocations_experiment_name_fkey', 'resource_allocations', type_='foreignkey')
    op.create_foreign_key('resource_allocations_experiment_name_fkey', 'resource_allocations', 'experiments', ['experiment_name'], ['name'], ondelete='CASCADE')


def downgrade():
    # --- Remove indexes ---
    op.drop_index('ix_resource_allocations_owner', table_name='resource_allocations')
    op.drop_index('ix_device_allocations_owner', table_name='device_allocations')
    op.drop_index('ix_tasks_created_at', table_name='tasks')
    op.drop_index('ix_experiments_created_at', table_name='experiments')
    op.drop_index('ix_experiments_owner', table_name='experiments')
    op.drop_index('ix_campaigns_created_at', table_name='campaigns')
    op.drop_index('ix_campaigns_owner', table_name='campaigns')

    # --- Restore foreign keys without ON DELETE CASCADE ---

    op.drop_constraint('fk_experiments_campaign', 'experiments', type_='foreignkey')
    op.create_foreign_key('fk_experiments_campaign', 'experiments', 'campaigns', ['campaign'], ['name'])

    op.drop_constraint('campaign_samples_campaign_name_fkey', 'campaign_samples', type_='foreignkey')
    op.create_foreign_key('campaign_samples_campaign_name_fkey', 'campaign_samples', 'campaigns', ['campaign_name'], ['name'])

    op.drop_constraint('campaign_samples_experiment_name_fkey', 'campaign_samples', type_='foreignkey')
    op.create_foreign_key('campaign_samples_experiment_name_fkey', 'campaign_samples', 'experiments', ['experiment_name'], ['name'])

    op.drop_constraint('allocation_requests_experiment_name_fkey', 'allocation_requests', type_='foreignkey')
    op.create_foreign_key('allocation_requests_experiment_name_fkey', 'allocation_requests', 'experiments', ['experiment_name'], ['name'])

    op.drop_constraint('device_allocations_experiment_name_fkey', 'device_allocations', type_='foreignkey')
    op.create_foreign_key('device_allocations_experiment_name_fkey', 'device_allocations', 'experiments', ['experiment_name'], ['name'])

    op.drop_constraint('resource_allocations_experiment_name_fkey', 'resource_allocations', type_='foreignkey')
    op.create_foreign_key('resource_allocations_experiment_name_fkey', 'resource_allocations', 'experiments', ['experiment_name'], ['name'])
