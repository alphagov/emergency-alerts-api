"""

Revision ID: 0391_add_feature_toggles_table
Revises: 0390_remove_default_service
Create Date: 2023-07-18 12:21:02:01.084361

"""

import sqlalchemy as sa
from alembic import op

revision = "0391_add_feature_toggles_table"
down_revision = "0390_remove_default_service"


def upgrade():
    op.create_table(
        "feature_toggles",
        sa.Column("name", sa.String(length=255)),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("display_html", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("name"),
    )

    op.execute("INSERT INTO feature_toggles \
            (name, is_enabled, display_html) \
        VALUES \
            ('service_is_not_live', false, \
                'This service is currently not live. You cannot send alerts out to the public.')")


def downgrade():
    pass
