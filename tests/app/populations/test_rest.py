import pytest


@pytest.mark.parametrize(
    "data, expected_population_estimate",
    [
        (
            {
                "areas": (
                    "POLYGON ((-3.092981 53.549283, -3.055212 53.549283, "
                    "-3.055212 53.568045, -3.092981 53.568045, -3.092981 53.549283))"
                ),
            },
            2420.1072053293447,
        ),
        (
            {
                "areas": (
                    "POLYGON ((-3.049393 53.501525, -3.028793 53.501525, -3.028793 "
                    "53.513776, -3.049393 53.513776, -3.049393 53.501525))"
                ),
            },
            1507.8223210601932,
        ),
        (
            {
                "areas": (
                    "POLYGON ((-3.076854 53.572938, -3.081661 53.54398, "
                    "-3.026723 53.520717, -3.050759 53.562744, -3.076854 53.572938))"
                ),
            },
            4340.332039679511,
        ),
        (
            # WKT for area in Hull, no intersection with test areas so unable to estimate population
            {
                "areas": (
                    "POLYGON ((-0.376219 53.781992, -0.353557 53.75886, -0.294499 53.776515, -0.376219 53.781992))"
                ),
            },
            0,
        ),
    ],
)
def test_population_estimate_returned_for_valid_area(
    notify_db_session, add_population_test_data, admin_request, data, expected_population_estimate
):
    response = admin_request.post(
        "populations.get_population_estimate_for_area",
        _data=data,
        _expected_status=200,
    )

    assert response == expected_population_estimate


@pytest.mark.parametrize(
    "data, expected_errors",
    [
        (
            # Invalid WKT as the polygon isn't closed
            {},
            {"result": "error", "message": "Area must be provided for population estimation"},
        ),
        (
            # Invalid WKT as the polygon isn't closed
            {
                "areas": (
                    "POLYGON ((-3.092981 53.549283, -3.055212 53.549283, " "-3.055212 53.568045, -3.092981 53.568045))"
                ),
            },
            {"result": "error", "message": ["Invalid WKT string"]},
        ),
        (
            # Invalid as the area isn't Polygon or MultiPolygon
            {
                "areas": "LINESTRING (-3.092981 53.549283, -3.055212 "
                "53.549283, -3.055212 53.568045, -3.092981 53.568045)",
            },
            {"result": "error", "message": ["Area must be a Polygon or MultiPolygon"]},
        ),
        (
            # Invalid as Shapely determines geometry invalid as it is self-intersecting
            {
                "areas": (
                    "POLYGON ((-2.50445 53.357109, -1.70236 53.585984, "
                    "-2.427538 52.776186, -0.889282 53.298056, -2.50445 53.357109))"
                ),
            },
            {"result": "error", "message": ["Provided WKT area is not valid"]},
        ),
    ],
)
def test_population_estimate_validation_error_returned_for_invalid_area(
    notify_db_session, admin_request, data, expected_errors
):
    response = admin_request.post(
        "populations.get_population_estimate_for_area",
        _data=data,
        _expected_status=400,
    )

    assert response == expected_errors
