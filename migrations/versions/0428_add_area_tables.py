"""

Revision ID: 0428_add_area_tables
Revises: 0427_add_area_population_table
Create Date: 2026-06-16 15:28:00

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0428_add_area_tables"
down_revision = "0427_add_area_population_table"


def upgrade():
    # Stores the different geography types, i.e. country, county and unitary
    # authority, local authority district etc
    op.create_table(
        "geography_type",
        sa.Column("id", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("route", sa.String(), nullable=True, unique=True),
    )
    op.create_index(
        "ix_geography_type_id",
        "geography_type",
        ["id"],
    )
    op.create_index(
        "ix_geography_type_name",
        "geography_type",
        ["name"],
    )
    op.create_index(
        "ix_geography_type_route",
        "geography_type",
        ["route"],
    )

    # Stores the different versions, for each geography type, with the source
    # URL and state (draft, live, deprecated)
    op.create_table(
        "geography_version",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("geography_type_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["geography_type_id"], ["geography_type.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geography_version_geography_type_id",
        "geography_version",
        ["geography_type_id"],
    )
    op.create_index(
        "ix_geography_version_version",
        "geography_version",
        ["version"],
    )
    op.create_index(
        "ix_geography_version_state",
        "geography_version",
        ["state"],
    )

    # Stores the WKT area for each geography item, as well as parent geography,
    # geography version and geography type
    op.create_table(
        "geography_polygons",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("geometry", Geometry("GEOMETRY", srid=4326), nullable=False),
        sa.Column("parent_geography_id", sa.String(), nullable=True),
        sa.Column("geography_version_id", sa.String(), nullable=False),
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


def downgrade():
    op.drop_index("ix_geography_polygons_geometry", table_name="geography_polygons")
    op.drop_index("ix_geography_polygons_geography_type_id", table_name="geography_polygons")
    op.drop_index("ix_geography_polygons_geography_version_id", table_name="geography_polygons")
    op.drop_index("ix_geography_polygons_parent_geography_id", table_name="geography_polygons")
    op.drop_index("ix_geography_polygons_name", table_name="geography_polygons")
    op.drop_index("ix_geography_polygons_id", table_name="geography_polygons")

    op.drop_index("ix_geography_version_state", table_name="geography_version")
    op.drop_index("ix_geography_version_version", table_name="geography_version")
    op.drop_index("ix_geography_version_geography_type_id", table_name="geography_version")

    op.drop_index("ix_geography_type_route", table_name="geography_type")
    op.drop_index("ix_geography_type_name", table_name="geography_type")
    op.drop_index("ix_geography_type_id", table_name="geography_type")

    op.drop_table("geography_polygons")
    op.drop_table("geography_version")
    op.drop_table("geography_type")
