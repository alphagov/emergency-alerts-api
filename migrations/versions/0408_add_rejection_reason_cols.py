"""

Revision ID: 0408_add_rejection_reason_cols
Revises: 0407_drop_notify_template_fields
Create Date: 2024-11-22 10:08:10

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0408_add_rejection_reason_cols"
down_revision = "0407_drop_notify_template_fields"


def upgrade():
    op.add_column("broadcast_message", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("broadcast_message", sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("broadcast_message", sa.Column("rejected_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "broadcast_message_rejected_by_id_fkey",
        "broadcast_message",
        "users",
        ["rejected_by_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("broadcast_message_rejected_by_id_fkey", "broadcast_message", type_="foreignkey")
    op.drop_column("broadcast_message", "rejection_reason")
    op.drop_column("broadcast_message", "rejected_by_id")
    op.drop_column("broadcast_message", "rejected_at")
