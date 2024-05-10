"""

Revision ID: 0394_drop_inbound
Revises: 0393_drop_branding
Create Date: 2024-05-10 10:00:00

"""

from alembic import op

revision = "0394_drop_inbound"
down_revision = "0393_drop_branding"


def upgrade():
    op.drop_table("service_sms_senders")
    op.drop_table("inbound_numbers")


def downgrade():
    pass
