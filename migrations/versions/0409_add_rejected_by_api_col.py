"""

Revision ID: 0409_add_rejected_by_api_col
Revises: 0408_add_rejection_reason_cols
Create Date: 2025-01-6 11:56:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0409_add_rejected_by_api_col"
down_revision = "0408_add_rejection_reason_cols"


def upgrade():
    op.add_column(
        "broadcast_message", sa.Column("rejected_by_api_key_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "broadcast_message_rejected_by_api_key_id_fkey",
        "broadcast_message",
        "api_keys",
        ["rejected_by_api_key_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("broadcast_message_rejected_by_api_key_id_fkey", "broadcast_message", type_="foreignkey")
    op.drop_column("broadcast_message", "rejected_by_api_key_id")
