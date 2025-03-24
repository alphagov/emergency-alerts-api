"""

Revision ID: 0411_service_providers
Revises: 0410_add_admin_actions
Create Date: 2025-03-24 11:16:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0411_service_providers"
down_revision = "0410_add_admin_actions"


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
    op.drop_column("service_broadcast_settings", "provider")
    op.drop_table("service_broadcast_provider_restriction")

    sql = """
        delete broadcast_provider_types
        where name = 'all'
        """
    conn = op.get_bind()
    conn.execute(sql)


def downgrade():
    op.drop_table("service_broadcast_providers")
