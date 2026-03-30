"""rename experiments to protocol runs

Revision ID: b7e2f1a3c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-03-25 12:00:00.000000

"""
from alembic import op

# revision identifiers used by Alembic.
revision = 'b7e2f1a3c9d0'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # -- 1. Rename the experiments table to protocol_runs --
    op.rename_table('experiments', 'protocol_runs')

    # -- 2. Rename the experiment status enum type --
    op.execute("ALTER TYPE experimentstatus RENAME TO protocolrunstatus")

    # -- 3. Rename columns in campaigns table --
    op.alter_column('campaigns', 'experiment_type', new_column_name='protocol')
    op.alter_column('campaigns', 'max_experiments', new_column_name='max_protocol_runs')
    op.alter_column('campaigns', 'max_concurrent_experiments', new_column_name='max_concurrent_protocol_runs')
    op.alter_column('campaigns', 'experiment_parameters', new_column_name='protocol_run_parameters')
    op.alter_column('campaigns', 'experiments_completed', new_column_name='protocol_runs_completed')

    # -- 4. Rename experiment_name columns in child tables --
    # tasks
    op.alter_column('tasks', 'experiment_name', new_column_name='protocol_run_name')
    # campaign_samples
    op.alter_column('campaign_samples', 'experiment_name', new_column_name='protocol_run_name')
    # device_allocations
    op.alter_column('device_allocations', 'experiment_name', new_column_name='protocol_run_name')
    # resource_allocations
    op.alter_column('resource_allocations', 'experiment_name', new_column_name='protocol_run_name')

    # -- 5. Rename indexes on protocol_runs (formerly experiments) --
    op.execute("ALTER INDEX IF EXISTS ix_experiments_name RENAME TO ix_protocol_runs_name")
    op.execute("ALTER INDEX IF EXISTS ix_experiments_owner RENAME TO ix_protocol_runs_owner")
    op.execute("ALTER INDEX IF EXISTS ix_experiments_created_at RENAME TO ix_protocol_runs_created_at")

    # -- 6. Rename indexes on child tables --
    op.execute(
        "ALTER INDEX IF EXISTS idx_experiment_name_task_name RENAME TO idx_protocol_run_name_task_name"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_device_allocations_experiment_name "
        "RENAME TO ix_device_allocations_protocol_run_name"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_resource_allocations_experiment_name "
        "RENAME TO ix_resource_allocations_protocol_run_name"
    )

    # -- 7. Rename foreign key constraints --
    # tasks -> protocol_runs
    op.execute(
        "ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_experiment_name_fkey"
    )
    op.create_foreign_key(
        'tasks_protocol_run_name_fkey', 'tasks', 'protocol_runs',
        ['protocol_run_name'], ['name'], ondelete='CASCADE'
    )

    # campaign_samples -> protocol_runs
    op.execute(
        "ALTER TABLE campaign_samples DROP CONSTRAINT IF EXISTS campaign_samples_experiment_name_fkey"
    )
    op.create_foreign_key(
        'campaign_samples_protocol_run_name_fkey', 'campaign_samples', 'protocol_runs',
        ['protocol_run_name'], ['name'], ondelete='CASCADE'
    )

    # device_allocations -> protocol_runs
    op.execute(
        "ALTER TABLE device_allocations DROP CONSTRAINT IF EXISTS device_allocations_experiment_name_fkey"
    )
    op.create_foreign_key(
        'device_allocations_protocol_run_name_fkey', 'device_allocations', 'protocol_runs',
        ['protocol_run_name'], ['name'], ondelete='CASCADE'
    )

    # resource_allocations -> protocol_runs
    op.execute(
        "ALTER TABLE resource_allocations DROP CONSTRAINT IF EXISTS resource_allocations_experiment_name_fkey"
    )
    op.create_foreign_key(
        'resource_allocations_protocol_run_name_fkey', 'resource_allocations', 'protocol_runs',
        ['protocol_run_name'], ['name'], ondelete='CASCADE'
    )

    # -- 8. Update definition type values --
    op.execute("UPDATE definitions SET type = 'protocol' WHERE type = 'experiment'")

    # -- 9. Update source_path values in definitions --
    op.execute("UPDATE definitions SET source_path = REPLACE(source_path, '/experiments/', '/protocols/') WHERE source_path LIKE '%/experiments/%'")


