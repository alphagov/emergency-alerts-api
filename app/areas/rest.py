import uuid

from emergency_alerts_utils.formatters import formatted_list
from flask import Blueprint, jsonify

from app.dao.areas_dao import AreasDAO

areas_blueprint = Blueprint(
    "areas",
    __name__,
    url_prefix="/areas",
)


@areas_blueprint.route("/geography-types", methods=["GET"])
def get_geography_types():
    """Returns a list of geography types/libraries."""
    results = AreasDAO.get_geography_types()
    local_authority_routes = ["counties_and_unitary_authorities", "local_authority_districts"]
    geography_types = []

    # Combine county and unitary authorities and local authority districts
    for _, geography_type in results:
        if geography_type.route not in local_authority_routes:
            geography_types.append(
                {
                    "id": str(geography_type.id),
                    "name": geography_type.name,
                    "name_singular": geography_type.name_singular,
                    "route": geography_type.route,
                }
            )

    geography_types.append(
        {
            "id": str(uuid.uuid4()),
            "name": "Local Authorities",
            "name_singular": "local authority",
            "route": "local_authorities",
        }
    )

    return jsonify({"data": geography_types})


@areas_blueprint.route("/geography-types/<type_route>/examples", methods=["GET"])
def get_geography_type_examples(type_route):
    """Returns the example hint text for a geography type/library."""
    data = AreasDAO.get_geography_type_examples(type_route)
    count = data["count"]
    example_areas = data["examples"]

    # Generates examples string to be displayed on Admin
    # applications 'libraries' page
    if count <= 4:
        examples = formatted_list(example_areas, before_each="", after_each="")
    else:
        shown = example_areas[:3]
        remaining = count - 3
        examples = f"{', '.join(shown)} and {remaining} more..."

    return jsonify({"data": examples})
