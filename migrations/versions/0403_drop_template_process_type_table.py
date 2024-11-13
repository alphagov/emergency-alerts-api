"""

Revision ID: 0403_drop_template_process_type_table
Revises: 0402_drop_deprecated_tables
Create Date: 2024-10-30 16:56:00

"""

from alembic import op

revision = "0403_drop_template_process_type_table"
down_revision = "0402_drop_deprecated_tables"


def upgrade():
    op.drop_table("template_process_type")


def downgrade():
    pass
