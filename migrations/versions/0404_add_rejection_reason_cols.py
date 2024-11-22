"""

Revision ID: 0404_add_rejection_reason_cols
Revises: 0403_add_common_passwords_table
Create Date: 2024-11-22 10:08:10

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0404_add_rejection_reason_cols"
down_revision = "0403_add_common_passwords_table"


def upgrade():
    op.add_column("broadcast_message", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("broadcast_message", sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "rejection_reason")
    op.drop_column("broadcast_message", "rejected_by_id")
