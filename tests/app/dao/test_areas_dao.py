import uuid

import pytest
from geoalchemy2.shape import to_shape

from app.dao.areas_dao import (
    dao_check_coordinates_valid,
    dao_combine_geometries,
    dao_create_area,
    dao_create_circle_area,
    dao_get_area_by_id,
    dao_get_area_centroid,
    dao_get_areas_by_ids,
    dao_get_areas_by_names,
    dao_get_areas_for_geography_type,
    dao_get_child_areas_for_parent_geography_id,
    dao_get_dominant_parent_geography_id,
    dao_get_grandparent_areas,
    dao_get_latest_active_version_for_type_route,
    dao_get_latest_area_by_geographic_id,
    dao_get_latest_geography_types_with_count_and_examples,
    dao_get_latest_geography_version_number,
    dao_get_latest_geography_versions,
)
from tests.app.db import (
    create_area,
    create_area_with_version_and_type,
    create_geography_type,
    create_geography_version,
)


def test_dao_get_latest_geography_version_number_returns_expected_version(notify_db_session):
    geography_type = create_geography_type(route="local_authorities")
    create_geography_version(geography_type_id=geography_type.id, version="1.0.0", state="active")
    newer = create_geography_version(geography_type_id=geography_type.id, version="2.0.0", state="active")
    # inactive shouldn't be returned
    create_geography_version(geography_type_id=geography_type.id, version="3.0.0", state="inactive")

    version_number = dao_get_latest_geography_version_number()

    assert version_number == newer.version


def test_dao_get_latest_geography_versions_returns_latest_versions(notify_db_session):
    type1 = create_geography_type(route="local_authorities", name="Local authorities")
    type2 = create_geography_type(route="wards", name="Wards")

    create_geography_version(geography_type_id=type1.id, version="1.0.0", state="active")
    version1_new = create_geography_version(geography_type_id=type1.id, version="2.0.0", state="active")
    version2_new = create_geography_version(geography_type_id=type2.id, version="2.0.0", state="active")

    # Latest version number across all active types is 2.0.0
    latest_versions = dao_get_latest_geography_versions()

    assert {v.id for v in latest_versions} == {version1_new.id, version2_new.id}


def test_dao_get_latest_geography_versions_returns_empty_list_if_no_active_versions(notify_db_session):
    type1 = create_geography_type(route="local_authorities")
    create_geography_version(geography_type_id=type1.id, version="1.0.0", state="inactive")

    result = dao_get_latest_geography_versions()
    assert result == []


def test_dao_get_latest_active_version_for_type_route_returns_expected_version_for_type(notify_db_session):
    geography_type = create_geography_type(route="local_authorities")
    create_geography_version(geography_type_id=geography_type.id, version="1.0.0", state="active")
    v_latest = create_geography_version(geography_type_id=geography_type.id, version="2.0.0", state="active")

    found = dao_get_latest_active_version_for_type_route("local_authorities")
    assert found.id == v_latest.id


def test_dao_get_areas_for_geography_type_returns_all_expected_areas_for_type(notify_db_session):
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    gv1 = create_geography_version(geography_type_id=geography_type.id, version="1.0.0", state="active")
    gv0 = create_geography_version(geography_type_id=geography_type.id, version="0.9.0", state="active")

    area_latest1 = create_area(geography_type_id=geography_type.id, geography_version_id=gv1.id, name="Area A")
    area_latest2 = create_area(geography_type_id=geography_type.id, geography_version_id=gv1.id, name="Area B")
    create_area(geography_type_id=geography_type.id, geography_version_id=gv0.id, name="Area Old")

    areas = dao_get_areas_for_geography_type("local_authorities")

    # Only latest version's areas, ordered by name
    assert [a.name for a in areas] == ["Area A", "Area B"]
    assert {a.id for a in areas} == {area_latest1.id, area_latest2.id}


def test_dao_get_areas_for_geography_type_returns_empty_list_if_no_active_versions(notify_db_session):
    # geography type exists, but no active version
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    create_geography_version(geography_type_id=geography_type.id, version="1.0.0", state="inactive")

    areas = dao_get_areas_for_geography_type("local_authorities")
    assert areas == []


