def test_create_report(admin_request, mocker):
    data = {
        "type": "some-violation",
        "url": "https://gov.uk",
        "user_agent": "some-browser",
        "body": {"something": "random", "could_be": "anything"},
    }

    mock_log_report = mocker.patch(
        "app.reports.rest.slack_client.send_message_to_slack",
        autospec=True,
        return_value={"message": "Slack message sent to the provided webhook URL."},
    )

    admin_request.post("reports.log_report", _data=data, _expected_status=201)

    mock_log_report.assert_called_once()
