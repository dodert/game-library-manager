"""Initial schema (v0.1: platforms and games)

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(100)),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("platform_id", sa.Integer(), sa.ForeignKey("platforms.id"), nullable=False),
        sa.Column("format", sa.Enum("physical", "digital", name="gameformat", native_enum=False, length=8), nullable=False),
        sa.Column("status", sa.Enum("owned", "wishlist", "sold", "lent", name="gamestatus", native_enum=False, length=8), nullable=False),
        sa.Column("completion", sa.Enum("unplayed", "playing", "completed", "abandoned", name="completionstatus", native_enum=False, length=9), nullable=False),
        sa.Column("store", sa.String(100)),
        sa.Column("edition", sa.String(150)),
        sa.Column("region", sa.String(20)),
        sa.Column("barcode", sa.String(50)),
        sa.Column("release_year", sa.Integer()),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("purchase_price", sa.Numeric(10, 2)),
        sa.Column("notes", sa.Text()),
        sa.Column("cover_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_games_title", "games", ["title"])
    op.create_index("ix_games_barcode", "games", ["barcode"])


def downgrade() -> None:
    op.drop_table("games")
    op.drop_table("platforms")
