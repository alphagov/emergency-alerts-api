import uuid

import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.areas_dao import AreasDAO
from app.models import GeographyPolygons, GeographyType, GeographyVersion
from tests.app.db import (
    create_area,
    create_area_with_type_and_version,
    create_country_area_data_for_coordinates_checks,
    create_geography_type,
    create_geography_version,
)


def test_add_geography_type_if_not_already_stored_adds_type(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    assert GeographyType.query.all() == [geography_type]


def test_add_geography_type_if_not_already_stored_skips_adding_type_if_already_exists(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    assert GeographyType.query.count() == 1
    assert GeographyType.query.all() == [geography_type]


def test_add_geography_version_add_version(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    geography_version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    assert GeographyVersion.query.all() == [geography_version]


def test_add_geography_version_skips_adding_version_if_already_exists(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    geography_version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    assert GeographyVersion.query.all() == [geography_version]


def test_add_geography_version_returns_error_if_type_not_added(notify_db_session):
    nonexistent_type_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        AreasDAO.add_geography_version(nonexistent_type_id, "1.0.0", "test_areas.csv")


def test_add_geography_polygons_adds_polygons(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    geography_version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    rows = pd.DataFrame(
        [
            {
                "geographic_id": "area-1",
                "name": "Test area",
                "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                "parent_geography_id": None,
            }
        ],
    )

    parent_areas = {}
    parent_areas = AreasDAO.add_geography_polygons(
        rows,
        geography_version.id,
        parent_areas,
        sub_area=False,
        is_selectable=True,
    )

    polygons = GeographyPolygons.query.all()
    assert parent_areas == {polygons[0].geographic_id: polygons[0].id}
    assert len(polygons) == 1


def test_add_geography_polygons_adds_polygons_with_parents(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    geography_version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    rows = pd.DataFrame(
        [
            {
                "geographic_id": "area-1",
                "name": "Test area",
                "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                "parent_geography_id": None,
            }
        ],
    )
    child_rows = pd.DataFrame(
        [
            {
                "geographic_id": "child-area",
                "name": "Test child area",
                "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                "parent_geography_id": "area-1",
            }
        ],
    )

    parent_areas = {}
    parent_areas = AreasDAO.add_geography_polygons(
        rows,
        geography_version.id,
        parent_areas,
        sub_area=False,
        is_selectable=False,
    )
    parent_areas = AreasDAO.add_geography_polygons(
        child_rows,
        geography_version.id,
        parent_areas,
        sub_area=True,
        is_selectable=True,
    )

    polygons = GeographyPolygons.query.all()
    assert parent_areas == {polygons[0].geographic_id: polygons[0].id, polygons[1].geographic_id: polygons[1].id}
    assert polygons[1].parent_geography_id == str(
        polygons[0].id
    )  # Stored as a string as geographic_id is a string initially
    assert len(polygons) == 2


def test_add_geography_polygons_returns_error_if_version_not_already_added(notify_db_session):
    nonexistent_version_id = uuid.uuid4()
    rows = pd.DataFrame(
        [
            {
                "geographic_id": "child-area",
                "name": "Test child area",
                "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                "parent_geography_id": "area-1",
            }
        ],
    )
    with pytest.raises(IntegrityError):
        parent_areas = {}
        AreasDAO.add_geography_polygons(rows, nonexistent_version_id, parent_areas, sub_area=False, is_selectable=True)


def test_get_area_returns_expected_area(notify_db_session):
    test_area = create_area_with_type_and_version(notify_db_session)
    assert AreasDAO.get_area(test_area.id) == {"area": test_area, "geography_type_name": "test_route"}


def test_get_area_returns_None_if_no_version(notify_db_session):
    nonexistent_version_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        create_area(notify_db_session, geography_version_id=nonexistent_version_id)


def test_get_area_by_geographic_id_and_type_route_returns_expected_data(notify_db_session):
    test_area = create_area_with_type_and_version(notify_db_session)
    assert (
        AreasDAO.get_area_by_geographic_id_and_type_route(test_area.geographic_id, type_route="test_route") == test_area
    )


def test_get_area_by_geographic_id_and_type_route_returns_None_if_no_area_exists(notify_db_session):
    nonexistent_id = uuid.uuid4()
    assert AreasDAO.get_area_by_geographic_id_and_type_route(nonexistent_id, type_route="test_route") is None


def test_geography_version_ordering_returns_versions_in_correct_order(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    first_version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    third_version = AreasDAO.add_geography_version(geography_type.id, "3.0.0", "test_areas.csv")
    second_version = AreasDAO.add_geography_version(geography_type.id, "2.0.0", "test_areas.csv")
    ordered_versions = GeographyVersion.query.order_by(*AreasDAO.geography_version_ordering()).all()
    assert [version.version for version in ordered_versions] == [
        third_version.version,
        second_version.version,
        first_version.version,
    ]


def test_get_geography_types_returns_expected_data(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")

    second_geography_type = AreasDAO.add_geography_type_if_not_already_stored(
        "Test Name 2", "test_route_2", "test area_2"
    )
    second_type_version = AreasDAO.add_geography_version(second_geography_type.id, "1.0.0", "test_areas_2.csv")
    geography_types = AreasDAO.get_geography_types()
    assert (version.id, geography_type) in geography_types
    assert (second_type_version.id, second_geography_type) in geography_types
    assert len(geography_types) == 2


def test_get_geography_types_returns_empty_list_if_no_types_with_active_versions(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv", state="inactive")
    geography_types = AreasDAO.get_geography_types()
    assert geography_types == []


def test_get_geography_type_returns_expected_data(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    assert AreasDAO.get_geography_type(geography_type.route) == (version.id, geography_type)


def test_get_geography_type_returns_None_if_no_type_with_active_version(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv", state="inactive")
    assert AreasDAO.get_geography_type(geography_type.route) is None


def test_get_geography_type_examples_returns_expected_data_for_type(notify_db_session):
    area = create_area_with_type_and_version(notify_db_session)
    create_area(notify_db_session, geography_version_id=area.geography_version_id, name="Test 2")
    create_area(notify_db_session, geography_version_id=area.geography_version_id, name="Test 3")
    assert AreasDAO.get_geography_type_examples("test_route") == {
        "count": 3,
        "examples": ["Test 2", "Test 3", "Test Area"],
    }


def test_get_geography_type_examples_returns_None_if_no_type_exists_with_active_version(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv", state="inactive")
    create_area(notify_db_session, geography_version_id=version.id)
    assert AreasDAO.get_geography_type_examples("test_route") == {"count": 0, "examples": []}


def test_get_areas_returns_expected_data_for_version_id(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    area1 = create_area(notify_db_session, geography_version_id=version.id)
    area2 = create_area(notify_db_session, geography_version_id=version.id, name="Test Area2")
    assert AreasDAO.get_areas(version.id) == [area1, area2]


def test_get_areas_returns_expected_data_for_version_and_parent_id(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    area1 = create_area(notify_db_session, geography_version_id=version.id)
    area2 = create_area(
        notify_db_session, geography_version_id=version.id, name="Test Area2", parent_geography_id=str(area1.id)
    )
    assert AreasDAO.get_areas(version.id, str(area1.id)) == [area2]


def test_get_areas_returns_None_for_nonexistent_version_and_parent_id(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored("Test Name", "test_route", "test area")
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    area1 = create_area(notify_db_session, geography_version_id=version.id)
    area2 = create_area(
        notify_db_session, geography_version_id=version.id, name="Test Area2", parent_geography_id=str(area1.id)
    )
    assert AreasDAO.get_areas(version.id, str(area1.id)) == [area2]


def test_get_latest_versions_for_local_authorities_returns_expected_data(notify_db_session):
    local_authority_districts_type = create_geography_type(notify_db_session, route="local_authority_districts")
    county_and_unitary_authorities_type = create_geography_type(
        notify_db_session, route="counties_and_unitary_authorities", name="Test 2"
    )
    local_authority_districts_version = create_geography_version(notify_db_session, local_authority_districts_type.id)
    county_and_unitary_authorities_version = create_geography_version(
        notify_db_session, county_and_unitary_authorities_type.id
    )
    assert AreasDAO.get_latest_versions_for_local_authorities() == [
        county_and_unitary_authorities_version.id,
        local_authority_districts_version.id,
    ]


def test_get_latest_versions_for_local_authorities_returns_None_if_missing_types(notify_db_session):
    assert AreasDAO.get_latest_versions_for_local_authorities() == []


def test_get_areas_by_ids_returns_expected_areas_for_ids(notify_db_session):
    area1 = create_area_with_type_and_version(notify_db_session)
    area2 = create_area(
        notify_db_session,
        geography_version_id=area1.geography_version_id,
        name="Second area",
    )

    result = AreasDAO.get_areas_by_ids([area1.id, area2.id])
    assert {item["area"] for item in result} == {area1, area2}


def test_get_areas_by_ids_filters_by_version_id(notify_db_session):
    area1 = create_area_with_type_and_version(notify_db_session)
    area2 = create_area(
        notify_db_session,
        geography_version_id=area1.geography_version_id,
        name="Second area",
    )

    result = AreasDAO.get_areas_by_ids(
        [area1.id, area2.id],
        version_id=area1.geography_version_id,
    )

    assert result == [
        {
            "area": area1,
            "geography_type_name": "test_route",
        },
        {
            "area": area2,
            "geography_type_name": "test_route",
        },
    ]


def test_get_areas_by_ids_returns_areas_with_ward_type(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored(
        "Test Name", "local_authority_districts", "test area"
    )
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    test_area = create_area(notify_db_session, geography_version_id=version.id, is_selectable=True)

    result = AreasDAO.get_areas_by_ids(
        [test_area.id],
        version_id=test_area.geography_version_id,
    )

    assert result == [
        {
            "area": test_area,
            "geography_type_name": "wards",
        }
    ]


def test_get_areas_by_ids_returns_empty_list_for_local_authorities_without_versions(notify_db_session):
    assert (
        AreasDAO.get_areas_by_ids(
            [uuid.uuid4()],
            version_id="local_authorities",
        )
        == []
    )


def test_get_areas_by_names_returns_areas_with_matching_names(notify_db_session):
    area1 = create_area_with_type_and_version(notify_db_session)
    area2 = create_area(
        notify_db_session,
        geography_version_id=area1.geography_version_id,
        name="Second area",
    )

    result = AreasDAO.get_areas_by_names([area1.name, area2.name])
    assert result == [area1, area2]


def test_get_areas_by_geographic_ids_returns_expected_data(notify_db_session):
    area1 = create_area_with_type_and_version(notify_db_session)
    area2 = create_area(
        notify_db_session,
        geography_version_id=area1.geography_version_id,
        name="Second area",
    )
    result = AreasDAO.get_areas_by_geographic_ids([area1.geographic_id, area2.geographic_id])
    assert result == [area1, area2]


def test_get_areas_by_geographic_ids_returns_None_if_no_matching_areas(notify_db_session):
    nonexistent_geographic_id = "area-does-not-exist"
    result = AreasDAO.get_areas_by_geographic_ids([nonexistent_geographic_id])
    assert result == []


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, coordinate_type, expected_result",
    [
        (530111, 170000, "easting_northing", True),
        (54.0, -2.0, "latitude_longitude", True),
        (5301110, 1700000, "easting_northing", False),
        (540.0, -20.0, "latitude_longitude", False),
    ],
)
def test_check_coordinates_valid_returns_expected_result(
    notify_db_session, first_coordinate, second_coordinate, coordinate_type, expected_result
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    assert AreasDAO.check_coordinates_valid(first_coordinate, second_coordinate, coordinate_type) == expected_result


# create_area
def test_create_area_returns_expected_wkt(notify_db_session):
    area1_wkt = (
        "POLYGON ((-0.6707817702352941 51.47200285566962, -0.6144825070060733 51.47200285566962, -0.6144825070060733 "
        "51.49749738300797, -0.6707817702352941 51.49749738300797, -0.6707817702352941 51.47200285566962))"
    )
    area2_wkt = (
        "POLYGON ((-0.6424944659055427 51.46403289258371, -0.5938723749349037 51.46403289258371, -0.5938723749349037 "
        "51.48634528116824, -0.6424944659055427 51.48634528116824, -0.6424944659055427 51.46403289258371))"
    )
    assert AreasDAO.create_area([area1_wkt, area2_wkt]).startswith("POLYGON")


def test_create_circle_area_returns_expected_wkt(notify_db_session):
    centroid = "POINT (-2 54)"
    radius = 1
    assert AreasDAO.create_circle_area(centroid, radius).startswith("POLYGON")


def test_get_dominant_parent_geography_id_returns_expected_parent_geography(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored(
        "Test Name", "local_authority_districts", "test area"
    )
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    parent_local_authority = create_area(notify_db_session, geography_version_id=version.id, is_selectable=True)
    assert AreasDAO.get_dominant_parent_geography_id("POINT (-0.125 51.505)") == parent_local_authority.id


def test_get_dominant_parent_geography_id_returns_None_if_no_overlapping_geography(notify_db_session):
    assert AreasDAO.get_dominant_parent_geography_id("POINT (-0.135 51.325)") is None
