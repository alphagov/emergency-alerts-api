"""

Revision ID: 0409_add_rejected_by_api_col
Revises: 0408_add_rejection_reason_cols
Create Date: 2025-01-6 11:56:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0409_add_rejected_by_api_col"
down_revision = "0408_add_rejection_reason_cols"


def upgrade():
    op.add_column("broadcast_message", sa.Column("rejected_by_api", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "rejected_by_api")
