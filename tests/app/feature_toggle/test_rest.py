from tests.app.db import create_feature_toggle


def test_find_feature_toggle_by_name_finds_feature_toggle_object(notify_db_session, admin_request, mocker):
    feature_toggle_1 = create_feature_toggle(name="ABC", is_enabled=True)
    feature_toggle_2 = create_feature_toggle(name="DEF", is_enabled=False, display_html="Display HTML")

    response = admin_request.get("feature_toggle.find_feature_toggle_by_name", feature_toggle_name="ABC")
    assert response["is_enabled"] is feature_toggle_1.is_enabled

    response = admin_request.get("feature_toggle.find_feature_toggle_by_name", feature_toggle_name="DEF")
    assert response["display_html"] == feature_toggle_2.display_html


def test_find_feature_toggle_by_name_returns_empty_if_none_found(notify_db_session, admin_request, mocker):
    create_feature_toggle(name="ABC", is_enabled=True)

    response = admin_request.get("feature_toggle.find_feature_toggle_by_name", feature_toggle_name="DEF")
    assert response is not None
    assert response == {}
