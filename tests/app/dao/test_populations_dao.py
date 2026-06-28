import pytest

from app.dao.populations_dao import dao_estimate_population_for_area


@pytest.mark.parametrize(
    "area, estimated_population",
    [
        (
            "POLYGON ((-3.092981 53.549283, -3.055212 53.549283, "
            "-3.055212 53.568045, -3.092981 53.568045, -3.092981 53.549283))",
            2420.1072053293447,
        ),
        (
            "POLYGON ((-3.069976 53.581704, -3.059332 53.525411, " "-3.051778 53.564579, -3.069976 53.581704))",
            1467.1212788958733,
        ),
        (
            "POLYGON ((-3.043192 53.516022, -3.026024 53.49785, "
            "-2.959068 53.510714, -3.004735 53.519696, -3.043192 53.516022))",
            4506.858628088665,
        ),
        (
            "POLYGON ((-2.997533 53.483143, -2.991009 53.450851, -2.936071 "
            "53.484164, -2.963197 53.502138, -2.997533 53.483143))",
            28022.185686176763,
        ),
        (
            "POLYGON ((-3.04423 53.528472, -3.039423 53.528472, -3.039423 "
            "53.530921, -3.04423 53.530921, -3.04423 53.528472))",
            41.49599612043222,
        ),
        # WKT for area in Manchester, no intersection with test areas so unable to estimate population
        (
            "POLYGON ((-2.289877 53.459438, -2.206097 53.459438, -2.206097 "
            "53.490497, -2.289877 53.490497, -2.289877 53.459438))",
            0,
        ),
    ],
)
def test_estimate_population_gives_accurate_estimate(area, estimated_population, add_population_test_data):
    assert dao_estimate_population_for_area(area) == estimated_population
