"""

Revision ID: 0426_service_email_table
Revises: 0425_remove_permission
Create Date: 2026-06-03 11:40:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0426_service_email_table"
down_revision = "0425_remove_permission"


def upgrade():
    op.create_table(
        "service_email",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("service_id", "email_address"),
    )


def downgrade():
    op.drop_table("service_email")
