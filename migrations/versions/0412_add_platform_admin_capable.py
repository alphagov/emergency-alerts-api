"""

Revision ID: 0412_add_platform_admin_capable
Revises: 5206923870d3
Create Date: 2025-03-05 17:13:13.720166

"""

from alembic import op
import sqlalchemy as sa

revision = "0412_add_platform_admin_capable"
down_revision = "5206923870d3"  # TODO: Fix for draft alerts


def upgrade():
    op.add_column("users", sa.Column("platform_admin_capable", sa.Boolean()))
    op.execute("UPDATE users SET platform_admin_capable = platform_admin")
    op.alter_column("users", "platform_admin_capable", nullable=False)

    op.add_column("users", sa.Column("platform_admin_redeemable", sa.Boolean()))
    op.execute("UPDATE users SET platform_admin_redeemable = false")
    op.alter_column("users", "platform_admin_redeemable", nullable=False)

    op.add_column("users", sa.Column("platform_admin_expiry", sa.DateTime(), nullable=True))
    op.drop_column("users", "platform_admin")


def downgrade():
    op.add_column("users", sa.Column("platform_admin", sa.Boolean()))
    op.execute("UPDATE users SET platform_admin = platform_admin_capable")
    op.alter_column("users", "platform_admin", nullable=False)
    op.drop_column("users", "platform_admin_expiry")
    op.drop_column("users", "platform_admin_capable")
    op.drop_column("users", "platform_admin_redeemable")
