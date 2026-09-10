"""

Revision ID: 0431_adjust_area_tables.py
Revises: 0430_add_bpm_err_retry_exhausted
Create Date: 2026-08-05 14:22:30

"""

import uuid

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0431_adjust_area_tables.py"
down_revision = "0430_add_bpm_err_retry_exhausted"


def upgrade():
    # Clearing all existing data to add the new column
    op.execute("DELETE FROM geography_polygons")
    op.execute("DELETE FROM geography_version")
    op.execute("DELETE FROM geography_type")

    # How a single area from this library is referred to in Admin application
    op.add_column("geography_type", sa.Column("name_singular", sa.Text(), nullable=True))

    op.drop_table("geography_polygons")

    op.create_table(
        "geography_polygons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4),
        #  Office for National Statistics (ONS) and Government Statistical Service (GSS) code for the area e.g. England's is E92000001
        sa.Column("geographic_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("geometry", Geometry("GEOMETRY", srid=4326), nullable=False),
        sa.Column("parent_geography_id", sa.String(), nullable=True),
        sa.Column("geography_version_id", sa.String(), nullable=False),
        # Stored for optimisation purposes - not strictly necessary as we can retrieve
        # geography_type_id from geography_version relation in first instance
        sa.Column("geography_type_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["geography_version_id"],
            ["geography_version.id"],
        ),
        sa.ForeignKeyConstraint(
            ["geography_type_id"],
            ["geography_type.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geography_polygons_id",
        "geography_polygons",
        ["id"],
    )
    op.create_index(
        "ix_geography_polygons_geographic_id",
        "geography_polygons",
        ["geographic_id"],
    )
    op.create_index(
        "ix_geography_polygons_name",
        "geography_polygons",
        ["name"],
    )
    op.create_index(
        "ix_geography_polygons_parent_geography_id",
        "geography_polygons",
        ["parent_geography_id"],
    )
    op.create_index(
        "ix_geography_polygons_geography_version_id",
        "geography_polygons",
        ["geography_version_id"],
    )
    op.create_index(
        "ix_geography_polygons_geography_type_id",
        "geography_polygons",
        ["geography_type_id"],
    )
    op.create_index(
        "ix_geography_polygons_geometry",
        "geography_polygons",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade():
    # Dropping everything related to geography_polygons table before we re-add with adjustments
    op.drop_column("geography_type", "name_singular")
    op.drop_table("geography_polygons")

    op.create_table(
        "geography_polygons",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("geometry", Geometry("GEOMETRY", srid=4326), nullable=False),
        sa.Column("parent_geography_id", sa.String(), nullable=True),
        sa.Column("geography_version_id", sa.String(), nullable=False),
        # Stored for optimisation purposes - not strictly necessary as we can retrieve
        # geography_type_id from geography_version relation in first instance
        sa.Column("geography_type_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["geography_version_id"],
            ["geography_version.id"],
        ),
        sa.ForeignKeyConstraint(
            ["geography_type_id"],
            ["geography_type.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geography_polygons_id",
        "geography_polygons",
        ["id"],
    )
    op.create_index(
        "ix_geography_polygons_name",
        "geography_polygons",
        ["name"],
    )
    op.create_index(
        "ix_geography_polygons_parent_geography_id",
        "geography_polygons",
        ["parent_geography_id"],
    )
    op.create_index(
        "ix_geography_polygons_geography_version_id",
        "geography_polygons",
        ["geography_version_id"],
    )
    op.create_index(
        "ix_geography_polygons_geography_type_id",
        "geography_polygons",
        ["geography_type_id"],
    )
    op.create_index(
        "ix_geography_polygons_geometry",
        "geography_polygons",
        ["geometry"],
        postgresql_using="gist",
    )
