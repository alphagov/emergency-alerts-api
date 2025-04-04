"""

Revision ID: 0412_service_providers
Revises: 0411_broadcast_message_history
Create Date: 2025-03-24 11:16:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0412_service_providers"
down_revision = "0411_broadcast_message_history"


def upgrade():
    op.create_table(
        "service_broadcast_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["provider"],
            ["broadcast_provider_types.name"],
        ),
    )
    op.execute(
        """
        INSERT INTO broadcast_provider_types
        SELECT 'deprecated'
        """
    )


def downgrade():
    op.drop_table("service_broadcast_providers")
    op.execute(
        """
        DELETE FROM broadcast_provider_types
        WHERE name = 'deprecated'
        """
    )
