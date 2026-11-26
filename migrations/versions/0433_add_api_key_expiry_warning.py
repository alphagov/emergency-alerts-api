"""

Revision ID: 0433_add_api_key_expiry_warning
Revises: 0432_add_email_changed_at
Create Date: 2026-11-26 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0433_add_api_key_expiry_warning"
down_revision = "0432_add_email_changed_at"


def upgrade():
    # Both tables: ApiKey is Versioned, so history rows copy every column
    op.add_column("api_keys", sa.Column("expiry_warning_sent_at", sa.DateTime(), nullable=True))
    op.add_column("api_keys_history", sa.Column("expiry_warning_sent_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("api_keys_history", "expiry_warning_sent_at")
    op.drop_column("api_keys", "expiry_warning_sent_at")
