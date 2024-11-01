"""

Revision ID: 0390_remove_default_service
Revises: 0389_org_to_emergency_alerts
Create Date: 2023-06-29 12:43:12:01.094412

"""

from alembic import op
from sqlalchemy.sql import text

revision = "0390_remove_default_service"
down_revision = "0389_org_to_emergency_alerts"

service_id = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"


def upgrade():
    conn = op.get_bind()

    conn.execute(
        text(
            """
            DELETE FROM
                annual_billing
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                service_email_reply_to
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                service_permissions
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                service_sms_senders
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                services_history
            WHERE
                id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                templates_history
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                user_to_service
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                template_redacted
            WHERE
                template_id IN (
                    SELECT template_id
                    FROM templates
                    WHERE service_id = :id
                )
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                templates
            WHERE
                service_id = :id
        """
        ),
        {"id": service_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM
                services
            WHERE
                id = :id
        """
        ),
        {"id": service_id},
    )


def downgrade():
    pass
