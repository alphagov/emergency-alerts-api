"""

Revision ID: 0413_remove_old_service_code
Revises: 0411_broadcast_message_history
Create Date: 2025-03-24 11:16:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0413_remove_old_service_code"
down_revision = "0412_service_providers"


def upgrade():
    op.drop_table("service_broadcast_provider_restriction")
    op.drop_column("service_broadcast_settings", "provider")
    op.execute(
        """
        DELETE FROM broadcast_provider_types
        WHERE name IN ('all', 'deprecated')
        """
    )


def downgrade():
    pass
