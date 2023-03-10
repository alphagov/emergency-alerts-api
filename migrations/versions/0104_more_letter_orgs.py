"""empty message

Revision ID: 0104_more_letter_orgs
Revises: 0103_add_historical_redact
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = "0104_more_letter_orgs"
down_revision = "0103_add_historical_redact"

import sqlalchemy as sa
from alembic import op
from flask import current_app
from sqlalchemy.dialects import postgresql


def upgrade():
    op.execute(
        """
        INSERT INTO dvla_organisation VALUES
        ('003', 'Department for Work and Pensions'),
        ('004', 'Government Equalities Office')
    """
    )


def downgrade():
    # data migration, no downloads
    pass
