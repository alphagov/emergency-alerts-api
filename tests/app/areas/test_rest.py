import uuid

import pytest

from app.schemas import (
    template_schema,
)
from tests.app.db import (
    create_area,
    create_area_with_type_and_version,
    create_broadcast_message,
    create_country_area_data_for_coordinates_checks,
    create_geography_type,
    create_geography_version,
    create_template,
)


def test_get_area_by_id_returns_expected_area(admin_request, notify_db_session):
    test_area = create_area_with_type_and_version(notify_db_session)
    resp = admin_request.get("areas.get_area_by_id", area_id=test_area.id)
    assert resp["data"] == {
        **test_area.serialize(),
        # Serialize methods returns all values as strings so cast the existing uuid values to strings
        "id": str(test_area.id),
        "geography_version_id": str(test_area.geography_version_id),
        "geography_type_name": "test_route",
    }


def test_get_area_by_id_returns_error_response_if_nonexistent_area(admin_request, notify_db_session):
    nonexistent_area_id = uuid.uuid4()
    resp = admin_request.get("areas.get_area_by_id", area_id=nonexistent_area_id, _expected_status=404)
    assert resp["message"] == "Area not found"


def test_get_areas_by_ids_returns_expected_predefined_areas(admin_request, notify_db_session):
    test_area1 = create_area_with_type_and_version(notify_db_session)
    # Second test area can be part of same geography version as first
    test_area2 = create_area(notify_db_session, test_area1.geography_version_id, name="Test area 2")
    resp = admin_request.post("areas.get_areas_by_ids", _data={"area_ids": [str(test_area1.id), str(test_area2.id)]})
    expected_areas = [
        {
            **test_area1.serialize(),
            "id": str(test_area1.id),
            "geography_version_id": str(test_area1.geography_version_id),
            "geography_type_name": "test_route",
        },
        {
            **test_area2.serialize(),
            "id": str(test_area2.id),
            "geography_version_id": str(test_area2.geography_version_id),
            "geography_type_name": "test_route",
        },
    ]

    areas_by_id = {area["id"]: area for area in resp["data"]}
    assert [areas_by_id[area["id"]] for area in expected_areas] == expected_areas


def test_get_areas_by_ids_returns_expected_postcode_areas(admin_request):
    postcode_area_id = "postcodes_-2.09627_57.15_30.0_AB10 1AL"
    radius = 30
    postcode = "AB10 1AL"
    resp = admin_request.post(
        "areas.get_areas_by_ids",
        _data={"area_ids": [postcode_area_id]},
    )

    assert resp["data"] == [
        {
            "id": postcode_area_id,
            "name": f"{radius:g}km around the postcode {postcode}",
            "geographic_id": postcode,
            "geography_type_name": "postcodes",
        }
    ]


@pytest.mark.parametrize(
    "coordinate_area_id, expected_name",
    [
        (
            "coordinates_54.0_-2.0_30.0_latitude_longitude",
            "30km around the easting of 54 and the northing of -2",
        ),
        (
            "coordinates_400000.0_300000.0_30.0_easting_northing",
            "30km around the easting of 400000 and the northing of 300000",
        ),
    ],
)
def test_get_areas_by_ids_returns_expected_coordinate_areas(admin_request, coordinate_area_id, expected_name):
    resp = admin_request.post(
        "areas.get_areas_by_ids",
        _data={"area_ids": [coordinate_area_id]},
    )

    assert resp["data"] == [
        {
            "id": coordinate_area_id,
            "name": expected_name,
            "geographic_id": None,
            "geography_type_name": "coordinates",
        }
    ]


@pytest.mark.parametrize(
    "coordinate_area_id, expected_error",
    [
        (
            # ID ends with postcode not coordinate_type
            "coordinates_-2_57.15_30.0_AB10 1AL",
            "Invalid coordinate values or coordinate type",
        ),
        (
            # ID doesn't have the correct format - so splits incorrectly, raising ValueError
            "coordinates_300000.0_30.0_easting_northing",
            "Invalid coordinate area ID: 'coordinates_300000.0_30.0_easting_northing'",
        ),
        (
            # ID doesn't have the correct format - so splits incorrectly, raising ValueError
            "coordinates",
            "Invalid coordinate area ID: 'coordinates'",
        ),
    ],
)
def test_get_areas_by_ids_returns_expected_error_for_invalid_coordinate_ids(
    admin_request, coordinate_area_id, expected_error
):
    resp = admin_request.post("areas.get_areas_by_ids", _data={"area_ids": [coordinate_area_id]}, _expected_status=400)
    assert resp["message"] == expected_error


