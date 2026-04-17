"""

Revision ID: 0423_provider_message_status
Revises: 0422_add_publish_progress_table
Create Date: 2026-04-16 12:27:04.628384

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0423_provider_message_status"
down_revision = "0422_add_publish_progress_table"


def upgrade():
    op.execute("create sequence broadcast_provider_message_status_seq")
    op.create_table(
        "broadcast_provider_message_status",
        sa.Column(
            "id",
            sa.Integer(),
            server_default=sa.text("nextval('broadcast_provider_message_status_seq')"),
            nullable=False,
        ),
        sa.Column("broadcast_provider_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "technical-failure",
                "sending",
                "returned-ack",
                "returned-error",
                name="broadcast_provider_message_status_types",
            ),
            nullable=False,
        ),
        sa.Column("error_detail", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["broadcast_provider_message_id"],
            ["broadcast_provider_message.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # In the 'old' world broadcast_provider_message has a status that gets overwritten
    # We'll use its created_at date to create a pending status row, and then it's updated_at
    # to create a relevant status row of what it is now.
    op.execute(
        """
        INSERT INTO broadcast_provider_message_status
            (broadcast_provider_message_id, status, created_at)
        SELECT id, 'sending', created_at
        FROM broadcast_provider_message
    """
    )
    op.execute(
        """
        INSERT INTO broadcast_provider_message_status
            (broadcast_provider_message_id, status, created_at)
        SELECT id, status::broadcast_provider_message_status_types, updated_at
        FROM broadcast_provider_message
        WHERE updated_at IS NOT NULL
    """
    )

    op.drop_table("broadcast_provider_message_status_type")
    op.drop_column("broadcast_provider_message", "updated_at")
    op.drop_column("broadcast_provider_message", "status")


def downgrade():
    op.add_column("broadcast_provider_message", sa.Column("status", sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column(
        "broadcast_provider_message",
        sa.Column("updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    )

    op.execute("UPDATE broadcast_provider_message SET updated_at = created_at")
    # Get the latest status and use that to backfill the old column
    op.execute(
        """
            UPDATE broadcast_provider_message bpm
            SET status = s.status::varchar
            FROM (
                SELECT DISTINCT ON (broadcast_provider_message_id)
                    broadcast_provider_message_id,
                    status
                FROM broadcast_provider_message_status
                ORDER BY broadcast_provider_message_id, created_at DESC
            ) s
            WHERE bpm.id = s.broadcast_provider_message_id;
    """
    )

    op.drop_table("broadcast_provider_message_status")
    op.execute("drop sequence broadcast_provider_message_status_seq")
    op.execute("drop type broadcast_provider_message_status_types")

    # This table was never used for anything, so no need to put data in it...
    op.create_table(
        "broadcast_provider_message_status_type",
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