def downgrade():
    # -- Reverse definition data --
    op.execute("UPDATE definitions SET source_path = REPLACE(source_path, '/protocols/', '/experiments/') WHERE source_path LIKE '%/protocols/%'")
    op.execute("UPDATE definitions SET type = 'experiment' WHERE type = 'protocol'")

    # -- Reverse FK constraints --
    op.drop_constraint('resource_allocations_protocol_run_name_fkey', 'resource_allocations', type_='foreignkey')
    op.create_foreign_key(
        'resource_allocations_experiment_name_fkey', 'resource_allocations', 'experiments',
        ['experiment_name'], ['name'], ondelete='CASCADE'
    )

    op.drop_constraint('device_allocations_protocol_run_name_fkey', 'device_allocations', type_='foreignkey')
    op.create_foreign_key(
        'device_allocations_experiment_name_fkey', 'device_allocations', 'experiments',
        ['experiment_name'], ['name'], ondelete='CASCADE'
    )

    op.drop_constraint('campaign_samples_protocol_run_name_fkey', 'campaign_samples', type_='foreignkey')
    op.create_foreign_key(
        'campaign_samples_experiment_name_fkey', 'campaign_samples', 'experiments',
        ['experiment_name'], ['name'], ondelete='CASCADE'
    )

    op.drop_constraint('tasks_protocol_run_name_fkey', 'tasks', type_='foreignkey')
    op.create_foreign_key(
        'tasks_experiment_name_fkey', 'tasks', 'experiments',
        ['experiment_name'], ['name'], ondelete='CASCADE'
    )

    # -- Reverse index renames --
    op.execute(
        "ALTER INDEX IF EXISTS ix_resource_allocations_protocol_run_name "
        "RENAME TO ix_resource_allocations_experiment_name"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_device_allocations_protocol_run_name "
        "RENAME TO ix_device_allocations_experiment_name"
    )
    op.execute(
        "ALTER INDEX IF EXISTS idx_protocol_run_name_task_name RENAME TO idx_experiment_name_task_name"
    )
    op.execute("ALTER INDEX IF EXISTS ix_protocol_runs_created_at RENAME TO ix_experiments_created_at")
    op.execute("ALTER INDEX IF EXISTS ix_protocol_runs_owner RENAME TO ix_experiments_owner")
    op.execute("ALTER INDEX IF EXISTS ix_protocol_runs_name RENAME TO ix_experiments_name")

    # -- Reverse column renames --
    op.alter_column('resource_allocations', 'protocol_run_name', new_column_name='experiment_name')
    op.alter_column('device_allocations', 'protocol_run_name', new_column_name='experiment_name')
    op.alter_column('campaign_samples', 'protocol_run_name', new_column_name='experiment_name')
    op.alter_column('tasks', 'protocol_run_name', new_column_name='experiment_name')
    op.alter_column('campaigns', 'protocol_runs_completed', new_column_name='experiments_completed')
    op.alter_column('campaigns', 'protocol_run_parameters', new_column_name='experiment_parameters')
    op.alter_column('campaigns', 'max_concurrent_protocol_runs', new_column_name='max_concurrent_experiments')
    op.alter_column('campaigns', 'max_protocol_runs', new_column_name='max_experiments')
    op.alter_column('campaigns', 'protocol', new_column_name='experiment_type')

    # -- Reverse enum rename --
    op.execute("ALTER TYPE protocolrunstatus RENAME TO experimentstatus")

    # -- Reverse table rename --
    op.rename_table('protocol_runs', 'experiments')
