"""

Revision ID: 0423_route_advisor_table
Revises: 0422_add_publish_progress_table
Create Date: 2026-04-23 13:45:00

"""

import sqlalchemy as sa
from alembic import op

revision = "0423_route_advisor_table"
down_revision = "0422_add_publish_progress_table"

PROVIDER_TYPES = ("ee", "o2", "three", "vodafone")


def upgrade():
    op.create_table(
        "route_advisor",
        sa.Column("mno", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("mno"),
        sa.Column("proxy", sa.String(length=255), nullable=True),
        sa.Column("target", sa.String(length=255), nullable=True)
    )
    for provider in PROVIDER_TYPES:
        op.execute(f"INSERT INTO route_advisor VALUES ('{provider}', 'primary', 'a')")


def downgrade():
    op.drop_table("route_advisor")
