import uuid

import pandas as pd
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import Integer, func, insert, text
from sqlalchemy.orm import aliased

from app import db
from app.models import GeographyPolygons, GeographyType, GeographyVersion


class AreasDAO:
    """Data access object for querying and manipulating geographic areas,
    using GeographyPolygons, GeographyType and GeographyVersion models"""

    @staticmethod
    def get_area_by_id(area_id):
        """Returns the area, from geography_polygons, with specified area ID (UUID)"""
        return (
            db.session.query(
                GeographyPolygons.id,
                GeographyPolygons.geographic_id,
                GeographyPolygons.name,
                GeographyPolygons.parent_geography_id,
                GeographyType.route.label("geography_type_name"),
                GeographyPolygons.geometry,
            )
            .join(
                GeographyType,
                GeographyPolygons.geography_type_id == GeographyType.id,
            )
            .filter(GeographyPolygons.id == area_id)
            .one_or_none()
        )

    @staticmethod
    def get_latest_area_by_geographic_id(geographic_id, type_name=None):
        """
        Returns the latest active GeographyPolygons for a given geographic_id
        """

        # If geography type specified, get latest version for that type,
        # otherwise return all latest geography types' versions to filter the results by
        if type_name is not None:
            latest_version = AreasDAO.get_latest_active_version_for_type_route(type_name)
            if latest_version is None:
                return None

            version_ids = [latest_version.id]
        else:
            latest_types = AreasDAO.get_active_geography_types_with_version()
            if not latest_types:
                return None

            version_ids = [geography_type.version_id for geography_type in latest_types]

        return (
            db.session.query(
                GeographyPolygons.id,
                GeographyPolygons.geographic_id,
                GeographyPolygons.name,
                GeographyPolygons.parent_geography_id,
                GeographyType.route.label("geography_type_name"),
                GeographyPolygons.geometry,
            )
            .join(
                GeographyType,
                GeographyPolygons.geography_type_id == GeographyType.id,
            )
            .filter(
                GeographyPolygons.geographic_id == geographic_id,
                GeographyPolygons.geography_version_id.in_(version_ids),
            )
            .one_or_none()
        )

    @staticmethod
    def get_areas_by_ids(area_ids):
        """Returns list of areas for the specified area IDs"""
        return (
            db.session.query(
                GeographyPolygons.id,
                GeographyPolygons.geographic_id,
                GeographyPolygons.name,
                GeographyPolygons.parent_geography_id,
                GeographyType.route.label("geography_type_name"),
                GeographyPolygons.geometry,
            )
            .join(
                GeographyType,
                GeographyPolygons.geography_type_id == GeographyType.id,
            )
            .filter(GeographyPolygons.id.in_(area_ids))
            .order_by(GeographyPolygons.name)
            .all()
        )

    @staticmethod
    def get_areas_by_names(area_names, type_name):
        """Returns the areas from geography_polygons, with latest version ID"""
        latest_version = AreasDAO.get_latest_active_version_for_type_route(type_name)

        if latest_version is None:
            return []

        return GeographyPolygons.query.filter(
            GeographyPolygons.name.in_(area_names),
            GeographyPolygons.geography_version_id == latest_version.id,
        ).all()

    @staticmethod
    def get_areas_for_geography_type(type_name):
        latest_active_version = AreasDAO.get_latest_active_version_for_type_route(type_name)
        if latest_active_version is None:
            return []

        return (
            GeographyPolygons.query.with_entities(
                GeographyPolygons.id,
                GeographyPolygons.geographic_id,
                GeographyPolygons.name,
                GeographyPolygons.parent_geography_id,
            )
            .filter_by(geography_version_id=latest_active_version.id)
            .order_by(GeographyPolygons.name)
            .all()
        )

    @staticmethod
    def get_child_areas_for_parent_geography_id(parent_geography_id):
        """Return active areas belonging to the specified parent area."""
        active_geography_types = AreasDAO.get_active_geography_types_with_version()
        active_version_ids = [geography_type.version_id for geography_type in active_geography_types]

        return (
            GeographyPolygons.query.with_entities(
                GeographyPolygons.id,
                GeographyPolygons.geographic_id,
                GeographyPolygons.name,
                GeographyPolygons.parent_geography_id,
            )
            .filter(
                GeographyPolygons.geography_version_id.in_(active_version_ids),
                GeographyPolygons.parent_geography_id == parent_geography_id,
            )
            .order_by(GeographyPolygons.name)
            .all()
        )

    @staticmethod
    def get_grandparent_areas():
        """Returns list of areas that have child areas that are parent areas"""

        version_ids = []
        for type_name in ("local_authorities", "wards"):
            latest_version = AreasDAO.get_latest_active_version_for_type_route(type_name)

            if latest_version is not None:
                version_ids.append(latest_version.id)

        # Use aliases of GeographyPolygons so we can join the table to itself:
        #   GeographyPolygons = grandparent
        #   parent_area      = child of grandparent
        #   child_area       = child of parent_area (grandchild of grandparent)
        parent_area = aliased(GeographyPolygons)
        child_area = aliased(GeographyPolygons)

        return (
            db.session.query(
                GeographyPolygons.id,  # Grandparent area IDs
            )
            # Finds parent areas by choosing those that are stored as parent_geography_id
            .join(parent_area, parent_area.parent_geography_id == GeographyPolygons.geographic_id)
            # Finds child areas of those parent areas
            .join(child_area, child_area.parent_geography_id == parent_area.geographic_id)
            .filter(GeographyPolygons.geography_version_id.in_(version_ids))
            .distinct()
            .order_by(GeographyPolygons.name)
            .all()
        )

    @staticmethod
    def geography_version_ordering():
        """Returns expressions for ordering geography versions semantically"""
        major = func.split_part(GeographyVersion.version, ".", 1).cast(Integer)
        minor = func.split_part(GeographyVersion.version, ".", 2).cast(Integer)
        patch = func.split_part(GeographyVersion.version, ".", 3).cast(Integer)

        return major.desc(), minor.desc(), patch.desc()

    @staticmethod
    def get_active_geography_types_with_version():
        """
        Returns the active geography types and their latest versions
        """

        return (
            db.session.query(
                GeographyVersion.id.label("version_id"),
                GeographyVersion.geography_type_id,
                GeographyType.name.label("geography_type_name"),
                GeographyType.name_singular,
                GeographyType.route,
            )
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
    def get_latest_active_version_for_type_route(type_name):
        """Returns the latest active version for a geography type"""
        return (
            db.session.query(GeographyVersion)
            .join(
                GeographyType,
                GeographyVersion.geography_type_id == GeographyType.id,
            )
            .filter(
                GeographyType.route == type_name,
                GeographyVersion.state == "active",
            )
            .order_by(*AreasDAO.geography_version_ordering(), GeographyVersion.id.desc())
            .first()
        )

    @staticmethod
    def get_geography_type_examples(type_name):
        """Returns the area count and first four area names for a geography type."""
        latest_version = AreasDAO.get_latest_active_version_for_type_route(type_name)

        if latest_version is None:
            return {
                "count": 0,
                "examples": [],
            }

        area_query = GeographyPolygons.query.filter_by(
            geography_version_id=latest_version.id,
        )

        count = area_query.count()

        examples = [area.name for area in area_query.order_by(GeographyPolygons.name).limit(4).all()]

        return {
            "count": count,
            "examples": examples,
        }

    @staticmethod
    def get_dominant_parent_geography_id(
        area_wkt,
        parent_type_name="local_authorities",
    ):
        """
        Given an area geometry in WKT, return the ID of the parent GeographyPolygons
        of type `parent_type_name` that overlaps it the most (by intersection area),
        or None.

        `parent_type_name` should match GeographyType.route, e.g. "local_authorities"
        or "local-authorities" depending on your data.
        """

        # Look up the GeographyType id for the requested parent type (by route)
        parent_type = db.session.query(GeographyType.id).filter(GeographyType.route == parent_type_name).first()
        if not parent_type:
            return None

        parent_type_id = parent_type.id

        sql = text("""
            SELECT parent.id
            FROM geography_polygons AS parent
            JOIN (
                SELECT ST_GeomFromText(:area_wkt, 4326) AS geom
            ) AS child
            ON ST_Intersects(child.geom, parent.geometry)
            WHERE parent.geography_type_id = :parent_type_id
            ORDER BY ST_Area(ST_Intersection(child.geom, parent.geometry)) DESC
            LIMIT 1
            """)

        result = db.session.execute(
            sql,
            {"area_wkt": area_wkt, "parent_type_id": parent_type_id},
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_area_centroid(area_id):
        """Returns the WKT string for centroid calculated for area"""
        area = AreasDAO.get_area_by_id(area_id)
        if area is None or area.geometry is None:
            return None
        geometry = to_shape(area.geometry).wkt
        query = """
            SELECT ST_AsText(ST_Centroid(g))
            FROM ST_GeomFromText(:geometry, 4326) AS g;
        """
        return db.session.execute(query, {"geometry": geometry}).scalar()

    @staticmethod
    def create_area(geometries):
        """Combines multiple geometries and returns the combined area as WKT string"""
        sql = text("""
            SELECT ST_ASText(
                ST_UnaryUnion(
                    ST_Collect(geom)
                )
            )
            FROM unnest(:geometries) AS geom
            """)
        return db.session.execute(sql, {"geometries": geometries}).scalar()

    @staticmethod
    def create_circle_area(centroid, radius):
        """Returns the area as WKT string for the 'circle' area generated using centroid and radius as buffer"""
        radius = radius * 1000
        query = """
            SELECT
                ST_AsText(
                    ST_Transform(
                        ST_Buffer(
                            ST_Transform(
                                ST_GeomFromText(:centroid, 4326),
                                27700
                            ),
                            :radius
                        ),
                        4326
                    )
                );
        """
        return db.session.execute(query, {"centroid": centroid, "radius": radius}).scalar()

    @staticmethod
    def combine_geometries(geometry_1, geometry_2):
        """Returns the combination of 2 geomtries as WKT string"""
        query = """
            SELECT ST_AsText(
                ST_Union(
                    ST_GeomFromText(:geometry_1, 4326),
                    ST_GeomFromText(:geometry_2, 4326)
                )
            );
        """
        return db.session.execute(query, {"geometry_1": geometry_1, "geometry_2": geometry_2}).scalar()

    @staticmethod
    def check_coordinates_valid(first, second, coordinate_type):
        if first is None or second is None:
            return False

        try:
            first_val = float(first)
            second_val = float(second)
        except (TypeError, ValueError):
            return False

        if coordinate_type == "latitude_longitude":
            lat = first_val
            lon = second_val
            point_wkt = f"POINT({lon} {lat})"
            # Spatial Reference Identifier (SRID) for latitude and longitude coordinates
            srid_in = 4326
        elif coordinate_type == "easting_northing":
            easting = first_val
            northing = second_val
            point_wkt = f"POINT({easting} {northing})"
            # Spatial Reference Identifier (SRID) for Cartesian - eastings and northings coordinates
            srid_in = 27700

        # Retrieve the country area IDs as these will be the basis for
        # checking whether or not coordinates are within UK
        country_areas = AreasDAO.get_areas_for_geography_type("countries")
        area_ids = [str(area.id) for area in country_areas]

        sql = text("""
            SELECT EXISTS (
                SELECT 1
                FROM geography_polygons gp
                WHERE gp.id IN :boundary_area_ids
                AND ST_Contains(
                    gp.geometry,
                    ST_Transform(
                        ST_GeomFromText(:point_wkt, :srid_in),
                        4326
                    )
                )
            );
            """)

        result = db.session.execute(
            sql,
            {"point_wkt": point_wkt, "srid_in": srid_in, "boundary_area_ids": tuple(area_ids)},
        ).scalar()

        return bool(result)

    @staticmethod
    def add_geography_version(geography_type_id, VERSION, source_url, state="active"):
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
    def add_geography_type_if_not_already_stored(name, route, name_singular):
        # Check that type isn't already stored
        geography_type = GeographyType.query.filter_by(name=name).one_or_none()
        if not geography_type:
            geography_type = GeographyType(name=name, route=route, name_singular=name_singular)
            db.session.add(geography_type)
        db.session.flush()
        return geography_type

    @staticmethod
    def add_geography_polygons(rows, geography_type_id, geography_version_id):
        """Bulk insert a dataframe chunk using SQLAlchemy's insert to GeographyPolygons"""
        if rows.empty:
            return

        geography_polygons_list = []
        for row in rows.to_dict(orient="records"):
            parent_geography_id = row["parent_geography_id"]

            if pd.isna(parent_geography_id):
                parent_geography_id = None

            geography_polygons_list.append(
                {
                    "id": uuid.uuid4(),
                    "geographic_id": row["geographic_id"],
                    "name": row["name"],
                    "geometry": WKTElement(row["geometry"], srid=4326),
                    "parent_geography_id": parent_geography_id,
                    "geography_version_id": geography_version_id,
                    "geography_type_id": geography_type_id,
                }
            )
        db.session.execute(insert(GeographyPolygons), geography_polygons_list)
        db.session.flush()
