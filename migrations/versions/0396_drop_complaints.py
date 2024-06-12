"""

Revision ID: 0396_drop_complaints
Revises: 0395_drop_returned_letters
Create Date: 2024-05-10 10:00:00

"""

from alembic import op

revision = "0396_drop_complaints"
down_revision = "0395_drop_returned_letters"


def upgrade():
    op.drop_table("complaints")


def downgrade():
    pass
