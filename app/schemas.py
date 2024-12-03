from uuid import UUID

from dateutil.parser import parse
from emergency_alerts_utils.recipients import (
    InvalidEmailError,
    InvalidPhoneError,
    validate_email_address,
    validate_phone_number,
)
from flask_marshmallow.fields import fields
from marshmallow import (
    EXCLUDE,
    ValidationError,
    post_dump,
    post_load,
    pre_dump,
    pre_load,
    validates,
    validates_schema,
)
from marshmallow_sqlalchemy import field_for

from app import ma, models
from app.dao.permissions_dao import permission_dao
from app.models import ServicePermission
from app.utils import DATETIME_FORMAT_NO_TIMEZONE


class FlexibleDateTime(fields.DateTime):
    """
    Allows input data to not contain tz info.
    Outputs data using the output format that marshmallow version 2 used to use, OLD_MARSHMALLOW_FORMAT
    """

    DEFAULT_FORMAT = "flexible"
    OLD_MARSHMALLOW_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"

    def __init__(self, *args, allow_none=True, **kwargs):
        super().__init__(*args, allow_none=allow_none, **kwargs)
        self.DESERIALIZATION_FUNCS["flexible"] = parse
        self.SERIALIZATION_FUNCS["flexible"] = lambda x: x.strftime(self.OLD_MARSHMALLOW_FORMAT)


class UUIDsAsStringsMixin:
    @post_dump()
    def __post_dump(self, data, **kwargs):
        for key, value in data.items():
            if isinstance(value, UUID):
                data[key] = str(value)

            if isinstance(value, list):
                data[key] = [(str(item) if isinstance(item, UUID) else item) for item in value]
        return data


class BaseSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        load_instance = True
        include_relationships = True
        unknown = EXCLUDE

    def __init__(self, load_json=False, *args, **kwargs):
        self.load_json = load_json
        super(BaseSchema, self).__init__(*args, **kwargs)

    @post_load
    def make_instance(self, data, **kwargs):
        """Deserialize data to an instance of the model. Update an existing row
        if specified in `self.instance` or loaded by primary key(s) in the data;
        else create a new row.
        :param data: Data to deserialize.
        """
        if self.load_json:
            return data
        return super(BaseSchema, self).make_instance(data)


class UserSchema(BaseSchema):
    permissions = fields.Method("user_permissions", dump_only=True)
    password_changed_at = field_for(models.User, "password_changed_at", format=DATETIME_FORMAT_NO_TIMEZONE)
    created_at = field_for(models.User, "created_at", format=DATETIME_FORMAT_NO_TIMEZONE)
    updated_at = FlexibleDateTime()
    logged_in_at = FlexibleDateTime()
    auth_type = field_for(models.User, "auth_type")
    password = fields.String(required=True, load_only=True)

    def user_permissions(self, usr):
        retval = {}
        for x in permission_dao.get_permissions_by_user_id(usr.id):
            service_id = str(x.service_id)
            if service_id not in retval:
                retval[service_id] = []
            retval[service_id].append(x.permission)
        return retval

    class Meta(BaseSchema.Meta):
        model = models.User
        exclude = (
            "_password",
            "created_at",
            "email_access_validated_at",
            "updated_at",
            "verify_codes",
        )

    @validates("name")
    def validate_name(self, value):
        if not value:
            raise ValidationError("Invalid name")

    @validates("email_address")
    def validate_email_address(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))

    @validates("mobile_number")
    def validate_mobile_number(self, value):
        try:
            if value is not None:
                validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            raise ValidationError("Invalid phone number: {}".format(error))


class UserUpdateAttributeSchema(BaseSchema):
    auth_type = field_for(models.User, "auth_type")
    email_access_validated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.User
        exclude = (
            "_password",
            "created_at",
            "failed_login_count",
            "id",
            "logged_in_at",
            "password_changed_at",
            "platform_admin",
            "state",
            "updated_at",
            "verify_codes",
        )

    @validates("name")
    def validate_name(self, value):
        if not value:
            raise ValidationError("Invalid name")

    @validates("email_address")
    def validate_email_address(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))

    @validates("mobile_number")
    def validate_mobile_number(self, value):
        try:
            if value is not None:
                validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            raise ValidationError("Invalid phone number: {}".format(error))

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data, **kwargs):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError("Unknown field name {}".format(key))


class UserUpdatePasswordSchema(BaseSchema):
    class Meta(BaseSchema.Meta):
        model = models.User

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data, **kwargs):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError("Unknown field name {}".format(key))


