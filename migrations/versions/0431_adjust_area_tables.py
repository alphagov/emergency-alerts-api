"""

Revision ID: 0431_adjust_area_tables.py
Revises: 0430_add_bpm_err_retry_exhausted
Create Date: 2026-08-05 14:22:30

"""

import sqlalchemy as sa
from alembic import op
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

    #  geographic_id stores the Office for National Statistics (ONS) and Government 
    # Statistical Service (GSS) code for the area
    op.add_column(
        "geography_polygons",
        sa.Column("geographic_id", sa.String(), nullable=False),
    )

    # Drop the existing foreign keys before changing the geography_type 
    # and geography_version ID column types to uuid
    op.drop_constraint(
        "geography_version_geography_type_id_fkey",
        "geography_version",
        type_="foreignkey",
    )
    op.drop_constraint(
        "geography_polygons_geography_type_id_fkey",
        "geography_polygons",
        type_="foreignkey",
    )
    op.drop_constraint(
        "geography_polygons_geography_version_id_fkey",
        "geography_polygons",
        type_="foreignkey",
    )

    # geography_type id type becomes uuid
    op.alter_column(
        "geography_type",
        "id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="id::uuid",
    )
    # geography_type_id type becomes uuid
    op.alter_column(
        "geography_version",
        "geography_type_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="geography_type_id::uuid",
    )
    op.alter_column(
        "geography_polygons",
        "geography_type_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="geography_type_id::uuid",
    )

    # geography_version id type becomes uuid
    op.alter_column(
        "geography_version",
        "id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="id::uuid",
    )
    # geography_version_id type becomes uuid
    op.alter_column(
        "geography_polygons",
        "geography_version_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="geography_version_id::uuid",
    )

    # geography_polygons id type becomes uuid
    op.alter_column(
        "geography_polygons",
        "id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="id::uuid",
    )

    # Adds back foreign keys and relevant index
    op.create_foreign_key(
        "geography_version_geography_type_id_fkey",
        "geography_version",
        "geography_type",
        ["geography_type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "geography_polygons_geography_version_id_fkey",
        "geography_polygons",
        "geography_version",
        ["geography_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "geography_polygons_geography_type_id_fkey",
        "geography_polygons",
        "geography_type",
        ["geography_type_id"],
        ["id"],
    )

    op.create_index(
        "ix_geography_polygons_geographic_id",
        "geography_polygons",
        ["geographic_id"],
    )


def downgrade():
    # Dropping relevant index and foreign key constraints, before reverting relevant column data types
    op.drop_index(
        "ix_geography_polygons_geographic_id",
        table_name="geography_polygons",
    )
    op.drop_constraint(
        "geography_polygons_geography_type_id_fkey",
        "geography_polygons",
        type_="foreignkey",
    )
    op.drop_constraint(
        "geography_polygons_geography_version_id_fkey",
        "geography_polygons",
        type_="foreignkey",
    )
    op.drop_constraint(
        "geography_version_geography_type_id_fkey",
        "geography_version",
        type_="foreignkey",
    )

    # Setting GeographyType id data type back to String & adjusting all reference columns also
    op.alter_column(
        "geography_type",
        "id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="id::text",
    )
    op.alter_column(
        "geography_polygons",
        "geography_type_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="geography_type_id::text",
    )
    # Setting GeographyVersion id data type back to String & adjusting all reference columns also
    op.alter_column(
        "geography_version",
        "geography_type_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="geography_type_id::text",
    )
    op.alter_column(
        "geography_version",
        "id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="id::text",
    )
    op.alter_column(
        "geography_polygons",
        "geography_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="geography_version_id::text",
    )
    # Setting GeographyPolygons id data type back to String
    op.alter_column(
        "geography_polygons",
        "id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using="id::text",
    )

    # Recreating foreign key constraints now data types have been reverted
    op.create_foreign_key(
        "geography_version_geography_type_id_fkey",
        "geography_version",
        "geography_type",
        ["geography_type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "geography_polygons_geography_version_id_fkey",
        "geography_polygons",
        "geography_version",
        ["geography_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "geography_polygons_geography_type_id_fkey",
        "geography_polygons",
        "geography_type",
        ["geography_type_id"],
        ["id"],
    )

    # Dropping the additional columns
    op.drop_column("geography_type", "name_singular")
    op.drop_column("geography_polygons", "geographic_id")