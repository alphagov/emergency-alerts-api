from flask import Blueprint, jsonify, request
from app.dao.populations_dao import dao_estimate_population_for_polygon
from app.errors import register_errors

populations_blueprint = Blueprint(
    "populations",
    __name__,
    url_prefix="/populations",
)

register_errors(populations_blueprint)

@populations_blueprint.route("", methods=["POST"])
def get_population_estimate_for_area():
    # get alert area based on alert
    data = request.get_json()
    return jsonify(dao_estimate_population_for_polygon(data.get("area")))
