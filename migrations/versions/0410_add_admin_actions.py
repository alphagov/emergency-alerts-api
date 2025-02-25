"""

Revision ID: 5206923870d3
Revises: 0409_add_rejected_by_api_col
Create Date: 2025-02-07 13:03:27.866070

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "5206923870d3"
down_revision = "0409_add_rejected_by_api_col"


def upgrade():
    op.create_table(
        "admin_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum("invite_user", "edit_permissions", "create_api_key", name="admin_action_types"),
            nullable=False,
        ),
        sa.Column("action_data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "invalidated", name="admin_action_status_types"),
            nullable=False,
        ),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_actions_created_by_id"), "admin_actions", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_admin_actions_reviewed_by_id"), "admin_actions", ["reviewed_by_id"], unique=False)
    op.create_index(op.f("ix_admin_actions_service_id"), "admin_actions", ["service_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_admin_actions_service_id"), table_name="admin_actions")
    op.drop_index(op.f("ix_admin_actions_reviewed_by_id"), table_name="admin_actions")
    op.drop_index(op.f("ix_admin_actions_created_by_id"), table_name="admin_actions")
    op.drop_table("admin_actions")
