"""

Revision ID: 0389_org_to_emergency_alerts
Revises: 0388_populate_letter_branding
Create Date: 2023-06-23 17:14:12:01.094412

"""

from alembic import op
from sqlalchemy.sql import text

revision = "0389_org_to_emergency_alerts"
down_revision = "0388_populate_letter_branding"

organisation_id = "38e4bf69-93b0-445d-acee-53ea53fe02df"


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text("""
            UPDATE
                organisation
            SET
                name = 'Emergency Alerts'
            WHERE
                id = :id
        """),
        {"id": organisation_id},
    )


def downgrade():
    pass
