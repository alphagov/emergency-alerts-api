"""

Revision ID: 0410_broadcast_message_history
Revises: 0409_add_rejected_by_api_col
Create Date: 2025-01-30 10:00:00

"""

# revision identifiers, used by Alembic.
revision = "0410_broadcast_message_history"
down_revision = "0409_add_rejected_by_api_col"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "broadcast_message_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("areas", postgresql.JSONB(none_as_null=True, astext_type=sa.Text())),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.create_index(
        op.f("ix_broadcast_message_history_created_by_id"), "broadcast_message_history", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_broadcast_message_history_service_id"), "broadcast_message_history", ["service_id"], unique=False
    )

    op.execute(
        (
            """INSERT INTO broadcast_message_history (id, reference, created_at, updated_at,
            content, service_id, version, created_by_id)
             SELECT id, reference, created_at, updated_at, content, service_id, 1, created_by_id FROM broadcast_message"""
        )
    )

    op.alter_column("broadcast_message_history", "created_at", nullable=False)
    op.alter_column("broadcast_message_history", "created_by_id", nullable=False)
    op.alter_column("broadcast_message_history", "version", nullable=False)


def downgrade():
    op.drop_index(op.f("ix_broadcast_message_history_service_id"), table_name="broadcast_message_history")
    op.drop_index(op.f("ix_broadcast_message_history_created_by_id"), table_name="broadcast_message_history")
    op.drop_table("broadcast_message_history")