def test_get_areas_by_ids_returns_error_if_nonexistent_area(admin_request, notify_db_session):
    nonexistent_area_id = uuid.uuid4()
    resp = admin_request.post(
        "areas.get_areas_by_ids", _data={"area_ids": [str(nonexistent_area_id)]}, _expected_status=400
    )
    assert resp["message"] == "No area could be found for one or more area IDs"


def test_get_areas_by_version_id_returns_expected_areas(admin_request, notify_db_session):
    test_area1 = create_area_with_type_and_version(notify_db_session)
    # Second test area can be part of same geography version as first
    test_area2 = create_area(
        notify_db_session,
        test_area1.geography_version_id,
        geographic_id="test456",
        name="Test area 2",
    )

    resp = admin_request.get("areas.get_areas_by_version_id", version_id=test_area1.geography_version_id)

    assert resp["data"] == [
        {
            **test_area1.serialize(),
            "id": str(test_area1.id),
            "geography_version_id": str(test_area1.geography_version_id),
        },
        {
            **test_area2.serialize(),
            # Serialize methods returns all values as strings so cast the existing uuid values to strings
            "id": str(test_area2.id),
            "geography_version_id": str(test_area2.geography_version_id),
        },
    ]


def test_get_areas_by_version_id_returns_no_areas_if_version_has_no_areas(admin_request, notify_db_session):
    test_type = create_geography_type(notify_db_session)
    test_version = create_geography_version(notify_db_session, geography_type_id=test_type.id)
    resp = admin_request.get("areas.get_areas_by_version_id", version_id=str(test_version.id))
    assert resp["data"] == []


def test_get_local_authorities_areas_by_names_returns_expected_area_ids(admin_request, notify_db_session):
    local_authorities_type = create_geography_type(
        notify_db_session,
        route="counties_and_unitary_authorities",
    )
    version = create_geography_version(
        notify_db_session,
        geography_type_id=local_authorities_type.id,
    )
    test_area1 = create_area(
        notify_db_session,
        geography_version_id=version.id,
    )
    resp = admin_request.post(
        "areas.get_local_authorities_areas_by_names",
        _data={"area_names": [str(test_area1.name)]},
    )

    assert resp == {"data": [str(test_area1.id)]}


@pytest.mark.parametrize(
    "area_names, expected_error",
    [
        (["Test Area", "Test Area"], "Local authority 'Test Area' currently appears in the list more than once"),
        (
            [f"Test Area {number}" for number in range(26)],
            "Maximum of 25 local authorities allowed as a list in one emergency alert",
        ),
        ([], "Enter at least 1 local authority"),
        (["Fake area"], "Local authority 'Fake area' not found"),
    ],
)
def test_get_local_authorities_areas_by_names_returns_error_response_for_invalid_area_names(
    admin_request, notify_db_session, area_names, expected_error
):
    local_authorities_type = create_geography_type(
        notify_db_session,
        route="counties_and_unitary_authorities",
    )
    version = create_geography_version(
        notify_db_session,
        geography_type_id=local_authorities_type.id,
    )
    create_area(
        notify_db_session,
        geography_version_id=version.id,
    )
    resp = admin_request.post(
        "areas.get_local_authorities_areas_by_names",
        _data={"area_names": area_names},
        _expected_status=400,
    )
    assert resp["message"] == expected_error


def test_get_flood_warning_areas_by_geographic_ids_returns_expected_areas(admin_request, notify_db_session):
    flood_warnings_type = create_geography_type(
        notify_db_session,
        route="flood_warning_areas",
    )
    version = create_geography_version(
        notify_db_session,
        geography_type_id=flood_warnings_type.id,
    )
    test_area1 = create_area(
        notify_db_session,
        geography_version_id=version.id,
    )
    resp = admin_request.post(
        "areas.get_flood_warning_areas_by_geographic_ids",
        _data={"ta_codes": [str(test_area1.geographic_id)]},
    )

    assert resp["data"] == [str(test_area1.id)]


@pytest.mark.parametrize(
    "ta_codes, expected_error",
    [
        (["test123", "test123"], "Flood Warning TA code 'test123' appears in the list more than once"),
        (
            [f"test{number}" for number in range(26)],
            "Maximum of 25 TA codes in an emergency alert",
        ),
        ([], "Enter at least 1 Flood Warning TA code"),
        (["test12345"], "Flood Warning TA Code 'test12345' not found"),
    ],
)
def test_get_flood_warning_areas_by_geographic_ids_returns_error_response_for_invalid_ids(
    admin_request, notify_db_session, ta_codes, expected_error
):
    flood_warnings_type = create_geography_type(
        notify_db_session,
        route="flood_warning_areas",
    )
    version = create_geography_version(
        notify_db_session,
        geography_type_id=flood_warnings_type.id,
    )
    create_area(
        notify_db_session,
        geography_version_id=version.id,
    )
    resp = admin_request.post(
        "areas.get_flood_warning_areas_by_geographic_ids",
        _data={"ta_codes": ta_codes},
        _expected_status=400,
    )

    assert resp["message"] == expected_error