def test_dao_get_child_areas_for_parent_geography_id_returns_all_expected_child_areas_for_parent_area(
    notify_db_session,
):
    la_type = create_geography_type(route="local_authorities")
    la_version = create_geography_version(geography_type_id=la_type.id, version="1.0.0", state="active")
    ward_type = create_geography_type(route="wards", name="Wards")
    ward_version = create_geography_version(geography_type_id=ward_type.id, version="1.0.0", state="active")

    parent = create_area(geography_type_id=la_type.id, geography_version_id=la_version.id, geographic_id="parent-id")
    child_la = create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        geographic_id="child-la",
    )
    child_ward = create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=ward_type.id,
        geography_version_id=ward_version.id,
        geographic_id="child-ward",
    )

    children = dao_get_child_areas_for_parent_geography_id(parent.geographic_id)

    assert [area.geographic_id for area in children] == [child_la.geographic_id, child_ward.geographic_id]


def test_dao_get_child_areas_for_parent_geography_id_returns_empty_list_if_no_active_versions(notify_db_session):
    la_type = create_geography_type(route="local_authorities")
    la_version = create_geography_version(geography_type_id=la_type.id, version="1.0.0", state="inactive")

    parent = create_area(geography_type_id=la_type.id, geography_version_id=la_version.id, geographic_id="parent-id")
    create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        geographic_id="child-id",
    )

    children = dao_get_child_areas_for_parent_geography_id(parent.geographic_id)
    assert children == []


def test_dao_get_grandparent_areas_returns_only_areas_that_are_grandparents(notify_db_session):
    la_type = create_geography_type(route="local_authorities")
    la_version = create_geography_version(geography_type_id=la_type.id, version="1.0.0", state="active")

    ward_type = create_geography_type(route="wards", name="Wards")
    create_geography_version(geography_type_id=ward_type.id, version="1.0.0", state="active")

    grandparent_area = create_area(
        geography_type_id=la_type.id, geography_version_id=la_version.id, geographic_id="grandparent"
    )
    parent_area = create_area(
        parent_geography_id=grandparent_area.geographic_id,
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        geographic_id="parent",
    )
    create_area(
        parent_geography_id=parent_area.geographic_id,
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        geographic_id="child",
    )

    non_grandparent_area = create_area(
        geography_type_id=la_type.id, geography_version_id=la_version.id, geographic_id="non-parent"
    )
    create_area(  # parent_of_non_grandparent
        parent_geography_id=non_grandparent_area.geographic_id,
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
    )

    grandparent_ids = [row[0] for row in dao_get_grandparent_areas()]
    assert str(grandparent_area.id) in {str(i) for i in grandparent_ids}
    assert str(non_grandparent_area.id) not in {str(i) for i in grandparent_ids}


def test_dao_get_latest_area_by_geographic_id_returns_expected_area(notify_db_session):
    area, geography_version, geography_type = create_area_with_version_and_type()
    result = dao_get_latest_area_by_geographic_id(area.geographic_id)

    assert result is not None
    assert result.id == area.id
    assert result.geographic_id == area.geographic_id
    assert result.name == area.name


def test_dao_get_latest_area_by_geographic_id_returns_None_if_no_active_area_exists(notify_db_session):
    # create area but mark its version inactive so it shouldn't be returned
    geography_type = create_geography_type()
    gv_inactive = create_geography_version(geography_type_id=geography_type.id, version="1.0.0", state="inactive")
    area = create_area(geography_type_id=geography_type.id, geography_version_id=gv_inactive.id)

    result = dao_get_latest_area_by_geographic_id(area.geographic_id)
    assert result is None


def test_dao_get_latest_area_by_geographic_id_with_type_returns_expected_area(notify_db_session):
    area, geography_version, geography_type = create_area_with_version_and_type(geography_type_route="postcodes")
    result = dao_get_latest_area_by_geographic_id(area.geographic_id, type_name="postcodes")

    assert result is not None
    assert result.id == area.id
    assert result.geography_type_name == geography_type.route


def test_dao_get_areas_by_names_returns_expected_areas(notify_db_session):
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    area1 = create_area(
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
        name="Local authority 1",
    )
    area2 = create_area(
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
        name="Local authority 2",
    )

    areas = dao_get_areas_by_names(["Local authority 1", "Local authority 2"], "local_authorities")

    assert {a.id for a in areas} == {area1.id, area2.id}


def test_dao_get_area_by_id_returns_expected_area_or_None(notify_db_session):
    area, _, geography_type = create_area_with_version_and_type()
    found = dao_get_area_by_id(area.id)

    assert found is not None
    assert found.id == area.id
    assert found.geographic_id == area.geographic_id
    assert found.geography_type_name == geography_type.route

    missing = dao_get_area_by_id(uuid.uuid4())
    assert missing is None


