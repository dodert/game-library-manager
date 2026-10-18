"""Optional text to look a game up online instead of its title (v0.8)

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("search_title", sa.String(300)))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_column("search_title")
