"""

Revision ID: 0427_add_area_population_table
Revises: 0426_service_email_table
Create Date: 2026-05-21 14:35:00

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0427_add_area_population_table"
down_revision = "0426_service_email_table"


def upgrade():
    op.create_table(
        "populations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("geometry", Geometry("GEOMETRY", srid=4326), nullable=False),
        sa.Column("density", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_populations_id",
        "populations",
        ["id"],
    )
    op.create_index(
        "ix_populations_geometry",
        "populations",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade():
    op.drop_index("ix_populations_id", table_name="populations")
    op.drop_index("ix_populations_geometry", table_name="populations")
    op.drop_table("populations")
