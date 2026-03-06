"""

Revision ID: 0420_add_default_template_areas
Revises: 0419_add_area_col
Create Date: 2025-09-10 12:04:00

"""

from alembic import op

revision = "0420_add_default_template_areas"
down_revision = "0419_add_area_col"


def upgrade():
    op.execute("""
        UPDATE templates
        SET areas = '{}'
        WHERE areas IS NULL;
    """)
    op.execute("""
        UPDATE templates_history
        SET areas = '{}'
        WHERE areas IS NULL;
    """)


def downgrade():
    # This is a patch to 0419 which breaks old templates (areas previously were empty but
    # should default to "{}") - we don't want to revert this without downgrading 0419 entirely
    pass
