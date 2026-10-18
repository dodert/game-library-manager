"""Add summary and steam_appid to games (v0.2)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("summary", sa.Text()))
        batch.add_column(sa.Column("steam_appid", sa.Integer()))
        batch.create_index("ix_games_steam_appid", ["steam_appid"])


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_index("ix_games_steam_appid")
        batch.drop_column("steam_appid")
        batch.drop_column("summary")
