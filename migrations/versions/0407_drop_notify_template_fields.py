"""

Revision ID: 0407_drop_notify_template_fields
Revises: 0406_drop_notify_service_fields
Create Date: 2024-10-30 16:56:00

"""

from alembic import op

revision = "0407_drop_notify_template_fields"
down_revision = "0406_drop_notify_service_fields"


def upgrade():
    op.drop_column("templates", "process_type")
    op.drop_column("templates", "hidden")
    op.drop_column("templates", "postage")

    op.drop_column("templates_history", "process_type")
    op.drop_column("templates_history", "hidden")
    op.drop_column("templates_history", "postage")

    op.drop_table("template_process_type")


def downgrade():
    pass
