"""

Revision ID: 0392_add_alert_duration
Revises: 0391_add_feature_toggles_table
Create Date: 2023-08-09 16:20:15:09.012062

"""

import sqlalchemy as sa
from alembic import op

revision = "0392_add_alert_duration"
down_revision = "0391_add_feature_toggles_table"


def upgrade():
    op.add_column("broadcast_message", sa.Column("duration", sa.Interval(), nullable=True))


def downgrade():
    pass
