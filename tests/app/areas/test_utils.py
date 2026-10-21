from io import StringIO

import pytest

from app.areas.utils import (
    convert_to_long_lat_coordinates,
    get_parent_area_name,
    reorder_polygons_to_long_lat,
    split_into_chunks_and_insert_into_db,
    validate_bulk_area_input,
    wkt_geometry_to_alert_polygons,
)
from app.dao.areas_dao import AreasDAO
from app.models import GeographyPolygons
from tests.app.db import create_area


def test_split_into_chunks_and_insert_into_db_adds_data_as_expected(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored(name="test", route="test", name_singular="test")
    version = AreasDAO.add_geography_version(
        geography_type_id=geography_type.id, version="1.0.0", source_url="test.csv"
    )
    csv_data = StringIO(
        "geographic_id,name,geometry,parent_geography_id\n" 'test-area,Test area,"POLYGON ((0 0, 1 0, 1 1, 0 0))",\n'
    )
    parent_areas = {}
    split_into_chunks_and_insert_into_db("test", version.id, csv_data, parent_areas)

    geography_polygons = GeographyPolygons.query.all()
    assert len(geography_polygons) == 1
    assert geography_polygons[0].geographic_id == "test-area"
    assert geography_polygons[0].name == "Test area"
    assert geography_polygons[0].geography_version_id == version.id


def test_wkt_geometry_to_alert_polygons(notify_db_session):
    assert wkt_geometry_to_alert_polygons(
        (
            "POLYGON ((-0.305045 51.460623, -0.303402 51.460623,"
            " -0.303402 51.461296, -0.305045 51.461296, -0.305045 51.460623))"
        )
    ) == [
        [
            [51.460623, -0.305045],
            [51.460623, -0.303402],
            [51.461296, -0.303402],
            [51.461296, -0.305045],
            [51.460623, -0.305045],
        ]
    ]


def test_reorder_polygons_to_long_lat(notify_db_session):
    assert reorder_polygons_to_long_lat(
        [
            [
                [51.460623, -0.305045],
                [51.460623, -0.303402],
                [51.461296, -0.303402],
                [51.461296, -0.305045],
                [51.460623, -0.305045],
            ]
        ]
    ) == [
        [
            [-0.305045, 51.460623],
            [-0.303402, 51.460623],
            [-0.303402, 51.461296],
            [-0.305045, 51.461296],
            [-0.305045, 51.460623],
        ]
    ]


@pytest.mark.parametrize(
    ("first_coordinate", "second_coordinate", "coordinate_type", "expected_coordinates"),
    [
        (54, -2, "latitude_longitude", (-2, 54)),
        (
            530111,
            170000,
            "easting_northing",
            (-0.1304314403905844, 51.41409803439686),
        ),
    ],
)
def test_convert_to_long_lat_coordinates(
    notify_db_session,
    first_coordinate,
    second_coordinate,
    coordinate_type,
    expected_coordinates,
):
    assert convert_to_long_lat_coordinates(first_coordinate, second_coordinate, coordinate_type) == expected_coordinates


@pytest.mark.parametrize(
    ("first_coordinate", "second_coordinate", "coordinate_type"),
    [
        (54, -2, "latitude_longitudes"),
        (530111, 170000, "eastings_northings"),
        (None, 170000, "eastings_northings"),
    ],
)
def test_convert_to_long_lat_coordinates_returns_error_for_invalid_data(
    notify_db_session, first_coordinate, second_coordinate, coordinate_type
):
    with pytest.raises(ValueError) as e:
        convert_to_long_lat_coordinates(first_coordinate, second_coordinate, coordinate_type)
    assert str(e.value) == "Invalid coordinate values or coordinate type"


def test_get_parent_area_name(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored(
        "Test Name", "local_authority_districts", "test area"
    )
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    create_area(notify_db_session, geography_version_id=version.id, is_selectable=True, name="Test Parent, City of")
    assert get_parent_area_name("POINT (-0.125 51.505)") == "City of Test Parent"


def test_get_parent_area_name_returns_None_if_no_overlapping_area(notify_db_session):
    geography_type = AreasDAO.add_geography_type_if_not_already_stored(
        "Test Name", "local_authority_districts", "test area"
    )
    version = AreasDAO.add_geography_version(geography_type.id, "1.0.0", "test_areas.csv")
    create_area(notify_db_session, geography_version_id=version.id, is_selectable=True, name="Test Parent")
    assert get_parent_area_name("POINT (-2 54)") is None


def test_validate_bulk_area_input_returns_correct_error_message_for_input():
    # missing data
    assert validate_bulk_area_input([], "local_authorities") == "Enter at least 1 local authority"

    # duplicates
    assert (
        validate_bulk_area_input(["Area 1", "Area 1"], "local_authorities")
        == "Local authority 'Area 1' currently appears in the list more than once"
    )

    # exceeds limit
    too_many = [f"Area {i}" for i in range(26)]
    assert (
        validate_bulk_area_input(too_many, "local_authorities")
        == "Maximum of 25 local authorities allowed as a list in one emergency alert"
    )

    # valid list returns None
    assert validate_bulk_area_input(["Area 1", "Area 2"], "local_authorities") is None
