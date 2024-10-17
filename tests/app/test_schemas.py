import pytest
from marshmallow import ValidationError


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [("name", "New User"), ("email_address", "newuser@mail.com"), ("mobile_number", "+4407700900460")],
)
def test_user_update_schema_accepts_valid_attribute_pairs(user_attribute, user_value):
    update_dict = {user_attribute: user_value}
    from app.schemas import user_update_schema_load_json

    errors = user_update_schema_load_json.validate(update_dict)
    assert not errors


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [("name", None), ("name", ""), ("email_address", "bademail@...com"), ("mobile_number", "+44077009")],
)
def test_user_update_schema_rejects_invalid_attribute_pairs(user_attribute, user_value):
    from app.schemas import user_update_schema_load_json

    update_dict = {user_attribute: user_value}

    with pytest.raises(ValidationError):
        user_update_schema_load_json.load(update_dict)


@pytest.mark.parametrize(
    "user_attribute",
    [
        "id",
        "updated_at",
        "created_at",
        "user_to_service",
        "_password",
        "verify_codes",
        "logged_in_at",
        "password_changed_at",
        "failed_login_count",
        "state",
        "platform_admin",
    ],
)
def test_user_update_schema_rejects_disallowed_attribute_keys(user_attribute):
    update_dict = {user_attribute: "not important"}
    from app.schemas import user_update_schema_load_json

    with pytest.raises(ValidationError) as excinfo:
        user_update_schema_load_json.load(update_dict)

    assert excinfo.value.messages["_schema"][0] == "Unknown field name {}".format(user_attribute)
