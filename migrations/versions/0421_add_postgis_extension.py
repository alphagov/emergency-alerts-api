"""

Revision ID: 0421_add_postgis_extension
Revises: 0420_add_default_template_areas
Create Date: 2025-09-10 15:51:00

"""

from alembic import op

revision = "0421_add_postgis_extension"
down_revision = "0420_add_default_template_areas"


def upgrade():
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS postgis
        """)


def downgrade():
    op.execute("""
        DROP EXTENSION IF EXISTS postgis
        """)
