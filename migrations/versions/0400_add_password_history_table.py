"""

Revision ID: 0400_add_password_history_table
Revises: 0399_change_feature_toggles_text
Create Date: 2024-09-20 14:30:13.653208

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0400_add_password_history_table"
down_revision = "0399_change_feature_toggles_text"


def upgrade():
    op.create_table(
        "password_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("_password", sa.String(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_user_id"),
        "password_history",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password"),
        "password_history",
        ["_password"],
        unique=False,
    )


def downgrade():
    op.drop_table("password_history")