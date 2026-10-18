"""Track when each game was last looked up online (v0.5)

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("scraped_at", sa.DateTime()))
        batch.add_column(sa.Column("scrape_error", sa.String(300)))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_column("scrape_error")
        batch.drop_column("scraped_at")
