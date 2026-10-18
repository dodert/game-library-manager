"""Add collector fields to games, matching CLZ Games (v0.4)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLUMNS = [
    ("publisher", sa.String(150)),
    ("developer", sa.String(150)),
    ("genre", sa.String(150)),
    ("series", sa.String(150)),
    ("item_type", sa.String(50)),
    ("serial_number", sa.String(100)),
    ("completeness", sa.String(30)),
    ("condition", sa.String(50)),
    ("has_box", sa.Boolean()),
    ("has_manual", sa.Boolean()),
    ("quantity", sa.Integer()),
    ("current_value", sa.Numeric(10, 2, asdecimal=False)),
    ("owner", sa.String(100)),
    ("location", sa.String(150)),
    ("storage_device", sa.String(150)),
    ("storage_slot", sa.String(50)),
    ("rating", sa.Integer()),
    ("tags", sa.String(500)),
    ("completed_at", sa.Date()),
    ("loan_due", sa.Date()),
]


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        for name, type_ in COLUMNS:
            batch.add_column(sa.Column(name, type_))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        for name, _ in reversed(COLUMNS):
            batch.drop_column(name)