def test_dao_get_areas_by_ids_returns_expected_areas(notify_db_session):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()

    areas = dao_get_areas_by_ids([str(area1.id), str(area2.id)])
    ids = [a.id for a in areas]

    assert set(ids) == {area1.id, area2.id}


def test_dao_get_latest_geography_types_with_count_and_examples_returns_expected_data_for_type(
    notify_db_session,
):
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_name="Local authorities",
        geography_type_route="local_authorities",
    )

    results = dao_get_latest_geography_types_with_count_and_examples()
    assert len(results) == 1

    row = results[0]
    assert row.id == geography_type.id
    assert row.geography_type_name == geography_type.name
    assert row.route == geography_type.route
    assert int(row.area_count) == 1
    assert list(row.areas) == [area.name]


def test_dao_create_area_returns_expected_area_wkt(notify_db_session):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()

    wkt1 = to_shape(area1.geometry).wkt
    wkt2 = to_shape(area2.geometry).wkt

    combined = dao_create_area([wkt1, wkt2])

    assert isinstance(combined, str)
    assert combined.startswith("POLYGON(")


def test_dao_get_area_centroid_returns_expected_wkt(notify_db_session):
    area, _, _ = create_area_with_version_and_type()
    centroid = dao_get_area_centroid(area.id)

    # matches what the REST tests expect for the default geometry
    assert centroid == "POINT(-1.2 53.925000000000004)"


def test_dao_get_area_centroid_returns_None_if_no_area_id_provided(notify_db_session):
    geography_type = create_geography_type()
    geography_version = create_geography_version(geography_type_id=geography_type.id)
    create_area(geography_type_id=geography_type.id, geography_version_id=geography_version.id)

    centroid = dao_get_area_centroid(None)
    assert centroid is None


def test_dao_create_circle_area_returns_expected_wkt(notify_db_session):
    # use a simple point centroid from the default area
    area, _, _ = create_area_with_version_and_type()
    centroid = dao_get_area_centroid(area.id)

    circle_wkt = dao_create_circle_area(centroid, radius=5)

    assert isinstance(circle_wkt, str)
    assert circle_wkt.startswith("POLYGON((")


def test_dao_combine_geometries_returns_expected_wkt(notify_db_session):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()

    wkt1 = to_shape(area1.geometry).wkt
    wkt2 = to_shape(area2.geometry).wkt

    combined = dao_combine_geometries(wkt1, wkt2)

    assert isinstance(combined, str)
    assert combined.startswith("POLYGON(") or combined.startswith("MULTIPOLYGON(")


@pytest.mark.parametrize(
    "data, expected_bool",
    [
        ({"first": 528000, "second": 178000, "coordinate_type": "easting_northing"}, True),
        ({"first": 0, "second": 0, "coordinate_type": "easting_northing"}, False),
        ({"first": 54, "second": -2, "coordinate_type": "latitude_longitude"}, True),
        ({"first": 0, "second": 0, "coordinate_type": "latitude_longitude"}, False),
    ],
)
def test_dao_check_coordinates_valid_returns_expected_bool_for_centroid(
    notify_db_session,
    data,
    expected_bool,
):
    # set up a country polygon so validity checks have something to contain/ exclude
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21"
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE"
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840"
    )
    create_area_with_version_and_type(
        geography_type_route="countries",
        geometry=country_geometry,
    )

    valid = dao_check_coordinates_valid(data["first"], data["second"], data["coordinate_type"])
    assert valid is expected_bool


def test_dao_get_dominant_parent_geography_id_returns_expected_parent_area_geography_id(
    notify_db_session,
):
    # Parent type
    la_type = create_geography_type(name="Local authorities", route="local_authorities")
    la_version = create_geography_version(geography_type_id=la_type.id)

    parent1 = create_area(
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        name="Parent 1",
    )
    create_area(
        geography_type_id=la_type.id,
        geography_version_id=la_version.id,
        name="Parent 2",
    )

    # Use geometry of parent1 as the child area WKT so it should overlap parent1 most
    parent1_wkt = to_shape(parent1.geometry).wkt

    dominant_id = dao_get_dominant_parent_geography_id(parent1_wkt, parent_type_name="local_authorities")

    assert dominant_id == parent1.id
