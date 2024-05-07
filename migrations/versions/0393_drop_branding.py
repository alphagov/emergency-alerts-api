"""

Revision ID: 0393_drop_branding
Revises: 0392_add_alert_duration
Create Date: 2024-05-07 11:53:00

"""

from alembic import op

revision = "0393_drop_branding"
down_revision = "0392_add_alert_duration"


def upgrade():
    op.drop_table("service_email_branding")
    op.drop_table("email_branding_to_organisation")
    op.drop_table("service_letter_branding")
    op.drop_table("letter_branding_to_organisation")

    op.drop_constraint("fk_organisation_email_branding_id", "organisation", type_="foreignkey")
    op.drop_column("organisation", "email_branding_id")
    op.drop_constraint("fk_organisation_letter_branding_id", "organisation", type_="foreignkey")
    op.drop_column("organisation", "letter_branding_id")

    op.drop_table("email_branding")
    op.drop_table("letter_branding")

    op.drop_table("branding_type")

def downgrade():
    pass
