"""

Revision ID: 0404_drop_constraints
Revises: 0403_add_common_passwords_table
Create Date: 2024-10-30 16:56:00

"""

from alembic import op

revision = "0404_drop_constraints"
down_revision = "0403_add_common_passwords_table"


def upgrade():
    op.alter_column("services", "message_limit", nullable=True)
    op.alter_column("services_history", "message_limit", nullable=True)
    op.drop_constraint(op.f("services_email_from_key"), "services", type_="unique")
    op.alter_column("services", "email_from", nullable=True)
    op.alter_column("services_history", "email_from", nullable=True)
    op.alter_column("services", "research_mode", nullable=True)
    op.alter_column("services_history", "research_mode", nullable=True)
    op.alter_column("services", "prefix_sms", nullable=True)
    op.alter_column("services", "rate_limit", nullable=True)
    op.alter_column("services_history", "rate_limit", nullable=True)
    op.alter_column("services", "count_as_live", nullable=True)
    op.alter_column("services_history", "count_as_live", nullable=True)

    op.alter_column("templates", "process_type", nullable=True)
    op.alter_column("templates", "hidden", nullable=True)
    op.alter_column("templates_history", "process_type", nullable=True)
    op.alter_column("templates_history", "hidden", nullable=True)


def downgrade():
    pass
