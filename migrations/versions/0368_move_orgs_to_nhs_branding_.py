"""

Revision ID: 0368_move_orgs_to_nhs_branding
Revises: 0367_add_reach
Create Date: 2022-04-12 18:22:12.069016

"""
from alembic import op

revision = "0368_move_orgs_to_nhs_branding"
down_revision = "0367_add_reach"


def upgrade():
    op.execute(
        """
        UPDATE
            organisation
        SET
            email_branding_id = 'a7dc4e56-660b-4db7-8cff-12c37b12b5ea'
        WHERE
            organisation_type IN ('nhs_central', 'nhs_local', 'nhs_gp')
        AND
            email_branding_id IS NULL
    """
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###
