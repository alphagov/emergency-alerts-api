"""

Revision ID: 0406_drop_notify_service_fields
Revises: 0405_drop_notify_org_fields
Create Date: 2024-10-30 16:56:00

"""

from alembic import op

revision = "0406_drop_notify_service_fields"
down_revision = "0405_drop_notify_org_fields"


def upgrade():
    op.drop_column("services", "message_limit")
    op.drop_column("services", "email_from")
    op.drop_column("services", "research_mode")
    op.drop_column("services", "prefix_sms")
    op.drop_column("services", "rate_limit")
    op.drop_column("services", "contact_link")
    op.drop_column("services", "consent_to_research")
    op.drop_column("services", "volume_email")
    op.drop_column("services", "volume_letter")
    op.drop_column("services", "volume_sms")
    op.drop_column("services", "count_as_live")
    op.drop_column("services", "billing_contact_email_addresses")
    op.drop_column("services", "billing_contact_names")
    op.drop_column("services", "billing_reference")
    op.drop_column("services", "purchase_order_number")

    op.drop_column("services_history", "message_limit")
    op.drop_column("services_history", "email_from")
    op.drop_column("services_history", "research_mode")
    op.drop_column("services_history", "prefix_sms")
    op.drop_column("services_history", "rate_limit")
    op.drop_column("services_history", "contact_link")
    op.drop_column("services_history", "consent_to_research")
    op.drop_column("services_history", "volume_email")
    op.drop_column("services_history", "volume_letter")
    op.drop_column("services_history", "volume_sms")
    op.drop_column("services_history", "count_as_live")
    op.drop_column("services_history", "billing_contact_email_addresses")
    op.drop_column("services_history", "billing_contact_names")
    op.drop_column("services_history", "billing_reference")
    op.drop_column("services_history", "purchase_order_number")


def downgrade():
    pass
