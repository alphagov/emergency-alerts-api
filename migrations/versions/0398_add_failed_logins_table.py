"""

Revision ID: 0398_add_failed_logins_table
Revises: 0397_drop_providers
Create Date: 2024-06-19 16:31:49.657408

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0398_add_failed_logins_table"
down_revision = "0397_drop_providers"


def upgrade():
    op.create_table(
        "failed_logins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("failed_logins")
