"""

Revision ID: 0430_add_bpm_err_retry_exhausted
Revises: 0429_unescape_message_content
Create Date: 2026-07-20 14:07:25.230919

"""

from alembic import op

revision = "0430_add_bpm_err_retry_exhausted"
down_revision = "0429_unescape_message_content"


def upgrade():
    op.execute("ALTER TYPE broadcast_provider_message_status_types ADD VALUE 'returned-error-retry-exhausted'")


def downgrade():
    # Postgres doesn't support removing from enums natively
    pass
