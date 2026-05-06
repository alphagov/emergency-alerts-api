"""

Revision ID: 0424_route_advisor_table
Revises: 0423_provider_message_status
Create Date: 2026-04-23 13:45:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0424_route_advisor_table"
down_revision = "0423_provider_message_status"


def upgrade():
    op.create_table(
        "route_advisor",
        sa.Column("mno", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("mno"),
        sa.Column("proxy", sa.String(length=255), nullable=True),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("route_advisor")
