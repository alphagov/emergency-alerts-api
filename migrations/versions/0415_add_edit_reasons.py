"""

Revision ID: 0415_add_edit_reasons
Revises: 0414_add_platform_admin_capable
Create Date: 2025-04-30 16:30:00

"""

# revision identifiers, used by Alembic.
revision = "0415_add_edit_reasons"
down_revision = "0414_add_platform_admin_capable"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.execute("delete from broadcast_message where status = 'draft'")
    op.create_table(
        "broadcast_message_edit_reasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broadcast_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edit_reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
        ),
    )
    op.create_index(
        op.f("ix_broadcast_message_edit_reasons_created_by_id"),
        "broadcast_message_edit_reasons",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broadcast_message_edit_reasons_submitted_by_id"),
        "broadcast_message_edit_reasons",
        ["submitted_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broadcast_message_edit_reasons_service_id"),
        "broadcast_message_edit_reasons",
        ["service_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_broadcast_message_edit_reasons_service_id"), table_name="broadcast_message_edit_reasons")
    op.drop_index(op.f("ix_broadcast_message_edit_reasons_created_by_id"), table_name="broadcast_message_edit_reasons")
    op.drop_index(
        op.f("ix_broadcast_message_edit_reasons_submitted_by_id"), table_name="broadcast_message_edit_reasons"
    )
    op.drop_table("broadcast_message_edit_reasons")
