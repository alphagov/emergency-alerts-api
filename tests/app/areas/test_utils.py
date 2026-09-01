import pytest
import shapely
from emergency_alerts_utils.polygons import Polygons
from geoalchemy2.shape import to_shape

from app.areas.utils import (
    add_custom_area_to_existing_areas,
    area_response_json,
    build_remaining_area_wkt,
    ensure_valid_wkt,
    generate_centroid_for_coordinate_area,
    get_parent_area_name,
    get_parent_geography_id,
    validate_bulk_area_input,
    wkt_geometry_to_alert_polygons,
)
from app.dao.areas_dao import (
    dao_get_area_centroid,
)
from tests.app.db import (
    create_area,
    create_area_with_version_and_type,
    create_broadcast_message,
    create_geography_type,
    create_geography_version,
)


class TestAreaObject:
    # Dummy Area object necessary for some tests asserting how object processed
    def __init__(self, id, name, parent_geography_id, geographic_id, geography_type_name):
        self.id = id
        self.name = name
        self.parent_geography_id = parent_geography_id
        self.geographic_id = geographic_id
        self.geography_type_name = geography_type_name


def test_area_response_json_returns_expected_json_for_area_object(notify_db_session):
    area, _, geography_type = create_area_with_version_and_type(geography_type_name="TEST")
    area_object = TestAreaObject(
        id=area.id,
        name=area.name,
        parent_geography_id=area.parent_geography_id,
        geographic_id=area.geographic_id,
        geography_type_name=geography_type.name,
    )
    result = area_response_json(area_object)

    assert result == {
        "id": area.id,
        "name": area.name,
        "parent": area.parent_geography_id,
        "geographic_id": area.geographic_id,
        "geography_type": geography_type.name,
    }


def test_get_parent_geography_id_returns_expected_parent_geography_for_area(notify_db_session):
    parent_type = create_geography_type(route="local_authorities")
    parent_version = create_geography_version(geography_type_id=parent_type.id, state="active")
    parent_area = create_area(
        geography_type_id=parent_type.id,
        geography_version_id=parent_version.id,
        name="Parent LA",
    )

    parent_wkt = to_shape(parent_area.geometry).wkt
    parent_id = get_parent_geography_id(parent_wkt, parent_type_name="local_authorities")

    assert parent_id == parent_area.id


def test_get_parent_geography_id_returns_None_if_unable_to_source_parent_area(notify_db_session):
    # point that should not intersect any stored area (no areas created)
    centroid = shapely.Point(-10.0, 0.0).wkt

    parent_id = get_parent_geography_id(centroid, parent_type_name="local_authorities")
    assert parent_id is None


def test_add_custom_area_to_existing_areas_returns_expected_area(notify_db_session, sample_broadcast_service):
    # Create an existing area and use its geometry for the initial polygons
    area, _, _ = create_area_with_version_and_type()
    existing_wkt = to_shape(area.geometry).wkt

    alert_polygons = wkt_geometry_to_alert_polygons(existing_wkt)
    polygons = Polygons(polygons=alert_polygons)

    existing = {
        "ids": [str(area.id)],
        "names": [area.name],
        "simple_polygons": polygons.polygons,
    }
    message = create_broadcast_message(
        service=sample_broadcast_service,
        reference="reference",
        content="content",
        areas=existing,
    )

    data = {
        "radius": 5,
        "first_coordinate": 54.0,
        "second_coordinate": -2.0,
        "coordinate_type": "latitude_longitude",
    }

    updated_message, error_response, status_code = add_custom_area_to_existing_areas(
        message,
        type_name="coordinates",
        data=data,
    )

    assert updated_message.areas == {
        "aggregate_names": ["Test name", "5km around 54.0 latitude, -2.0 longitude"],
        "ids": [str(area.id), "coordinates_54.0_-2.0_5.0_latitude_longitude"],
        "names": ["Test name", "5km around 54.0 latitude, -2.0 longitude"],
        "simple_polygons": [[[54.65, -2.65], [54.65, 0.25], [53.2, 0.25], [53.2, -2.65], [54.65, -2.65]]],
    }


def test_get_parent_area_name_returns_expected_string(notify_db_session):
    parent_type = create_geography_type(route="local_authorities")
    parent_version = create_geography_version(geography_type_id=parent_type.id, state="active")
    parent_area = create_area(
        geography_type_id=parent_type.id,
        geography_version_id=parent_version.id,
        name="Leeds, City of",
    )

    centroid = dao_get_area_centroid(parent_area.id)
    parent_area_name = get_parent_area_name(centroid)

    assert parent_area_name == "City of Leeds"


def test_generate_centroid_for_coordinate_area_returns_expected_geometry():
    centroid_latlon = generate_centroid_for_coordinate_area(
        first_coordinate=54.0,
        second_coordinate=-2.0,
        coordinate_type="latitude_longitude",
    )
    geom = shapely.wkt.loads(centroid_latlon)
    assert geom.geom_type == "Point"
    assert pytest.approx(geom.y, rel=1e-6) == 54.0
    assert pytest.approx(geom.x, rel=1e-6) == -2.0

    centroid_en = generate_centroid_for_coordinate_area(
        first_coordinate=528000,
        second_coordinate=178000,
        coordinate_type="easting_northing",
    )
    geom_en = shapely.wkt.loads(centroid_en)
    assert geom_en.geom_type == "Point"


def test_ensure_valid_wkt_validates_wkt_correctly():
    # valid polygon remains unchanged
    valid_wkt = shapely.Point(-2.0, 54.0).buffer(0.1).wkt
    result = ensure_valid_wkt(valid_wkt)
    assert isinstance(result, str)
    assert result == valid_wkt

    # deliberately construct an invalid self‑intersecting polygon and ensure it is repaired
    coords = [(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)]
    invalid_geom = shapely.Polygon(coords)
    assert not invalid_geom.is_valid
    fixed = ensure_valid_wkt(invalid_geom.wkt)
    # ensure_valid_wkt returns either wkt string or (response, status)
    assert isinstance(fixed, str)
    repaired_geom = shapely.wkt.loads(fixed)
    assert repaired_geom.is_valid


def test_validate_bulk_area_input_returns_correct_error_message_for_input():
    # missing data
    assert validate_bulk_area_input([], "local_authorities") == "Enter at least 1 local authority"

    # duplicates
    assert validate_bulk_area_input(["Area 1", "Area 1"], "local_authorities") == "All local authorities must be unique"

    # exceeds limit
    too_many = [f"Area {i}" for i in range(26)]
    assert (
        validate_bulk_area_input(too_many, "local_authorities")
        == "Maximum of 25 local authorities allowed as a list in one emergency alert"
    )

    # valid list returns None
    assert validate_bulk_area_input(["Area 1", "Area 2"], "local_authorities") is None


def test_build_remaining_area_wkt_returns_expected_wkt(notify_db_session):
    # creates two stored areas
    area1, _, _ = create_area_with_version_and_type()
    area2, _, _ = create_area_with_version_and_type(geography_type_name="Test Type", geography_type_route="Test")

    existing_ids = [str(area1.id), str(area2.id)]
    remaining_ids, polygons, combined_source_ids = build_remaining_area_wkt(
        existing_ids,
        area_id_to_remove=str(area1.id),
    )

    assert remaining_ids == [str(area2.id)]
    assert combined_source_ids == [str(area2.id)]
    assert isinstance(polygons, list)
    assert len(polygons) > 0
