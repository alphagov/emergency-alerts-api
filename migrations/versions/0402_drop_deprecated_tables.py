"""

Revision ID: 0402_drop_deprecated_tables
Revises: 0401_drop_job_tables
Create Date: 2024-10-30 16:56:00

"""

from alembic import op

revision = "0402_drop_deprecated_tables"
down_revision = "0401_drop_job_tables"


def upgrade():
    op.drop_table("annual_billing")
    op.drop_table("daily_sorted_letter")
    op.drop_table("inbound_sms")
    op.drop_table("inbound_sms_history")
    op.drop_table("letter_rates")
    op.drop_table("rates")
    op.drop_table("service_contact_list")
    op.drop_table("service_data_retention")
    op.drop_table("service_email_reply_to")

    op.drop_table("template_redacted")
    op.drop_column("templates", "service_letter_contact_id")
    op.drop_column("templates_history", "service_letter_contact_id")

    op.drop_table("service_letter_contacts")
    op.drop_table("service_whitelist")


def downgrade():
    pass
