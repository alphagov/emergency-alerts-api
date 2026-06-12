from flask import Blueprint, jsonify, request
from marshmallow import ValidationError
from shapely import MultiPolygon, Polygon, wkt

from app.dao.populations_dao import dao_estimate_population_for_area
from app.errors import register_errors

populations_blueprint = Blueprint(
    "populations",
    __name__,
    url_prefix="/populations",
)

register_errors(populations_blueprint)


@populations_blueprint.route("", methods=["POST"])
def get_population_estimate_for_area():
    # get alert area population data based on area posted
    data = request.get_json()
    area = data.get("areas")
    validate_wkt_area(area)
    return jsonify(dao_estimate_population_for_area(area))


def validate_wkt_area(area):
    # Firstly check string is valid WKT
    try:
        geom = wkt.loads(area)
    except Exception:
        raise ValidationError("Invalid WKT string")

    # Checking area is either Polygon or MultiPolygon
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValidationError("Area must be a Polygon or MultiPolygon")

    # Checking area has valid shape
    if not geom.is_valid:
        raise ValidationError("Provided WKT area is not valid")
