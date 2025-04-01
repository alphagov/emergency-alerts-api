"""

Revision ID: 0412_add_platform_admin_capable
Revises: 0411_broadcast_message_history
Create Date: 2025-03-05 17:13:13.720166

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0412_add_platform_admin_capable"
down_revision = "0411_broadcast_message_history"


def upgrade():
    op.add_column("users", sa.Column("platform_admin_capable", sa.Boolean()))
    op.execute("UPDATE users SET platform_admin_capable = platform_admin")
    op.alter_column("users", "platform_admin_capable", nullable=False)

    op.add_column("users", sa.Column("platform_admin_redemption", sa.DateTime(), nullable=True))
    op.drop_column("users", "platform_admin")

    op.alter_column("admin_actions", "service_id", existing_type=postgresql.UUID(), nullable=True)

    # We can't easily drop the enum in a downgrade so just make it idempotent
    op.execute("ALTER TYPE admin_action_types ADD VALUE IF NOT EXISTS 'elevate_platform_admin'")


def downgrade():
    op.add_column("users", sa.Column("platform_admin", sa.Boolean()))
    op.execute("UPDATE users SET platform_admin = platform_admin_capable")
    op.alter_column("users", "platform_admin", nullable=False)
    op.drop_column("users", "platform_admin_redemption")
    op.drop_column("users", "platform_admin_capable")
    op.alter_column("admin_actions", "service_id", existing_type=postgresql.UUID(), nullable=False)