def test_get_geography_types_returns_expected_geography_types(admin_request, notify_db_session):
    test_type = create_geography_type(notify_db_session)
    test_version = create_geography_version(notify_db_session, geography_type_id=test_type.id)
    resp = admin_request.get("areas.get_geography_types")
    # 3 types, test_type, local_authorities (the composite type we make) and coordinates
    assert len(resp["data"]) == 3
    assert {
        "id": str(test_type.id),
        "name": test_type.name,
        "name_singular": test_type.name_singular,
        "route": test_type.route,
        "version_id": str(test_version.id),
    } in resp["data"]


def test_get_geography_type_examples_returns_expected_example_content(admin_request, notify_db_session):
    test_area = create_area_with_type_and_version(notify_db_session)
    create_area(notify_db_session, geography_version_id=test_area.geography_version_id)
    create_area(notify_db_session, geography_version_id=test_area.geography_version_id)
    create_area(notify_db_session, geography_version_id=test_area.geography_version_id)
    resp = admin_request.get("areas.get_geography_type_examples", type_route="test_route")
    assert resp["data"] == "Test Area, Test Area, Test Area and Test Area"


def test_get_geography_type_examples_returns_empty_response_if_no_geography_types(admin_request, notify_db_session):
    resp = admin_request.get("areas.get_geography_type_examples", type_route="test_route")
    assert resp["data"] is None


# ---------------------------


@pytest.mark.parametrize("message_type", ["broadcast", "templates"])
def test_add_areas_returns_expected_updated_message(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
    message_type,
):
    test_area = create_area_with_type_and_version(notify_db_session)

    if message_type == "broadcast":
        message = create_broadcast_message(service=sample_broadcast_service, content="test", reference="test")
    else:
        message = create_template(sample_broadcast_service)

    resp = admin_request.post(
        "areas.add_areas",
        _data={
            "area_ids": [str(test_area.id)],
            "version_id": str(test_area.geography_version_id),
        },
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type=message_type,
    )

    assert str(test_area.id) in message.areas.get("ids")

    if message_type == "broadcast":
        assert resp == message.serialize()
    else:
        assert resp == template_schema.dump(message)


def test_add_areas_returns_error_when_area_ids_are_empty(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
):
    message = create_broadcast_message(service=sample_broadcast_service, content="test", reference="test")
    resp = admin_request.post(
        "areas.add_areas",
        _data={"area_ids": [], "version_id": ""},
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _expected_status=400,
    )

    assert resp["message"] == "area_ids is required"


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, coordinate_type, expected_result",
    [
        # Valid coordinates
        (530111, 170000, "easting_northing", True),
        (54.0, -2.0, "latitude_longitude", True),
        # Invalid coordinates types
        ("invalid", 300000, "easting_northing", False),
        (54.0, "invalid", "latitude_longitude", False),
        # Missing coordinates
        (None, 300000, "easting_northing", False),
        # Unsupported coordinate type
        (400000, 300000, "unsupported", False),
    ],
)
def test_check_coordinates_valid_returns_whether_coordinates_valid_or_not(
    admin_request,
    notify_db_session,
    first_coordinate,
    second_coordinate,
    coordinate_type,
    expected_result,
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    resp = admin_request.post(
        "areas.check_coordinates_valid",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
        },
    )

    assert resp["data"] is expected_result


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, radius, coordinate_type",
    [
        (530111, 170000, 5.0, "easting_northing"),
        (54.0, -2.0, 5.0, "latitude_longitude"),
    ],
)
def test_create_coordinate_area_returns_expected_area_wkt(
    admin_request, notify_db_session, first_coordinate, second_coordinate, radius, coordinate_type
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    resp = admin_request.post(
        "areas.create_coordinate_area",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
            "radius": radius,
        },
    )
    assert resp["data"].startswith("POLYGON")


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, radius, coordinate_type, expected_error",
    [
        (100, 100, 5.0, "easting_northing", "Enter coordinates within the UK"),
        (100, 100, 5.0, "latitude_longitude", "Enter coordinates within the UK"),
        (None, -2.0, 5.0, "latitude_longitude", "Coordinates and radius must be valid values"),
        (54.0, -2.0, None, "latitude_longitude", "Coordinates and radius must be valid values"),
    ],
)
def test_create_coordinate_area_returns_error_response_for_invalid_data(
    admin_request, notify_db_session, first_coordinate, second_coordinate, radius, coordinate_type, expected_error
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    resp = admin_request.post(
        "areas.create_coordinate_area",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
            "radius": radius,
        },
        _expected_status=400,
    )

    assert resp["message"] == expected_error


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, coordinate_type",
    [
        (530111, 170000, "easting_northing"),
        (54.0, -2.0, "latitude_longitude"),
    ],
)
def test_get_coordinates_centroid_returns_expected_centroid_wkt(
    admin_request,
    notify_db_session,
    first_coordinate,
    second_coordinate,
    coordinate_type,
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    resp = admin_request.post(
        "areas.get_coordinates_centroid",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
        },
    )

    assert resp["data"].startswith("POINT")


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, coordinate_type",
    [
        (54.0, "invalid", "latitude_longitude"),
        (None, 300000, "easting_northing"),
    ],
)
def test_get_coordinates_centroid_returns_expected_error_for_invalid_data(
    admin_request,
    notify_db_session,
    first_coordinate,
    second_coordinate,
    coordinate_type,
):
    resp = admin_request.post(
        "areas.get_coordinates_centroid",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
        },
        _expected_status=400,
    )

    assert resp["message"] == "Enter coordinates within the UK"


