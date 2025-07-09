"""

Revision ID: 0416_add_govuk_acknowledged
Revises: 0415_add_edit_reasons
Create Date: 2025-03-05 17:13:13.720166

"""

from alembic import op
import sqlalchemy as sa

revision = "0416_add_govuk_acknowledged"
down_revision = "0415_add_edit_reasons"


def upgrade():
    op.add_column("broadcast_message", sa.Column("finished_govuk_acknowledged", sa.Boolean(), default=False))
    op.execute("UPDATE broadcast_message SET finished_govuk_acknowledged = true")
    op.alter_column("broadcast_message", "finished_govuk_acknowledged", nullable=False)


def downgrade():
    op.drop_column("broadcast_message", "finished_govuk_acknowledged")
