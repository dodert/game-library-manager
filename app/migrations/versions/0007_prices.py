"""PriceCharting market prices and their history (v0.14)

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("pricecharting_id", sa.Integer))
        batch.add_column(sa.Column("price_checked_at", sa.DateTime))
        batch.add_column(sa.Column("price_error", sa.String(300)))
    op.create_table(
        "price_checks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checked_at", sa.DateTime, nullable=False),
        sa.Column("product_id", sa.Integer, nullable=False),
        sa.Column("product_name", sa.String(300)),
        sa.Column("console_name", sa.String(150)),
        *(sa.Column(name, sa.Integer) for name in ("loose", "cib", "new", "box_only", "manual_only", "graded")),
    )
    op.create_index("ix_price_checks_game_id", "price_checks", ["game_id"])
    op.create_index("ix_price_checks_checked_at", "price_checks", ["checked_at"])


def downgrade() -> None:
    op.drop_table("price_checks")
    with op.batch_alter_table("games") as batch:
        batch.drop_column("price_error")
        batch.drop_column("price_checked_at")
        batch.drop_column("pricecharting_id")
