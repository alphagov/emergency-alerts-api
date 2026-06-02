"""

Revision ID: 0425_remove_permission
Revises: 0424_route_advisor_table
Create Date: 2026-05-28 11:20:00

"""

from alembic import op

revision = "0425_remove_permission"
down_revision = "0424_route_advisor_table"


def upgrade():
    op.execute("DELETE FROM permissions WHERE permission = 'manage_settings'")


def downgrade():
    # Permission cannot be re-added as we don't know which rows have been deleted
    pass
