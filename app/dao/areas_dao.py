from geoalchemy2.shape import to_shape
from sqlalchemy import desc, func, text
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import aliased

from app import db
from app.models import GeographyPolygons, GeographyType, GeographyVersion


def dao_get_latest_geography_version_number():
    """Returns latest active version's version number"""
    return GeographyVersion.query.filter_by(state="active").order_by(GeographyVersion.created_at.desc()).first().version


def dao_get_latest_geography_versions():
    """
    Return the latest geography versions from  for each geography type
    """
    # Find the latest active version number
    latest_version = dao_get_latest_geography_version_number()

    if latest_version is None:
        return []

    return GeographyVersion.query.filter_by(state="active", version=latest_version).all()


def dao_get_latest_active_version_for_type_route(type_name):
    # Returns latest version for geography type
    return (
        db.session.query((GeographyVersion.id))
        .join(GeographyType, GeographyVersion.geography_type_id == GeographyType.id)
        .filter(GeographyType.route == type_name, GeographyVersion.state == "active")
        .order_by(desc(GeographyVersion.version))
        .first()
    )


def dao_get_areas_for_geography_type(type_name):
    latest_active_version = dao_get_latest_active_version_for_type_route(type_name).id
    query = (
        GeographyPolygons.query.with_entities(
            GeographyPolygons.id,
            GeographyPolygons.geographic_id,
            GeographyPolygons.name,
            GeographyPolygons.parent_geography_id,
        )
        .filter_by(
            geography_version_id=latest_active_version,
        )
        .order_by(GeographyPolygons.name)
    )

    return query.all()


def dao_get_child_areas_for_parent_geography_id(parent_geography_id):
    # Only areas with latest local authority or ward version to be retrieved,
    # as these are the only child areas we are interested in currently
    # Note: REPPIR sites also have parent_geography_id but we don't
    # want them rendered as children for selection
    latest_la_version_id = dao_get_latest_active_version_for_type_route("local_authorities").id
    latest_ward_version_id = dao_get_latest_active_version_for_type_route("wards").id

    version_ids = [latest_la_version_id, latest_ward_version_id]

    query = (
        GeographyPolygons.query.with_entities(
            GeographyPolygons.id,
            GeographyPolygons.geographic_id,
            GeographyPolygons.name,
            GeographyPolygons.parent_geography_id,
        )
        .filter(GeographyPolygons.geography_version_id.in_(version_ids))
        .filter_by(parent_geography_id=parent_geography_id)
        .order_by(GeographyPolygons.name)
    )

    return query.all()


def dao_get_grandparent_areas():
    """Returns list of areas that have child areas that are parent areas"""
    latest_la_version_id = dao_get_latest_active_version_for_type_route("local_authorities").id
    latest_ward_version_id = dao_get_latest_active_version_for_type_route("wards").id

    version_ids = [latest_la_version_id, latest_ward_version_id]

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


def dao_get_latest_area_by_geographic_id(area_id, type_name=None):
    """
    Return the latest active GeographyPolygons for a given geographic_id,
    regardless of geography type.
    """

    if type_name:
        latest_active_version = dao_get_latest_active_version_for_type_route(type_name)
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
                GeographyPolygons.geographic_id == area_id,
                GeographyPolygons.geography_version_id == latest_active_version.id,
            )
            .one_or_none()
        )

    else:
        latest_geography_versions = dao_get_latest_geography_versions()
        if latest_geography_versions == []:
            return None

        latest_version_ids = [v.id for v in latest_geography_versions]

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
                GeographyPolygons.geographic_id == area_id,
                GeographyPolygons.geography_version_id.in_(latest_version_ids),
            )
            .one_or_none()
        )


def dao_get_areas_by_names(area_names, type_name):
    """Returns the areas from geography_polygons, with latest version ID"""
    latest_version_id = dao_get_latest_active_version_for_type_route(type_name).id
    return (
        GeographyPolygons.query.filter(GeographyPolygons.name.in_(area_names))
        .filter_by(geography_version_id=latest_version_id)
        .all()
    )


def dao_get_area_by_id(area_id):
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


def dao_get_areas_by_ids(area_ids):
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


def dao_get_latest_geography_types_with_count_and_examples():
    """Returns the types from geography_type table, with latest version IDs,
    with the result being a list of elements with structure;
    - type ID
    - type name
    - type route
    - count of areas for the type
    - first 4 areas for the type
    - type's name_singular (how singular areas of this type are referred to)
    """
    latest_geography_version = dao_get_latest_geography_version_number()
    query = (
        db.session.query(
            GeographyType.id,
            GeographyType.name.label("geography_type_name"),
            GeographyType.route,
            func.count(GeographyPolygons.id).label("area_count"),
            func.array_agg(
                aggregate_order_by(
                    GeographyPolygons.name,
                    GeographyPolygons.name,
                )
            )[
                1:4
            ].label("areas"),
            GeographyType.name_singular,
        )
        .join(
            GeographyVersion,
            GeographyVersion.geography_type_id == GeographyType.id,
        )
        .outerjoin(
            GeographyPolygons,
            (GeographyPolygons.geography_type_id == GeographyType.id)
            & (GeographyPolygons.geography_version_id == GeographyVersion.id),
        )
        .filter(GeographyVersion.version == latest_geography_version)
        .group_by(
            GeographyType.id,
            GeographyType.name,
            GeographyType.route,
            GeographyType.name_singular,
        )
    )

    return query.all()


def dao_create_area(geometries):
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


def dao_get_area_centroid(area_id):
    """Returns the WKT string for centroid calculated for area"""
    area = dao_get_area_by_id(area_id)
    if area is None or area.geometry is None:
        return None
    geometry = to_shape(area.geometry).wkt
    query = """
        SELECT ST_AsText(ST_Centroid(g))
        FROM ST_GeomFromText(:geometry, 4326) AS g;
    """
    return db.session.execute(query, {"geometry": geometry}).scalar()


def dao_create_circle_area(centroid, radius):
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


def dao_combine_geometries(geometry_1, geometry_2):
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


def dao_check_coordinates_valid(first, second, coordinate_type):
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
        srid_in = 4326
    elif coordinate_type == "easting_northing":
        easting = first_val
        northing = second_val
        point_wkt = f"POINT({easting} {northing})"
        srid_in = 27700

    # Retrieve the country area IDs as these will be the basis for
    # checking whether or not coordinates are within UK
    country_areas = dao_get_areas_for_geography_type("countries")
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


def dao_get_dominant_parent_geography_id(area_wkt, parent_type_name="local_authorities"):
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
