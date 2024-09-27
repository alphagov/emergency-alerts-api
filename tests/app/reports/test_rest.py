from emergency_alerts_utils.clients.slack.slack_client import SlackMessage


def test_create_report(admin_request, mocker):
    data = {
        "type": "some-violation",
        "url": "https://gov.uk",
        "user_agent": "some-browser",
        "body": {"something": "random", "could_be": "anything"},
    }

    mock_send_message_to_slack = mocker.patch(
        "app.slack_client.send_message_to_slack",
        autospec=True,
    )

    slack_message = SlackMessage(
        webhook_url="",
        subject="Reporting Endpoint Submission",
        message_type="info",
        markdown_sections=[
            (
                "*Type*: some-violation\n\n"
                "*URL*: https://gov.uk\n\n"
                "*User Agent*: some-browser\n\n"
                '*Body*: ```{"something":"random","could_be":"anything"}```'
            )
        ],
    )
    admin_request.post("reports.log_report", _data=data)
    mock_send_message_to_slack.assert_called_once_with(slack_message)
