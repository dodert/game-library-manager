"""Add loan fields to games (v0.4)

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("loaned_to", sa.String(150)))
        batch.add_column(sa.Column("loaned_at", sa.Date()))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_column("loaned_at")
        batch.drop_column("loaned_to")
