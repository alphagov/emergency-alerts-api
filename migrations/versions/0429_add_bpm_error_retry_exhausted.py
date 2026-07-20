"""

Revision ID: 0429_add_bpm_error_retry_exhausted
Revises: 0428_add_area_tables
Create Date: 2026-07-20 14:07:25.230919

"""
from alembic import op

revision = '0429_add_bpm_error_retry_exhausted'
down_revision = '0428_add_area_tables'


def upgrade():
    op.execute("ALTER TYPE broadcast_provider_message_status_types ADD VALUE 'returned-error-retry-exhausted'")


def downgrade():
   # Postgres doesn't support removing from enums
   pass
