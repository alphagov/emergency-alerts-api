from app.dao.feature_toggle_dao import (
    dao_get_feature_toggle_by_name,
    dao_get_feature_toggles,
)
from tests.app.db import create_feature_toggle


def test_get_feature_toggles_returns_all_feature_toggles(notify_db_session):
    feature_toggle = create_feature_toggle(name="ABC", is_enabled=True)
    create_feature_toggle(name="DEF", is_enabled=False, display_html="Display HTML")
    response = dao_get_feature_toggles()
    assert len(response) == 2
    assert response[0].name == feature_toggle.name


def test_get_feature_toggle_by_name_returns_feature_toggle(notify_db_session):
    feature_toggle = create_feature_toggle(name="ABC", is_enabled=True)
    assert dao_get_feature_toggle_by_name(feature_toggle_name="ABC").name == feature_toggle.name


def test_get_feature_toggle_by_name_returns_none_if_none_found(notify_db_session):
    assert dao_get_feature_toggle_by_name(feature_toggle_name="ABC") is None
