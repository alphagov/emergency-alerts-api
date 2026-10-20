import uuid

import pandas as pd
from geoalchemy2 import WKTElement
from sqlalchemy import Integer, and_, bindparam, case, func, insert, text

from app import db
from app.models import GeographyPolygons, GeographyType, GeographyVersion


class AreasDAO:
    """Data access object for querying and manipulating geographic areas,
    using GeographyPolygons, GeographyType and GeographyVersion models"""

    # -------------------------------------
    # The following methods are for inserting data into database, with add-areas command

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
    def add_geography_polygons(rows, geography_version_id, parent_areas, sub_area, is_selectable):
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
                    "is_selectable": is_selectable,
                }
            )
        db.session.execute(insert(GeographyPolygons), geography_polygons_list)
        db.session.flush()
        return parent_areas

    # -------------------------------
    @staticmethod
    def get_area(area_id):
        """Return an area and its geography type route"""
        area_result = (
            db.session.query(
                GeographyPolygons,
                GeographyType.route.label("geography_type_name"),
            )
            .join(
                GeographyVersion,
                GeographyPolygons.geography_version_id == GeographyVersion.id,
            )
            .join(
                GeographyType,
                GeographyVersion.geography_type_id == GeographyType.id,
            )
            .filter(GeographyPolygons.id == area_id)
            .one_or_none()
        )

        if area_result is None:
            return None

        area, geography_type_name = area_result

        return {
            "area": area,
            "geography_type_name": geography_type_name,
        }

    @staticmethod
    def get_area_by_geographic_id_and_type_route(geographic_id, type_route):
        """Returns an area with the specified geographic id and geography type, or None"""
        geography_type = AreasDAO.get_geography_type(type_route)

        area_query = GeographyPolygons.query.filter_by(
            geography_version_id=geography_type[0], geographic_id=geographic_id
        )
        return area_query.one_or_none()

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
        Returns geography type for the specified route, with its latest version_id, or None
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
    def get_geography_type_examples(type_route):
        """Returns the area count and first four area names for a
        geography type with specified route"""
        if type_route == "local_authorities":
            latest_versions = AreasDAO.get_latest_versions_for_local_authorities()

            area_query = GeographyPolygons.query.filter(
                GeographyPolygons.geography_version_id.in_(latest_versions),
                GeographyPolygons.parent_geography_id.is_(None),
                GeographyPolygons.is_selectable.is_(False),
            )

            areas = area_query.order_by(GeographyPolygons.id).all()

            unique_areas = {}
            for area in areas:
                unique_areas.setdefault(area.name, area)

            areas = sorted(unique_areas.values(), key=lambda area: area.name)
            count = len(unique_areas)
            examples = [area.name for area in areas[:4]]

        else:
            geography_type = AreasDAO.get_geography_type(type_route)
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

    @staticmethod
    def get_areas(version_id, parent_id=None):
        """Returns unique list of areas either with specified parent_id,
        or without parent, for specified geography type route"""
        if version_id == "local_authorities":
            # This is the "ID" we made for the merged type for those types
            # so really we just want to retrieve latest areas for both types
            latest_versions = AreasDAO.get_latest_versions_for_local_authorities()

            area_query = GeographyPolygons.query.filter(
                GeographyPolygons.geography_version_id.in_(latest_versions),
            )
        else:
            area_query = GeographyPolygons.query.filter(
                GeographyPolygons.geography_version_id == version_id,
            )

        if parent_id is not None:
            area_query = area_query.filter(
                GeographyPolygons.parent_geography_id == parent_id,
            )
        else:
            area_query = area_query.filter(
                GeographyPolygons.parent_geography_id.is_(None),
            )

        areas = area_query.order_by(GeographyPolygons.id).all()

        unique_areas = {}
        for area in areas:
            unique_areas.setdefault(area.name, area)

        return list(unique_areas.values())

    @staticmethod
    def get_latest_versions_for_local_authorities():
        """Returns the latest versions for local authority routes"""
        local_authority_routes = [
            "counties_and_unitary_authorities",
            "local_authority_districts",
        ]
        latest_versions = []
        for route in local_authority_routes:
            latest_version = AreasDAO.get_geography_type(route)[0]
            latest_versions.append(latest_version)
        return latest_versions

    @staticmethod
    def get_areas_by_ids(area_ids, version_id=None):
        """Returns the area for the specified area IDs (uuids) and version_id"""

        # If the geography type route is either one of those that we combine for 'local_authorities',
        # and `is_selectable` is True then we can deduce it's an electoral ward and set the type for this accordingly,
        # so that in Admin application, the electoral ward descriptor displays the ward alongside parent in it's name
        geography_type_route = case(
            (
                and_(
                    GeographyType.route.in_(
                        [
                            "counties_and_unitary_authorities",
                            "local_authority_districts",
                        ]
                    ),
                    GeographyPolygons.is_selectable.is_(True),
                ),
                "wards",
            ),
            else_=GeographyType.route,
        )

        area_query = (
            db.session.query(
                GeographyPolygons,
                geography_type_route.label("geography_type_name"),
            )
            .join(
                GeographyVersion,
                GeographyPolygons.geography_version_id == GeographyVersion.id,
            )
            .join(
                GeographyType,
                GeographyVersion.geography_type_id == GeographyType.id,
            )
        )

        if version_id == "local_authorities":
            version_ids = AreasDAO.get_latest_versions_for_local_authorities()

            if not version_ids:
                return []

            area_query = area_query.filter(
                GeographyPolygons.geography_version_id.in_(version_ids),
            )
        elif version_id:
            area_query = area_query.filter(
                GeographyPolygons.geography_version_id == version_id,
            )

        areas = area_query.filter(GeographyPolygons.id.in_(area_ids)).all()

        return [
            {
                "area": area,
                "geography_type_name": geography_type_name,
            }
            for area, geography_type_name in areas
        ]

    @staticmethod
    def get_areas_by_names(area_names, type_route=None):
        area_query = GeographyPolygons.query

        if type_route == "local_authorities":
            latest_versions = AreasDAO.get_latest_versions_for_local_authorities()

            if not latest_versions:
                return []

            area_query = area_query.filter(
                GeographyPolygons.geography_version_id.in_(latest_versions),
                GeographyPolygons.is_selectable.is_(False),
            )
        elif type_route:
            geography_type = AreasDAO.get_geography_type(type_route)
            if not geography_type:
                return []

            area_query = area_query.filter(
                GeographyPolygons.geography_version_id == geography_type[0],
            )

        return area_query.filter(
            GeographyPolygons.name.in_(area_names),
        ).all()

    @staticmethod
    def get_areas_by_geographic_ids(geographic_ids, type_route=None):
        """Return areas matching geographic IDs and geography type."""
        if not geographic_ids:
            return []

        area_query = GeographyPolygons.query

        if type_route == "local_authorities":
            latest_versions = AreasDAO.get_latest_versions_for_local_authorities()

            if not latest_versions:
                return []

            area_query = area_query.filter(
                GeographyPolygons.geography_version_id.in_(latest_versions),
            )

        elif type_route:
            geography_type = AreasDAO.get_geography_type(type_route)
            if not geography_type:
                return []

            area_query = area_query.filter(
                GeographyPolygons.geography_version_id == geography_type[0],
            )

        return area_query.filter(
            GeographyPolygons.geographic_id.in_(geographic_ids),
        ).all()

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
        country_geography = AreasDAO.get_geography_type("countries")
        if country_geography:
            country_areas = AreasDAO.get_areas(country_geography[0])
        else:
            country_areas = []

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
    def get_dominant_parent_geography_id(area_wkt, type_route="local_authorities"):
        """Return the ID of the area intersecting the largest part of area_wkt."""

        parent_type_version_ids = []

        if type_route == "local_authorities":
            geography_routes = [
                "counties_and_unitary_authorities",
                "local_authority_districts",
            ]

            for route in geography_routes:
                geography_type = AreasDAO.get_geography_type(route)
                if geography_type:
                    parent_type_version_ids.append(geography_type[0])
        else:
            geography_type = AreasDAO.get_geography_type(type_route)
            if geography_type:
                parent_type_version_ids.append(geography_type[0])

        if not parent_type_version_ids:
            return None

        # Finds the parent area that overlaps the given child geometry the
        # most, calculating intersection areas in metres
        sql = text("""
            WITH child AS (
                SELECT ST_GeomFromText(:area_wkt, 4326) AS geometry
            )
            SELECT parent.id
            FROM geography_polygons AS parent
            CROSS JOIN child
            WHERE parent.geography_version_id IN :parent_type_version_ids
              AND ST_Intersects(child.geometry, parent.geometry)
              AND parent.parent_geography_id IS NULL
            ORDER BY ST_Area(
                ST_Transform(
                    ST_Intersection(child.geometry, parent.geometry),
                    27700
                )
            ) DESC
            LIMIT 1
        """).bindparams(bindparam("parent_type_version_ids", expanding=True))

        result = db.session.execute(
            sql,
            {
                "area_wkt": area_wkt,
                "parent_type_version_ids": parent_type_version_ids,
            },
        ).first()

        return result[0] if result else None
