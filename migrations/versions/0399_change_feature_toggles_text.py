"""

Revision ID: 0399_change_feature_toggles_text
Revises: 0398_add_failed_logins_table
Create Date: 2024-08-20 15:31:10.657408

"""

from alembic import op

revision = "0399_change_feature_toggles_text"
down_revision = "0398_add_failed_logins_table"


def upgrade():
    op.execute("DELETE FROM feature_toggles where name = 'service_is_not_live'")
    op.execute(
        "INSERT INTO feature_toggles \
            (name, is_enabled, display_html) \
        VALUES \
            ('service_is_not_live', false, \
                'This is a trial mode service......')"
    )


def downgrade():
    op.execute("DELETE FROM feature_toggles where name = 'service_is_not_live'")
    op.execute(
        "INSERT INTO feature_toggles \
            (name, is_enabled, display_html) \
        VALUES \
            ('service_is_not_live', false, \
                'This service is currently not live. You cannot send alerts out to the public.')"
    )