class ServiceSchema(BaseSchema, UUIDsAsStringsMixin):
    created_by = field_for(models.Service, "created_by", required=True)
    organisation_type = field_for(models.Service, "organisation_type")
    permissions = fields.Method("serialize_service_permissions", "deserialize_service_permissions")
    organisation = field_for(models.Service, "organisation")
    go_live_at = field_for(models.Service, "go_live_at", format=DATETIME_FORMAT_NO_TIMEZONE)
    allowed_broadcast_provider = fields.Method(dump_only=True, serialize="_get_allowed_broadcast_provider")
    broadcast_channel = fields.Method(dump_only=True, serialize="_get_broadcast_channel")

    def _get_allowed_broadcast_provider(self, service):
        return service.allowed_broadcast_provider

    def _get_broadcast_channel(self, service):
        return service.broadcast_channel

    def serialize_service_permissions(self, service):
        return [p.permission for p in service.permissions]

    def deserialize_service_permissions(self, in_data):
        if isinstance(in_data, dict) and "permissions" in in_data:
            str_permissions = in_data["permissions"]
            permissions = []
            for p in str_permissions:
                permission = ServicePermission(service_id=in_data["id"], permission=p)
                permissions.append(permission)

            in_data["permissions"] = permissions

        return in_data

    class Meta(BaseSchema.Meta):
        model = models.Service
        exclude = (
            "all_template_folders",
            "api_keys",
            "broadcast_messages",
            "crown",
            "service_broadcast_provider_restriction",
            "service_broadcast_settings",
            "templates",
            "updated_at",
            "users",
            "version",
        )

    @validates("permissions")
    def validate_permissions(self, value):
        permissions = [v.permission for v in value]
        for p in permissions:
            if p not in models.SERVICE_PERMISSION_TYPES:
                raise ValidationError("Invalid Service Permission: '{}'".format(p))

        if len(set(permissions)) != len(permissions):
            duplicates = list(set([x for x in permissions if permissions.count(x) > 1]))
            raise ValidationError("Duplicate Service Permission: {}".format(duplicates))

    @pre_load()
    def format_for_data_model(self, in_data, **kwargs):
        if isinstance(in_data, dict) and "permissions" in in_data:
            str_permissions = in_data["permissions"]
            permissions = []
            for p in str_permissions:
                permission = ServicePermission(service_id=in_data["id"], permission=p)
                permissions.append(permission)

            in_data["permissions"] = permissions

        return in_data


class DetailedServiceSchema(BaseSchema):
    statistics = fields.Dict()
    organisation_type = field_for(models.Service, "organisation_type")
    go_live_at = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.Service
        exclude = (
            "all_template_folders",
            "api_keys",
            "broadcast_messages",
            "created_by",
            "crown",
            "inbound_api",
            "permissions",
            "templates",
            "users",
            "version",
        )


class BaseTemplateSchema(BaseSchema):
    class Meta(BaseSchema.Meta):
        model = models.Template
        exclude = ("service_id",)


class TemplateSchema(BaseTemplateSchema, UUIDsAsStringsMixin):
    created_by = field_for(models.Template, "created_by", required=True)
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    @validates_schema
    def validate_type(self, data, **kwargs):
        pass


class TemplateSchemaNested(TemplateSchema):
    """
    Contains extra 'is_precompiled_letter' field for use with NotificationWithTemplateSchema
    """

    is_precompiled_letter = fields.Method("get_is_precompiled_letter")

    def get_is_precompiled_letter(self, template):
        return template.is_precompiled_letter


class TemplateSchemaNoDetail(TemplateSchema):
    class Meta(TemplateSchema.Meta):
        exclude = TemplateSchema.Meta.exclude + (
            "archived",
            "broadcast_data",
            "created_at",
            "created_by",
            "created_by_id",
            "service",
            "updated_at",
            "version",
        )

    @pre_dump
    def remove_content_for_non_broadcast_templates(self, template, **kwargs):
        if template.template_type != models.BROADCAST_TYPE:
            template.content = None

        return template


class TemplateHistorySchema(BaseSchema):
    created_by = fields.Nested(UserSchema, only=["id", "name", "email_address"], dump_only=True)
    created_at = field_for(models.Template, "created_at", format=DATETIME_FORMAT_NO_TIMEZONE)
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.TemplateHistory
        exclude = ("broadcast_messages",)


class ApiKeySchema(BaseSchema):
    created_by = field_for(models.ApiKey, "created_by", required=True)
    key_type = field_for(models.ApiKey, "key_type", required=True)
    expiry_date = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.ApiKey
        exclude = ("service", "_secret")


class InvitedUserSchema(BaseSchema):
    auth_type = field_for(models.InvitedUser, "auth_type")
    created_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.InvitedUser

    @validates("email_address")
    def validate_to(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))


class EmailDataSchema(ma.Schema):
    class Meta:
        unknown = EXCLUDE

    email = fields.Str(required=True)
    next = fields.Str(required=False)
    admin_base_url = fields.Str(required=False)

    def __init__(self, partial_email=False):
        super().__init__()
        self.partial_email = partial_email

    @validates("email")
    def validate_email(self, value):
        if self.partial_email:
            return
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))


class ServiceHistorySchema(ma.Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.UUID()
    name = fields.String()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    active = fields.Boolean()
    restricted = fields.Boolean()
    created_by_id = fields.UUID()
    version = fields.Integer()


class ApiKeyHistorySchema(ma.Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.UUID()
    name = fields.String()
    service_id = fields.UUID()
    expiry_date = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    created_by_id = fields.UUID()


class EventSchema(BaseSchema):
    created_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.Event


class UnarchivedTemplateSchema(BaseSchema):
    archived = fields.Boolean(required=True)

    @validates_schema
    def validate_archived(self, data, **kwargs):
        if data["archived"]:
            raise ValidationError("Template has been deleted", "template")


# should not be used on its own for dumping - only for loading
create_user_schema = UserSchema()
user_update_schema_load_json = UserUpdateAttributeSchema(load_json=True, partial=True)
user_update_password_schema_load_json = UserUpdatePasswordSchema(only=("_password",), load_json=True, partial=True)
service_schema = ServiceSchema()
detailed_service_schema = DetailedServiceSchema()
template_schema = TemplateSchema()
template_schema_no_detail = TemplateSchemaNoDetail()
api_key_schema = ApiKeySchema()
invited_user_schema = InvitedUserSchema()
email_data_request_schema = EmailDataSchema()
partial_email_data_request_schema = EmailDataSchema(partial_email=True)
service_history_schema = ServiceHistorySchema()
api_key_history_schema = ApiKeyHistorySchema()
template_history_schema = TemplateHistorySchema()
event_schema = EventSchema()
unarchived_template_schema = UnarchivedTemplateSchema()
