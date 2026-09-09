"""rename beacon meta key to optimizer

Revision ID: 391060b4292b
Revises: a47b8bf03ce8
Create Date: 2026-09-05 16:19:51.974429

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers used by Alembic.
revision = '391060b4292b'
down_revision = 'a47b8bf03ce8'
branch_labels = None
depends_on = None


_TABLES = ("campaigns", "campaign_samples")


def _rename_meta_key(old: str, new: str) -> None:
    for table in _TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} "
                f"SET meta = ((meta::jsonb - :old) || jsonb_build_object(:new, meta::jsonb -> :old))::json "
                f"WHERE meta::jsonb ? :old"
            ).bindparams(old=old, new=new)
        )


def upgrade():
    _rename_meta_key("beacon", "optimizer")


def downgrade():
    _rename_meta_key("optimizer", "beacon")
