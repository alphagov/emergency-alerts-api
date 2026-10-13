import uuid

import pandas as pd
from geoalchemy2 import WKTElement
from sqlalchemy import Integer, func, insert

from app import db
from app.models import GeographyPolygons, GeographyType, GeographyVersion


class AreasDAO:
    """Data access object for querying and manipulating geographic areas,
    using GeographyPolygons, GeographyType and GeographyVersion models"""

    # -------------------------------------
    # The following methods are solely for inserting data into database, with add-areas command

    @staticmethod
    def add_geography_type_if_not_already_stored(name, route, name_singular):
        # Check that type isn't already stored
        geography_type = GeographyType.query.filter_by(name=name).one_or_none()
        if not geography_type:
            geography_type = GeographyType(name=name, route=route, name_singular=name_singular)
            db.session.add(geography_type)
        db.session.flush()
        return geography_type

    @staticmethod
    def add_geography_version(geography_type_id, VERSION, source_url, state="active"):
        # only create if version doesn't exist already
        geography_version = GeographyVersion(
            geography_type_id=geography_type_id,
            version=VERSION,
            source_url=source_url,
            state=state,
        )
        db.session.add(geography_version)
        db.session.flush()
        return geography_version

    @staticmethod
    def add_geography_polygons(rows, geography_type_id, geography_version_id, parent_areas, sub_area):
        """Bulk insert a dataframe chunk using SQLAlchemy's insert to GeographyPolygons"""
        parent_id = None
        if rows.empty:
            return

        geography_polygons_list = []
        for row in rows.to_dict(orient="records"):
            id = uuid.uuid4()
            parent_geography_id = row["parent_geography_id"]

            if pd.isna(parent_geography_id):
                # So that when inserted, it shall be null
                parent_geography_id = None

            if row["geographic_id"] == "E07000070":
                print(row)

            # If the data to be added belongs to child area type (sub area),
            # retrieve parent ID from dictionary
            if sub_area and parent_geography_id:
                parent_id = parent_areas[parent_geography_id]
            parent_areas[row["geographic_id"]] = id

            geography_polygons_list.append(
                {
                    "id": id,
                    "geographic_id": row["geographic_id"],
                    "name": row["name"],
                    "geometry": WKTElement(row["geometry"], srid=4326),
                    "parent_geography_id": parent_id if sub_area else None,
                    "geography_version_id": geography_version_id,
                    "geography_type_id": geography_type_id,
                }
            )
        db.session.execute(insert(GeographyPolygons), geography_polygons_list)
        db.session.flush()
        return parent_areas

    # -------------------------------
    @staticmethod
    def geography_version_ordering():
        """Returns expressions for ordering geography versions semantically"""
        major = func.split_part(GeographyVersion.version, ".", 1).cast(Integer)
        minor = func.split_part(GeographyVersion.version, ".", 2).cast(Integer)
        patch = func.split_part(GeographyVersion.version, ".", 3).cast(Integer)

        return major.desc(), minor.desc(), patch.desc()

    @staticmethod
    def get_geography_types():
        """
        Returns the active geography types and their latest versions
        """

        return (
            db.session.query(GeographyVersion.id.label("version_id"), GeographyType)
            .join(
                GeographyType,
                GeographyVersion.geography_type_id == GeographyType.id,
            )
            .filter(GeographyVersion.state == "active")
            .distinct(GeographyVersion.geography_type_id)
            .order_by(
                GeographyVersion.geography_type_id, *AreasDAO.geography_version_ordering(), GeographyVersion.id.desc()
            )
            .all()
        )

    @staticmethod
    def get_geography_type(type_route):
        """
        Returns the active geography types and their latest versions
        """

        return (
            db.session.query(GeographyVersion.id.label("version_id"), GeographyType)
            .join(
                GeographyType,
                GeographyVersion.geography_type_id == GeographyType.id,
            )
            .filter(GeographyVersion.state == "active", GeographyType.route == type_route)
            .distinct(GeographyVersion.geography_type_id)
            .order_by(
                GeographyVersion.geography_type_id, *AreasDAO.geography_version_ordering(), GeographyVersion.id.desc()
            )
            .one_or_none()
        )

    @staticmethod
    def get_geography_type_examples(type_name):
        """Returns the area count and first four area names for a geography type."""
        if type_name == "local_authorities":
            local_authority_routes = ["counties_and_unitary_authorities", "local_authority_districts"]
            latest_versions = []
            for route in local_authority_routes:
                latest_version = AreasDAO.get_geography_type(route)[0]
                latest_versions.append(latest_version)

            area_query = GeographyPolygons.query.filter(
                GeographyPolygons.geography_version_id.in_(latest_versions),
            )

        else:
            geography_type = AreasDAO.get_geography_type(type_name)
            latest_version = geography_type[0] if geography_type else None

            if latest_version is None:
                return {
                    "count": 0,
                    "examples": [],
                }

            area_query = GeographyPolygons.query.filter_by(
                geography_version_id=latest_version,
            )

        count = area_query.count()

        examples = [area.name for area in area_query.order_by(GeographyPolygons.name).limit(4).all()]

        return {
            "count": count,
            "examples": examples,
        }
