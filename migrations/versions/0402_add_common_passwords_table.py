"""

Revision ID: 0402_add_common_passwords_table
Revises: 0401_drop_job_tables
Create Date: 2024-10-31 11:33:35

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0402_add_common_passwords_table"
down_revision = "0401_drop_job_tables"


def upgrade():
    op.create_table(
        "common_passwords",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_password"),
        "common_passwords",
        ["password"],
        unique=False,
    )


def downgrade():
    op.drop_table("common_passwords")
