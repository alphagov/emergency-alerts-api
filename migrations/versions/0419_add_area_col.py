"""

Revision ID: 0419_add_area_col
Revises: 0418_add_message_exclude_col
Create Date: 2025-08-06 16:23:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0419_add_area_col"
down_revision = "0418_add_message_exclude_col"


def upgrade():
    op.alter_column("templates", "name", nullable=False, new_column_name="reference")
    op.alter_column("templates_history", "name", nullable=False, new_column_name="reference")
    op.add_column("templates", sa.Column("areas", postgresql.JSONB(none_as_null=True, astext_type=sa.Text())))
    op.add_column("templates_history", sa.Column("areas", postgresql.JSONB(none_as_null=True, astext_type=sa.Text())))


def downgrade():
    op.alter_column("templates", "reference", nullable=False, new_column_name="name")
    op.alter_column("templates_history", "reference", nullable=False, new_column_name="name")
    op.drop_column("templates_history", "areas")
    op.drop_column("templates", "areas")
