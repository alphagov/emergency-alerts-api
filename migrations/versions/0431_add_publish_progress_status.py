"""

Revision ID: 0431_add_publish_progress_status
Revises: 0430_add_bpm_err_retry_exhausted
Create Date: 2026-10-30 11:13:13.720166

"""

import sqlalchemy as sa
from alembic import op

revision = "0431_add_publish_progress_status"
down_revision = "0430_add_bpm_err_retry_exhausted"


def upgrade():
    op.add_column("publish_task_progress", sa.Column("trace_id", sa.String(), nullable=True))

    status_enum = sa.Enum(
        "pending",
        "processing",
        "finished",
        name="publish_task_progress_status_types",
    )
    status_enum.create(op.get_bind())
    op.add_column(
        "publish_task_progress",
        sa.Column(
            "status",
            status_enum,
            nullable=True,  # Overridden after updating
        ),
    )
    op.execute("UPDATE publish_task_progress SET status = 'finished'")
    op.alter_column("publish_task_progress", "status", nullable=False)


def downgrade():
    op.drop_column("publish_task_progress", "trace_id")
    op.drop_column("publish_task_progress", "status")
    op.execute("drop type publish_task_progress_status_types")
