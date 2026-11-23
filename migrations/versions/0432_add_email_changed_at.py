"""

Revision ID: 0432_add_email_changed_at
Revises: 0431_add_publish_progress_status
Create Date: 2026-11-13 11:13:13.720166

"""

import sqlalchemy as sa
from alembic import op

revision = "0432_add_email_changed_at"
down_revision = "0431_add_publish_progress_status"


def upgrade():
    op.add_column("users", sa.Column("email_address_changed_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("users", "email_address_changed_at")