def test_get_postcode_centroid_returns_expected_centroid_wkt(admin_request, notify_db_session):
    postcode = "AB10 1AL"
    postcode_type = create_geography_type(
        notify_db_session,
        name="Postcodes",
        route="postcodes",
        name_singular="postcode",
    )
    postcode_version = create_geography_version(
        notify_db_session,
        geography_type_id=postcode_type.id,
    )
    create_area(
        notify_db_session,
        geography_version_id=postcode_version.id,
        geographic_id=postcode,
    )

    resp = admin_request.post(
        "areas.get_postcode_centroid",
        _data={"postcode": postcode},
    )
    assert resp["data"] == "POINT (-0.125 51.50499999999999)"


@pytest.mark.parametrize(
    "postcode",
    [
        None,
        "",
        "AB10 1ZZ",
    ],
)
def test_get_postcode_centroid_returns_expected_error_for_invalid_data(
    admin_request,
    notify_db_session,
    postcode,
):
    postcode_type = create_geography_type(notify_db_session, route="postcodes")
    create_geography_version(notify_db_session, geography_type_id=postcode_type.id)
    resp = admin_request.post(
        "areas.get_postcode_centroid",
        _data={"postcode": postcode},
        _expected_status=400,
    )
    assert resp["message"] == "Enter a postcode within the UK"


def test_create_postcode_area_returns_expected_area_wkt(admin_request, notify_db_session):
    postcode = "AB10 1AL"
    postcode_type = create_geography_type(
        notify_db_session,
        name="Postcodes",
        route="postcodes",
        name_singular="postcode",
    )
    postcode_version = create_geography_version(
        notify_db_session,
        geography_type_id=postcode_type.id,
    )
    create_area(
        notify_db_session,
        geography_version_id=postcode_version.id,
        geographic_id=postcode,
    )

    resp = admin_request.post(
        "areas.create_postcode_area",
        _data={"postcode": postcode, "radius": 5},
    )
    assert resp["circle"].startswith("POLYGON")
    assert resp["id"] == "postcodes_-0.12500000000000003_51.50499999999999_5_AB10 1AL"


def test_create_postcode_area_returns_error_response_for_invalid_data(admin_request, notify_db_session):
    # Assert that when invalid data posted i.e. missing or will raise TypeError - error response returned
    resp = admin_request.post(
        "areas.create_postcode_area",
        _data={"postcode": "", "radius": 5},
        _expected_status=400,
    )
    assert resp["message"] == "Enter postcode and radius to create postcode area"


@pytest.mark.parametrize("message_type", ["broadcast", "templates"])
def test_add_postcodes_area_returns_expected_updated_message(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
    message_type,
):
    postcode = "AB10 1AL"
    radius = 5

    postcode_type = create_geography_type(
        notify_db_session,
        name="Postcodes",
        route="postcodes",
        name_singular="postcode",
    )
    postcode_version = create_geography_version(
        notify_db_session,
        geography_type_id=postcode_type.id,
    )
    create_area(
        notify_db_session,
        geography_version_id=postcode_version.id,
        geographic_id=postcode,
    )

    if message_type == "broadcast":
        message = create_broadcast_message(
            service=sample_broadcast_service,
            content="test",
            reference="test",
        )
    else:
        message = create_template(sample_broadcast_service)

    resp = admin_request.post(
        "areas.add_postcodes_area",
        _data={
            "postcode": postcode,
            "radius": radius,
        },
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type=message_type,
    )

    assert message.areas["ids"] == ["postcodes_-0.12500000000000003_51.50499999999999_5_AB10 1AL"]

    if message_type == "broadcast":
        assert resp == message.serialize()
    else:
        assert resp == template_schema.dump(message)


