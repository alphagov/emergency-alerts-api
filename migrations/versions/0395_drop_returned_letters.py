"""

Revision ID: 0395_drop_returned_letters
Revises: 0394_drop_inbound
Create Date: 2024-05-10 10:00:00

"""

from alembic import op

revision = "0395_drop_returned_letters"
down_revision = "0394_drop_inbound"


def upgrade():
    op.drop_table("returned_letters")


def downgrade():
    pass
