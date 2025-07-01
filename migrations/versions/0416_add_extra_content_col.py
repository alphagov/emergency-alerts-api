"""

Revision ID: 0416_add_extra_content_col
Revises: 0415_add_edit_reasons
Create Date: 2025-01-6 11:56:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0416_add_extra_content_col"
down_revision = "0415_add_edit_reasons"


def upgrade():
    op.add_column("broadcast_message", sa.Column("extra_content", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "extra_content")

