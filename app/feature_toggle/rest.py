from flask import Blueprint, jsonify, request

from app.dao.feature_toggle_dao import dao_get_feature_toggle_by_name
from app.errors import InvalidRequest, register_errors

feature_toggle_blueprint = Blueprint(
    "feature_toggle",
    __name__,
    url_prefix="/feature-toggle",
)

register_errors(feature_toggle_blueprint)


@feature_toggle_blueprint.route("")
def find_feature_toggle_by_name():
    feature_toggle_name = request.args.get("feature_toggle_name")
    if not feature_toggle_name:
        errors = {"feature_toggle_name": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_feature_toggle_by_name(feature_toggle_name)
    return jsonify(data.serialize() if data else {}), 200
