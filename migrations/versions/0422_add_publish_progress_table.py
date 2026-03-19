"""

Revision ID: 0422_add_publish_progress_table
Revises: 0421_add_postgis_extension
Create Date: 2026-03-06 10:51:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0422_add_publish_progress_table"
down_revision = "0421_add_postgis_extension"


def upgrade():
    op.create_table(
        "publish_task_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("last_published_file", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_id"),
        "publish_task_progress",
        ["id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_task_id"),
        "publish_task_progress",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finished_at"),
        "publish_task_progress",
        ["finished_at"],
        unique=False,
    )


def downgrade():
    op.drop_table("publish_task_progress")