import uuid

import pytest

from tests.app.db import (
    create_area,
    create_area_with_version_and_type,
    create_broadcast_message,
    create_geography_type,
    create_geography_version,
    create_template,
)


def test_assert_get_area_returns_area_for_id(admin_request, sample_broadcast_service):
    area1_id = uuid.uuid4()
    area1, geography_type, geography_type = create_area_with_version_and_type(id=area1_id)
    response = admin_request.get(
        "areas.get_area", area_id=area1_id, service_id=sample_broadcast_service.id, _expected_status=200
    )

    assert response["data"] == {
        "geographic_id": area1.geographic_id,
        "geography_type": "Test route",
        "id": str(area1_id),
        "name": area1.name,
        "parent": area1.parent_geography_id,
    }


def test_assert_get_area_returns_400_when_area_not_found(notify_db_session, admin_request, sample_broadcast_service):
    response = admin_request.get(
        "areas.get_area", area_id=uuid.uuid4(), service_id=sample_broadcast_service.id, _expected_status=400
    )
    assert response == {"message": "No area with this ID"}


def test_assert_get_area_by_geographic_id_returns_area_with_geographic_id(
    notify_db_session, admin_request, sample_broadcast_service
):
    area1, geography_version, geography_type = create_area_with_version_and_type()
    response = admin_request.get(
        "areas.get_area_by_geographic_id_endpoint",
        geographic_id=str(area1.geographic_id),
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert response["data"] == {
        "geographic_id": area1.geographic_id,
        "geography_type": "Test route",
        "id": str(area1.id),
        "name": area1.name,
        "parent": area1.parent_geography_id,
    }


def test_assert_get_area_by_geographic_id_returns_None_if_incorrect_area_id(
    notify_db_session, admin_request, sample_broadcast_service
):
    response = admin_request.get(
        "areas.get_area_by_geographic_id_endpoint",
        geographic_id="fake-geographic-id",
        service_id=sample_broadcast_service.id,
        _expected_status=400,
    )

    assert response == {"message": "No area retrieved for this geographic ID."}


def test_get_areas_returns_areas(notify_db_session, admin_request, sample_broadcast_service):
    area1, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, geography_version, geography_type = create_area_with_version_and_type()

    response = admin_request.post(
        "areas.get_areas",
        service_id=sample_broadcast_service.id,
        _data={
            "area_ids": [str(area1.id), str(area2.id)],
            "area_names": [area1.name, area2.name],
        },
        _expected_status=200,
    )

    assert len(response["data"]) == 2
    assert [area.get("id") for area in response["data"]] == [str(area1.id), str(area2.id)]


def test_assert_area_is_grandparent_returns_bool_value(notify_db_session, admin_request, sample_broadcast_service):
    geography_type = create_geography_type(route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    ward_geography_type = create_geography_type(name="Wards", route="wards")
    create_geography_version(geography_type_id=ward_geography_type.id)

    grandparent = create_area(
        geography_type_id=geography_type.id, geography_version_id=geography_version.id, geographic_id="grandparent"
    )
    parent = create_area(
        parent_geography_id=grandparent.geographic_id,
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
        geographic_id="parent",
    )
    child = create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
        geographic_id="child",
    )

    resp_true = admin_request.get(
        "areas.is_grandparent",
        area_id=grandparent.id,
        _expected_status=200,
    )
    assert resp_true["data"] is True
    resp_false = admin_request.get(
        "areas.is_grandparent",
        area_id=child.id,
        _expected_status=200,
    )
    assert resp_false["data"] is False


def test_asserts_get_geography_types_and_examples_returns_valid_response_for_type(
    notify_db_session, admin_request, sample_broadcast_service
):
    area, geography_version, geography_type = create_area_with_version_and_type(geography_type_name="Local authorities")

    response = admin_request.get(
        "areas.get_geography_types_and_examples",
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert response["data"] == [
        {
            "examples": area.name,  # only the 1 area so 1 name
            "id": geography_type.id,
            "name": geography_type.name,
            "name_singular": geography_type.name_singular,
            "route": geography_type.route,
        }
    ]


def test_get_areas_for_type_returns_all_areas_for_valid_type(
    notify_db_session, admin_request, sample_broadcast_service
):
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    area1 = create_area(geography_type_id=geography_type.id, geography_version_id=geography_version.id)
    area2 = create_area(geography_type_id=geography_type.id, geography_version_id=geography_version.id)

    resp = admin_request.get(
        "areas.get_areas_for_type",
        type_name="local_authorities",
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert [a["geographic_id"] for a in resp["data"]] == [area1.geographic_id, area2.geographic_id]


def test_get_areas_for_type_returns_empty_list_for_invalid_type(
    notify_db_session, admin_request, sample_broadcast_service
):
    resp = admin_request.get(
        "areas.get_areas_for_type",
        type_name="not-a-real-type",
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert resp["data"] == []


def test_get_child_areas_for_parent_returns_all_child_areas_for_valid_parent(
    notify_db_session, admin_request, sample_broadcast_service
):
    geography_type = create_geography_type(route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    parent = create_area(geography_type_id=geography_type.id, geography_version_id=geography_version.id)
    child1 = create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
    )
    child2 = create_area(
        parent_geography_id=parent.geographic_id,
        geography_type_id=geography_type.id,
        geography_version_id=geography_version.id,
    )

    resp = admin_request.get(
        "areas.get_child_areas_for_parent",
        parent_geography_id=str(parent.geographic_id),
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert {a["geographic_id"] for a in resp["data"]} == {child1.geographic_id, child2.geographic_id}


def test_get_child_areas_for_parent_returns_empty_list_for_area_with_no_children(
    notify_db_session, admin_request, sample_broadcast_service
):
    geography_type = create_geography_type(route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    parent = create_area(geography_type_id=geography_type.id, geography_version_id=geography_version.id)

    resp = admin_request.get(
        "areas.get_child_areas_for_parent",
        parent_geography_id=str(parent.geographic_id),
        service_id=sample_broadcast_service.id,
        _expected_status=200,
    )

    assert resp["data"] == []


def test_get_postcode_centroid_returns_expected_centroid_for_area(
    notify_db_session, admin_request, sample_broadcast_service
):
    area, _, _ = create_area_with_version_and_type(geographic_id="Test Postcode", geography_type_route="postcodes")

    resp = admin_request.post(
        "areas.get_postcode_centroid",
        _data={"postcode": area.geographic_id},
        _expected_status=200,
    )

    assert resp["data"] == "POINT(-1.2 53.925000000000004)"  # Centroid WKT for default geometry


def test_get_postcode_centroid_returns_error_for_invalid_postcode(
    notify_db_session, admin_request, sample_broadcast_service
):
    area, _, _ = create_area_with_version_and_type(geography_type_route="postcodes")

    resp = admin_request.post(
        "areas.get_postcode_centroid",
        _data={"postcode": "NOT A REAL POSTCODE"},
        _expected_status=400,
    )
    assert resp == {"message": "Enter a postcode within the UK"}


@pytest.mark.parametrize(
    "data, expected_wkt",
    [
        (
            {"first_coordinate": 51, "second_coordinate": -0.3, "coordinate_type": "latitude_longitude"},
            "POINT (-0.3 51)",
        ),
        (
            {"first_coordinate": 528000, "second_coordinate": 178000, "coordinate_type": "easting_northing"},
            "POINT (-0.1578785176339254 51.48647326506538)",
        ),
    ],
)
def test_get_coordinate_centroid_returns_expected_centroid_for_area(
    notify_db_session, admin_request, sample_broadcast_service, data, expected_wkt
):
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_route="countries", geometry="".join(country_geometry)
    )

    resp = admin_request.post(
        "areas.get_coordinates_centroid",
        _data=data,
        _expected_status=200,
    )

    assert resp["data"] == expected_wkt  # Centroid WKT


def test_get_coordinates_centroid_returns_error_for_invalid_geometry(
    notify_db_session, admin_request, sample_broadcast_service
):
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_route="countries", geometry="".join(country_geometry)
    )

    resp = admin_request.post(
        "areas.get_coordinates_centroid",
        area_id=area.id,
        _data={"first_coordinate": 0, "second_coordinate": 0, "coordinate_type": "latitude_longitude"},
        _expected_status=400,
    )

    assert resp == {"message": "Enter coordinates within the UK"}


def test_get_areas_by_names_returns_expected_areas(notify_db_session, admin_request, sample_broadcast_service):
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    geography_version = create_geography_version(geography_type_id=geography_type.id)

    area1 = create_area(
        geography_type_id=geography_type.id, geography_version_id=geography_version.id, name="Local authority 1"
    )
    area2 = create_area(
        geography_type_id=geography_type.id, geography_version_id=geography_version.id, name="Local authority 2"
    )

    resp = admin_request.post(
        "areas.get_areas_by_names",
        type_name="local_authorities",
        _data={"area_names": ["Local authority 1", "Local authority 2"]},
        _expected_status=200,
    )
    assert resp["data"] == [str(area1.id), str(area2.id)]


@pytest.mark.parametrize(
    "data, expected_error_message",
    [
        # missing_data
        (
            {"area_names": []},
            "Enter at least 1 local authority",
        ),
        # duplicates
        (
            {"area_names": ["Local authority 1", "Local authority 1"]},
            "All local authorities must be unique",
        ),
        # invalid
        (
            {"area_names": ["Fake area"]},
            "Local authority 'Fake area' not found",
        ),
        # exceeds_limit
        (
            {"area_names": [f"Local authority {i}" for i in range(1, 27)]},
            "Maximum of 25 local authorities allowed as a list in one emergency alert",
        ),
    ],
)
def test_get_local_authorities_areas_by_names_returns_expected_error_for_invalid_input(
    notify_db_session, admin_request, sample_broadcast_service, data, expected_error_message
):
    geography_type = create_geography_type(name="Local authorities", route="local_authorities")
    create_geography_version(geography_type_id=geography_type.id)
    resp = admin_request.post(
        "areas.get_areas_by_names",
        type_name="local_authorities",
        _data=data,
        _expected_status=400,
    )

    assert resp == {"message": expected_error_message}


@pytest.mark.parametrize(
    "data, expected_error_message",
    [
        # missing_data
        (
            {"area_names": []},
            "Enter at least 1 Flood Warning TA code",
        ),
        # duplicates
        (
            {"area_names": ["Flood Warning TA code 1", "Flood Warning TA code 1"]},
            "All Flood Warning TA codes must be unique",
        ),
        # invalid
        (
            {"area_names": ["Fake area"]},
            "Flood Warning TA code not found",
        ),
        # exceeds_limit
        (
            {"area_names": [f"Flood Warning TA code {i}" for i in range(1, 27)]},
            "Maximum of 25 TA codes in an emergency alert",
        ),
    ],
)
def test_get_flood_warning_areas_by_names_returns_expected_error_for_invalid_input(
    notify_db_session, admin_request, sample_broadcast_service, data, expected_error_message
):
    geography_type = create_geography_type(name="Flood Warning areas", route="flood_warning_areas")
    create_geography_version(geography_type_id=geography_type.id)
    resp = admin_request.post(
        "areas.get_areas_by_names",
        type_name="flood_warning_areas",
        _data=data,
        _expected_status=400,
    )

    assert resp == {"message": expected_error_message}


def test_create_postcode_area_creates_valid_area_for_input(notify_db_session, admin_request, sample_broadcast_service):
    area, _, _ = create_area_with_version_and_type(
        geographic_id="Test Postcode",
        geography_type_route="postcodes",
    )

    resp = admin_request.post(
        "areas.create_postcode_area",
        _data={"postcode": "Test Postcode", "radius": 5},
        _expected_status=200,
    )
    assert "circle" in resp
    assert resp["id"] == "postcodes_-1.2_53.925000000000004_5_Test Postcode"


def test_create_postcode_area_returns_error_for_missing_postcode_or_radius(
    notify_db_session, admin_request, sample_broadcast_service
):
    # Missing postcode
    resp = admin_request.post(
        "areas.create_postcode_area",
        _data={"radius": 5},
        _expected_status=400,
    )
    assert resp == {"message": "Enter postcode and radius to create postcode area"}

    # Missing radius
    resp = admin_request.post(
        "areas.create_postcode_area",
        _data={"postcode": "Test Postcode"},
        _expected_status=400,
    )
    assert resp == {"message": "Enter postcode and radius to create postcode area"}


def test_create_coordinate_area_creates_valid_area_for_input(
    notify_db_session, admin_request, sample_broadcast_service
):
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_route="countries", geometry="".join(country_geometry)
    )
    resp = admin_request.post(
        "areas.create_coordinate_area",
        _data={
            "first_coordinate": 528000,
            "second_coordinate": 178000,
            "coordinate_type": "easting_northing",
            "radius": 5,
        },
        _expected_status=200,
    )
    assert resp["data"].startswith("POLYGON((")  # Returns POLYGON WKT string


def test_create_coordinate_area_returns_error_for_external_coordinates(
    notify_db_session, admin_request, sample_broadcast_service
):
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_route="countries", geometry="".join(country_geometry)
    )
    resp = admin_request.post(
        "areas.create_coordinate_area",
        _data={
            "first_coordinate": 0,
            "second_coordinate": 0,
            "coordinate_type": "easting_northing",
            "radius": 5,
        },
        _expected_status=400,
    )

    assert resp == {"message": "Enter coordinates within the UK"}


@pytest.mark.parametrize(
    "data, expected_bool",
    [
        (
            {"first_coordinate": 528000, "second_coordinate": 178000, "coordinate_type": "easting_northing"},
            True,
        ),
        (
            {
                "first_coordinate": 0,
                "second_coordinate": 0,
                "coordinate_type": "easting_northing",
            },
            False,
        ),
        (
            {"first_coordinate": 54, "second_coordinate": -2, "coordinate_type": "latitude_longitude"},
            True,
        ),
        (
            {
                "first_coordinate": 0,
                "second_coordinate": 0,
                "coordinate_type": "latitude_longitude",
            },
            False,
        ),
    ],
)
def test_check_coordinates_valid_returns_whether_coordinates_valid_or_not(
    notify_db_session, admin_request, sample_broadcast_service, data, expected_bool
):
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    area, geography_version, geography_type = create_area_with_version_and_type(
        geography_type_route="countries", geometry="".join(country_geometry)
    )

    resp_valid = admin_request.post(
        "areas.check_coordinates_valid",
        _data=data,
        _expected_status=200,
    )
    assert resp_valid["data"] is expected_bool


def test_build_alert_area_for_ids_returns_expected_area_dict(
    notify_db_session, admin_request, sample_broadcast_service
):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()

    resp = admin_request.post(
        "areas.build_alert_area_for_ids",
        service_id=sample_broadcast_service.id,
        _data={"area_ids": [str(area1.id), str(area2.id)]},
        _expected_status=200,
    )

    assert resp == {
        "aggregate_names": [area1.name, area2.name],
        "ids": [str(area1.id), str(area2.id)],
        "names": [area1.name, area2.name],
        "simple_polygons": [[[54.65, -2.65], [54.65, 0.25], [53.2, 0.25], [53.2, -2.65], [54.65, -2.65]]],
    }


def test_add_areas_to_broadcast_message_returns_expected_dict(
    notify_db_session, admin_request, sample_broadcast_service
):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()
    message = create_broadcast_message(
        service=sample_broadcast_service,
        reference="reference",
        content="content",
        areas={
            "ids": ["Starting area ID"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
            "names": ["Starting area"],
            "aggregate_names": ["Starting area"],
        },
    )
    resp = admin_request.post(
        "areas.add_areas",
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _data={"area_ids": [str(area2.id)]},
        _expected_status=200,
    )

    assert resp["areas"] == {
        "aggregate_names": ["Starting area", area2.name],
        "ids": ["Starting area ID", str(area2.id)],
        "names": ["Starting area", area2.name],
        "simple_polygons": [[[53.2, -2.65], [54.65, -2.65], [54.65, 0.25], [53.2, 0.25], [53.2, -2.65]]],
    }


def test_add_areas_to_template_returns_expected_dict(notify_db_session, admin_request, sample_broadcast_service):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()
    template = create_template(
        sample_broadcast_service,
        template_name="Template Name",
        template_type="broadcast",
    )
    resp = admin_request.post(
        "areas.add_areas",
        service_id=sample_broadcast_service.id,
        message_id=template.id,
        message_type="templates",
        _data={"area_ids": [str(area2.id)]},
        _expected_status=200,
    )

    assert resp["data"].get("areas") == {
        "aggregate_names": [area2.name],
        "ids": [str(area2.id)],
        "names": [area2.name],
        "simple_polygons": [[[53.2, -2.65], [53.2, 0.25], [54.65, 0.25], [54.65, -2.65], [53.2, -2.65]]],
    }


def test_add_custom_postcode_area_to_broadcast_message(notify_db_session, admin_request, sample_broadcast_service):
    radius = 5
    area, _, _ = create_area_with_version_and_type(
        geographic_id="Test Postcode", geography_type_route="postcodes", name="Test Postcode"
    )

    message = create_broadcast_message(
        service=sample_broadcast_service,
        reference="reference",
        content="content",
        areas={
            "ids": ["Starting area ID"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
            "names": ["Starting area"],
            "aggregate_names": ["Starting area"],
        },
    )

    resp = admin_request.post(
        "areas.add_custom_areas",
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        type_name="postcodes",
        _data={"postcode": "Test Postcode", "radius": radius},
        _expected_status=200,
    )
    response_areas = resp["areas"]
    assert response_areas["ids"] == ["Starting area ID", "postcodes_-1.2_53.925000000000004_5.0_Test Postcode"]
    assert response_areas["aggregate_names"] == ["Starting area", f"{radius:g}km around the postcode {area.name}"]
    assert response_areas["names"] == ["Starting area", f"{radius:g}km around the postcode {area.name}"]


def test_add_custom_postcode_area_to_template(notify_db_session, admin_request, sample_broadcast_service):
    area, _, _ = create_area_with_version_and_type(
        geographic_id="Template Postcode", geography_type_route="postcodes", name="Template Postcode"
    )
    radius = 3.0

    template = create_template(
        sample_broadcast_service,
        template_name="Template Name",
        template_type="broadcast",
        areas={
            "ids": ["Starting area ID"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
            "names": ["Starting area"],
            "aggregate_names": ["Starting area"],
        },
    )

    resp = admin_request.post(
        "areas.add_custom_areas",
        service_id=sample_broadcast_service.id,
        message_id=template.id,
        message_type="templates",
        type_name="postcodes",
        _data={"postcode": "Template Postcode", "radius": radius},
        _expected_status=200,
    )
    response_areas = resp.get("areas")
    assert response_areas["ids"] == ["Starting area ID", "postcodes_-1.2_53.925000000000004_3.0_Template Postcode"]
    assert response_areas["aggregate_names"] == ["Starting area", f"{radius:g}km around the postcode {area.name}"]
    assert response_areas["names"] == ["Starting area", f"{radius:g}km around the postcode {area.name}"]


def test_add_custom_coordinate_area_to_broadcast_message(notify_db_session, admin_request, sample_broadcast_service):
    # Country geometry so coordinate validity works and parent lookup is possible
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    create_area_with_version_and_type(
        geography_type_route="countries",
        geometry="".join(country_geometry),
    )

    radius = 10.0

    message = create_broadcast_message(
        service=sample_broadcast_service,
        reference="reference",
        content="content",
        areas={
            "ids": ["Starting area"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
            "names": ["Starting area"],
            "aggregate_names": ["Starting area"],
        },
    )

    resp = admin_request.post(
        "areas.add_custom_areas",
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        type_name="coordinates",
        _data={
            "first_coordinate": 54.0,
            "second_coordinate": -2.0,
            "coordinate_type": "latitude_longitude",
            "radius": radius,
        },
        _expected_status=200,
    )

    response_areas = resp["areas"]
    assert response_areas["ids"] == ["Starting area", "coordinates_54.0_-2.0_10.0_latitude_longitude"]
    assert response_areas["aggregate_names"] == ["Starting area", "10km around 54.0 latitude, -2.0 longitude"]
    assert response_areas["names"] == ["Starting area", "10km around 54.0 latitude, -2.0 longitude"]


def test_add_custom_coordinate_area_to_template(notify_db_session, admin_request, sample_broadcast_service):
    # Country geometry so coordinate validity works and parent lookup is possible
    country_geometry = (
        "0103000020E61000000100000005000000CDCCCCCCCC4C21",
        "C0CDCCCCCCCCEC48407B14AE47E17AFC3FCDCCCCCCCCEC48407B14AE47E17AFC3FAE",
        "47E17A146E4E40CDCCCCCCCC4C21C0AE47E17A146E4E40CDCCCCCCCC4C21C0CDCCCCCCCCEC4840",
    )
    create_area_with_version_and_type(
        geography_type_route="countries",
        geometry="".join(country_geometry),
    )

    first_coordinate = 54.0
    second_coordinate = -2.0
    radius = 10.0

    template = create_template(
        sample_broadcast_service,
        template_name="Template Name",
        template_type="broadcast",
        areas={
            "ids": ["Starting area"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
            "names": ["Starting area"],
            "aggregate_names": ["Starting area"],
        },
    )

    resp = admin_request.post(
        "areas.add_custom_areas",
        service_id=sample_broadcast_service.id,
        message_id=template.id,
        message_type="templates",
        type_name="coordinates",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": "latitude_longitude",
            "radius": radius,
        },
        _expected_status=200,
    )

    response_areas = resp.get("areas")
    assert response_areas["ids"] == [
        "Starting area",
        f"coordinates_{first_coordinate}_{second_coordinate}_{radius}_latitude_longitude",
    ]
    assert response_areas["aggregate_names"] == [
        "Starting area",
        f"{radius:g}km around {first_coordinate} latitude, {second_coordinate} longitude",
    ]
    assert response_areas["names"] == [
        "Starting area",
        f"{radius:g}km around {first_coordinate} latitude, {second_coordinate} longitude",
    ]


def test_remove_area_from_broadcast_message_returns_expected_area_dict(
    notify_db_session, admin_request, sample_broadcast_service
):
    area1, _, _ = create_area_with_version_and_type(
        geography_type_name="Test type", geography_type_route="Test route 2"
    )
    area2, _, _ = create_area_with_version_and_type()

    message = create_broadcast_message(
        service=sample_broadcast_service,
        reference="reference",
        content="content",
        areas={
            "aggregate_names": ["Starting area", area2.name],
            "ids": ["Starting area ID", str(area2.id)],
            "names": ["Starting area", area2.name],
            "simple_polygons": [[[53.2, -2.65], [54.65, -2.65], [54.65, 0.25], [53.2, 0.25], [53.2, -2.65]]],
        },
    )

    resp = admin_request.post(
        "areas.remove_area",
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _data={"area_id": "Starting area ID"},
        _expected_status=200,
    )

    assert resp["areas"] == {
        "aggregate_names": [area2.name],
        "ids": [str(area2.id)],
        "names": [area2.name],
        "simple_polygons": [[[53.2, -2.65], [53.2, 0.25], [54.65, 0.25], [54.65, -2.65], [53.2, -2.65]]],
    }
