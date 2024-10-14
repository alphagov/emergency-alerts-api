import json

from emergency_alerts_utils.clients.slack.slack_client import SlackMessage
from flask import Blueprint, current_app, jsonify, request

from app import slack_client
from app.errors import register_errors

reports_blueprint = Blueprint("reports", __name__, url_prefix="/reports")
register_errors(reports_blueprint)


@reports_blueprint.route("", methods=["POST"])
def log_report():
    data = request.get_json()
    message = SlackMessage(
        webhook_url=current_app.config["REPORTS_SLACK_WEBHOOK_URL"],
        subject="Reporting Endpoint Submission",
        message_type="info",
        markdown_sections=[
            (
                f"*Type*: {data.get('type', 'N/A')}\n\n"
                f"*URL*: {data.get('url', 'N/A')}\n\n"
                f"*User Agent*: {data.get('user_agent', 'N/A')}\n\n"
                f"*Body*: ```{json.dumps(data.get('body', {}), indent=4)}```"
            )
        ],
    )
    response = slack_client.send_message_to_slack(message)

    return jsonify(data=response), 201
