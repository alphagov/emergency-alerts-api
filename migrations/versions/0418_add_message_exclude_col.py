"""

Revision ID: 0418_add_message_exclude_col
Revises: 0417_add_extra_content_cols
Create Date: 2025-07-06 11:56:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0418_add_message_exclude_col"
down_revision = "0417_add_extra_content_cols"


def upgrade():
    op.add_column("broadcast_message", sa.Column("exclude", sa.Boolean(), default=False))
    op.execute("UPDATE broadcast_message SET exclude = false")
    op.alter_column("broadcast_message", "exclude", nullable=False)


def downgrade():
    op.drop_column("broadcast_message", "exclude")
