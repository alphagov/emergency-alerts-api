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

    op.execute("DELETE FROM service_permissions WHERE permission = 'email'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'inbound_sms'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'international_letters'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'international_sms'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'letter'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'letters_as_pdf'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'schedule_notifications'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'sms'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'upload_document'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'upload_letters'")

    op.execute("DELETE FROM service_permission_types WHERE name = 'email'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'inbound_sms'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'international_letters'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'international_sms'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'letter'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'letters_as_pdf'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'schedule_notifications'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'sms'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'upload_document'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'upload_letters'")


def downgrade():
    pass
