"""

Revision ID: 0405_drop_notify_org_fields
Revises: 0404_drop_constraints
Create Date: 2024-12-02 10:00:00

"""

from alembic import op

revision = "0405_drop_notify_org_fields"
down_revision = "0404_drop_constraints"


def upgrade():
    op.drop_column("organisation", "agreement_signed")
    op.drop_column("organisation", "agreement_signed_at")
    op.drop_column("organisation", "agreement_signed_by_id")
    op.drop_column("organisation", "agreement_signed_version")
    op.drop_column("organisation", "request_to_go_live_notes")
    op.drop_column("organisation", "agreement_signed_on_behalf_of_email_address")
    op.drop_column("organisation", "agreement_signed_on_behalf_of_name")
    op.drop_column("organisation", "billing_contact_email_addresses")
    op.drop_column("organisation", "billing_contact_names")
    op.drop_column("organisation", "billing_reference")
    op.drop_column("organisation", "purchase_order_number")

    op.drop_column("organisation_types", "annual_free_sms_fragment_limit")


def downgrade():
    pass
