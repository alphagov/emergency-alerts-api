"""

Revision ID: 0417_add_extra_content_cols
Revises: 0416_add_govuk_acknowledged
Create Date: 2025-07-06 11:56:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0417_add_extra_content_cols"
down_revision = "0416_add_govuk_acknowledged"


def upgrade():
    op.add_column("broadcast_message", sa.Column("extra_content", sa.Text(), nullable=True))
    op.add_column("broadcast_message_history", sa.Column("extra_content", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "extra_content")
    op.drop_column("broadcast_message_history", "extra_content")
