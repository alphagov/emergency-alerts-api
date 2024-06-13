"""

Revision ID: 0397_drop_providers
Revises: 0396_drop_complaints
Create Date: 2024-05-10 10:00:00

"""

from alembic import op

revision = "0397_drop_providers"
down_revision = "0396_drop_complaints"


def upgrade():
    op.drop_table("provider_details")
    op.drop_table("provider_details_history")


def downgrade():
    pass
