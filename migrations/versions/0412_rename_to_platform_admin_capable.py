"""

Revision ID: 0412_rename_to_platform_admin_capable
Revises: 5206923870d3
Create Date: 2025-03-05 17:13:13.720166

"""

from alembic import op
import sqlalchemy as sa

revision = "0412_rename_to_platform_admin_capable"
down_revision = "5206923870d3"


def upgrade():
    op.add_column("users", sa.Column("platform_admin_capable", sa.Boolean(), nullable=False))
    op.add_column("users", sa.Column("platform_admin_expiry", sa.DateTime(), nullable=True))
    op.execute("UPDATE users SET platform_admin_capable = platform_admin")
    op.drop_column("users", "platform_admin")


def downgrade():
    op.add_column("users", sa.Column("platform_admin", sa.BOOLEAN(), autoincrement=False, nullable=False))
    op.execute("UPDATE users SET platform_admin = platform_admin_capable")
    op.drop_column("users", "platform_admin_expiry")
    op.drop_column("users", "platform_admin_capable")
