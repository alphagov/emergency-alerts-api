def test_postgis_extension_added_to_db(
    notify_db_session,
):
    result = notify_db_session.execute("SELECT extname FROM pg_extension WHERE extname='postgis'").one()
    assert result[0] == "postgis"


def test_postgis_version_returns_version(
    notify_db_session,
):
    result = notify_db_session.execute("SELECT postgis_version()").one()
    assert "3.5 " in result[0]  # Asserts that PostGIS version is same as specified in docker-compose-tests.yml


def test_st_astext_returns_point_wkt(
    notify_db_session,
):
    # Asserts that ST_AsText and ST_GeomFromText are present,
    # as are provided by PostGIS extension, and converts geometry to WKT
    result = notify_db_session.execute("SELECT ST_AsText(ST_GeomFromText('POINT(0 0)', 4326))").one()
    assert result[0] == "POINT(0 0)"


def test_st_area_function_computes_area_of_polygon(notify_db_session):
    # Asserts that ST_Area functions present, provided by PostGIS extension,
    # and computes area of a polygon geometry, in this case a shape with area of 1
    result = notify_db_session.execute(
        "SELECT ST_Area(ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326))"
    ).one()
    assert int(result[0]) == 1


def test_st_intersects_function_detects_overlapping_geometries(notify_db_session):
    # Asserts that ST_Intersects functions present, provided by PostGIS extension,
    # and detects if geometries overlap
    result = notify_db_session.execute(
        "SELECT ST_Intersects(ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326), "
        "ST_GeomFromText('POLYGON((0 2, 1 2, 1 3, 0 3, 0 2))', 4326))"
    ).one()
    assert result[0] is False  # The 2 polygons don't intersect
    result = notify_db_session.execute(
        "SELECT ST_Intersects(ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326), "
        "ST_GeomFromText('POLYGON((0 0, 1 2, 1 3, 0 3, 0 0))', 4326))"
    ).one()
    assert result[0] is True  # The 2 polygons intersect at 0,0
