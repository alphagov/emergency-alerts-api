"""

Revision ID: 0407_add_rejection_reason_cols
Revises: 0406_drop_notify_service_fields
Create Date: 2024-11-22 10:08:10

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0407_add_rejection_reason_cols"
down_revision = "0406_drop_notify_service_fields"


def upgrade():
    op.add_column("broadcast_message", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("broadcast_message", sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("broadcast_message", sa.Column("rejected_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "rejection_reason")
    op.drop_column("broadcast_message", "rejected_by_id")
    op.drop_column("broadcast_message", "rejected_at")
