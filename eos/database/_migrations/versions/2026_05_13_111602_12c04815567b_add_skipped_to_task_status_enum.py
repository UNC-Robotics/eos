"""add SKIPPED to task status enum

Revision ID: 12c04815567b
Revises: b7e2f1a3c9d0
Create Date: 2026-05-13 11:16:02.371205

"""
from alembic import op


revision = '12c04815567b'
down_revision = 'b7e2f1a3c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'SKIPPED' AFTER 'COMPLETED'")

    op.execute("ALTER INDEX IF EXISTS ix_experiments_campaign RENAME TO ix_protocol_runs_campaign")
    op.execute("ALTER INDEX IF EXISTS ix_experiments_status RENAME TO ix_protocol_runs_status")


def downgrade():
    op.execute("ALTER INDEX IF EXISTS ix_protocol_runs_status RENAME TO ix_experiments_status")
    op.execute("ALTER INDEX IF EXISTS ix_protocol_runs_campaign RENAME TO ix_experiments_campaign")

    op.execute("UPDATE tasks SET status = 'CANCELLED' WHERE status = 'SKIPPED'")
    op.execute("ALTER TYPE taskstatus RENAME TO taskstatus_old")
    op.execute("CREATE TYPE taskstatus AS ENUM ('CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')")
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE taskstatus USING status::text::taskstatus")
    op.execute("DROP TYPE taskstatus_old")