@pytest.mark.parametrize(
    "postcode, radius, expected_error",
    [
        (
            "",
            5,
            "Enter postcode and radius to create postcode area",
        ),
        (
            "AB10 1AL",
            None,
            "Enter postcode and radius to create postcode area",
        ),
    ],
)
def test_add_postcodes_area_returns_expected_error_response_for_invalid_data(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
    postcode,
    radius,
    expected_error,
):
    message = create_broadcast_message(
        service=sample_broadcast_service,
        content="test",
        reference="test",
    )

    resp = admin_request.post(
        "areas.add_postcodes_area",
        _data={
            "postcode": postcode,
            "radius": radius,
        },
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _expected_status=400,
    )

    assert resp["message"] == expected_error


@pytest.mark.parametrize("message_type", ["broadcast", "templates"])
def test_add_coordinates_area_returns_expected_updated_message(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
    message_type,
):
    create_country_area_data_for_coordinates_checks(notify_db_session)
    if message_type == "broadcast":
        message = create_broadcast_message(
            service=sample_broadcast_service,
            content="test",
            reference="test",
        )
    else:
        message = create_template(sample_broadcast_service)

    first_coordinate = 54.0
    second_coordinate = -2.0
    radius = 5.0
    coordinate_type = "latitude_longitude"

    resp = admin_request.post(
        "areas.add_coordinates_area",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
            "radius": radius,
        },
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type=message_type,
    )

    expected_area_id = f"coordinates_{first_coordinate}_{second_coordinate}_{radius}_{coordinate_type}"

    assert message.areas["ids"] == [expected_area_id]

    if message_type == "broadcast":
        assert resp == message.serialize()
    else:
        assert resp == template_schema.dump(message)


@pytest.mark.parametrize(
    "first_coordinate, second_coordinate, coordinate_type",
    [(None, -2.0, "latitude_longitude"), (54.0, None, "latitude_longitude")],
)
def test_add_coordinates_area_returns_expected_error_response_for_invalid_data(
    admin_request,
    sample_broadcast_service,
    first_coordinate,
    second_coordinate,
    coordinate_type,
):
    message = create_broadcast_message(
        service=sample_broadcast_service,
        content="test",
        reference="test",
    )

    resp = admin_request.post(
        "areas.add_coordinates_area",
        _data={
            "first_coordinate": first_coordinate,
            "second_coordinate": second_coordinate,
            "coordinate_type": coordinate_type,
            "radius": 5,
        },
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _expected_status=400,
    )
    assert resp["message"] == "Coordinates and radius must be valid values"


@pytest.mark.parametrize("message_type", ["broadcast", "templates"])
def test_remove_area_returns_expected_updated_message(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
    message_type,
):
    test_area = create_area_with_type_and_version(notify_db_session)

    if message_type == "broadcast":
        message = create_broadcast_message(
            service=sample_broadcast_service,
            content="test",
            reference="test",
        )
    else:
        message = create_template(sample_broadcast_service)

    message.areas = {
        "ids": [str(test_area.id)],
        "names": [test_area.name],
        "aggregate_names": [test_area.name],
        "simple_polygons": [],
    }
    notify_db_session.commit()

    resp = admin_request.post(
        "areas.remove_area",
        _data={"area_id": str(test_area.id)},
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type=message_type,
    )

    assert message.areas == {"aggregate_names": [], "ids": [], "names": [], "simple_polygons": []}

    if message_type == "broadcast":
        assert resp == message.serialize()
    else:
        assert resp == template_schema.dump(message)


def test_remove_area_returns_expetced_error_response_for_invalid_data(
    admin_request,
    notify_db_session,
    sample_broadcast_service,
):
    message = create_broadcast_message(
        service=sample_broadcast_service,
        content="test",
        reference="test",
    )

    resp = admin_request.post(
        "areas.remove_area",
        _data={"area_id": None},
        service_id=sample_broadcast_service.id,
        message_id=message.id,
        message_type="broadcast",
        _expected_status=400,
    )

    assert resp["message"] == "area_id is required"
