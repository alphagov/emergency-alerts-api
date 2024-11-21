import datetime
import uuid

from emergency_alerts_utils.template import BroadcastMessageTemplate
from flask import current_app, url_for
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, JSON, JSONB, UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.schema import Sequence

from app import db, encryption
from app.hashing import check_hash, hashpw
from app.history_meta import Versioned
from app.utils import (
    DATETIME_FORMAT,
    DATETIME_FORMAT_NO_TIMEZONE,
    get_dt_string_or_none,
    get_interval_seconds_or_none,
    get_uuid_string_or_none,
)

BROADCAST_TYPE = "broadcast"
PLACEHOLDER_TYPE = "placeholder"  # dummy "permission" for testing

TEMPLATE_TYPES = [BROADCAST_TYPE]

template_types = db.Enum(*TEMPLATE_TYPES, name="template_type")

SMS_AUTH_TYPE = "sms_auth"
EMAIL_AUTH_TYPE = "email_auth"
WEBAUTHN_AUTH_TYPE = "webauthn_auth"
USER_AUTH_TYPES = [SMS_AUTH_TYPE, EMAIL_AUTH_TYPE, WEBAUTHN_AUTH_TYPE]

DELIVERY_STATUS_CALLBACK_TYPE = "delivery_status"
SERVICE_CALLBACK_TYPES = [DELIVERY_STATUS_CALLBACK_TYPE]


def filter_null_value_fields(obj):
    return dict(filter(lambda x: x[1] is not None, obj.items()))


class HistoryModel:
    @classmethod
    def from_original(cls, original):
        history = cls()
        history.update_from_original(original)
        return history

    def update_from_original(self, original):
        for c in self.__table__.columns:
            # in some cases, columns may have different names to their underlying db column -  so only copy those
            # that we can, and leave it up to subclasses to deal with any oddities/properties etc.
            if hasattr(original, c.name):
                setattr(self, c.name, getattr(original, c.name))
            else:
                current_app.logger.debug("{} has no column {} to copy from".format(original, c.name))


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False, index=True, unique=False)
    email_address = db.Column(db.String(255), nullable=False, index=True, unique=True)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    _password = db.Column(db.String, index=False, unique=False, nullable=False)
    mobile_number = db.Column(db.String, index=False, unique=False, nullable=True)
    password_changed_at = db.Column(
        db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow
    )
    logged_in_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    state = db.Column(db.String, nullable=False, default="pending")
    platform_admin = db.Column(db.Boolean, nullable=False, default=False)
    current_session_id = db.Column(UUID(as_uuid=True), nullable=True)
    auth_type = db.Column(db.String, db.ForeignKey("auth_type.name"), index=True, nullable=False, default=SMS_AUTH_TYPE)
    email_access_validated_at = db.Column(
        db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow
    )

    # either email auth or a mobile number must be provided
    CheckConstraint("auth_type in ('email_auth', 'webauthn_auth') or mobile_number is not null")

    services = db.relationship("Service", secondary="user_to_service", backref="users")
    organisations = db.relationship("Organisation", secondary="user_to_organisation", backref="users")

    @property
    def password(self):
        raise AttributeError("Password not readable")

    @property
    def can_use_webauthn(self):
        if self.platform_admin:
            return True

        if self.auth_type == "webauthn_auth":
            return True

        return any(
            str(service.organisation_id) == current_app.config["BROADCAST_ORGANISATION_ID"]
            or str(service.id) == current_app.config["NOTIFY_SERVICE_ID"]
            for service in self.services
        )

    @password.setter
    def password(self, password):
        self._password = hashpw(password)

    def check_password(self, password):
        return check_hash(password, self._password)

    def get_permissions(self, service_id=None):
        from app.dao.permissions_dao import permission_dao

        if service_id:
            return [x.permission for x in permission_dao.get_permissions_by_user_id_and_service_id(self.id, service_id)]

        retval = {}
        for x in permission_dao.get_permissions_by_user_id(self.id):
            service_id = str(x.service_id)
            if service_id not in retval:
                retval[service_id] = []
            retval[service_id].append(x.permission)
        return retval

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "email_address": self.email_address,
            "auth_type": self.auth_type,
            "current_session_id": self.current_session_id,
            "failed_login_count": self.failed_login_count,
            "email_access_validated_at": self.email_access_validated_at.strftime(DATETIME_FORMAT),
            "logged_in_at": get_dt_string_or_none(self.logged_in_at),
            "mobile_number": self.mobile_number,
            "organisations": [x.id for x in self.organisations if x.active],
            "password_changed_at": self.password_changed_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
            "permissions": self.get_permissions(),
            "platform_admin": self.platform_admin,
            "services": [x.id for x in self.services if x.active],
            "can_use_webauthn": self.can_use_webauthn,
            "state": self.state,
        }

    def serialize_for_users_list(self):
        return {
            "id": self.id,
            "name": self.name,
            "email_address": self.email_address,
            "mobile_number": self.mobile_number,
        }


class ServiceUser(db.Model):
    __tablename__ = "user_to_service"
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), primary_key=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), primary_key=True)

    __table_args__ = (UniqueConstraint("user_id", "service_id", name="uix_user_to_service"),)


user_to_organisation = db.Table(
    "user_to_organisation",
    db.Model.metadata,
    db.Column("user_id", UUID(as_uuid=True), db.ForeignKey("users.id")),
    db.Column("organisation_id", UUID(as_uuid=True), db.ForeignKey("organisation.id")),
    UniqueConstraint("user_id", "organisation_id", name="uix_user_to_organisation"),
)


user_folder_permissions = db.Table(
    "user_folder_permissions",
    db.Model.metadata,
    db.Column("user_id", UUID(as_uuid=True), primary_key=True),
    db.Column("template_folder_id", UUID(as_uuid=True), db.ForeignKey("template_folder.id"), primary_key=True),
    db.Column("service_id", UUID(as_uuid=True), primary_key=True),
    db.ForeignKeyConstraint(["user_id", "service_id"], ["user_to_service.user_id", "user_to_service.service_id"]),
    db.ForeignKeyConstraint(["template_folder_id", "service_id"], ["template_folder.id", "template_folder.service_id"]),
)


EMAIL_AUTH = "email_auth"
EDIT_FOLDER_PERMISSIONS = "edit_folder_permissions"

SERVICE_PERMISSION_TYPES = [
    BROADCAST_TYPE,
    EMAIL_AUTH,
    EDIT_FOLDER_PERMISSIONS,
]


class ServicePermissionTypes(db.Model):
    __tablename__ = "service_permission_types"

    name = db.Column(db.String(255), primary_key=True)


class Domain(db.Model):
    __tablename__ = "domain"
    domain = db.Column(db.String(255), primary_key=True)
    organisation_id = db.Column("organisation_id", UUID(as_uuid=True), db.ForeignKey("organisation.id"), nullable=False)


ORGANISATION_TYPES = [
    "central",
    "local",
    "nhs_central",
    "nhs_local",
    "nhs_gp",
    "emergency_service",
    "school_or_college",
    "other",
]

CROWN_ORGANISATION_TYPES = ["nhs_central"]
NON_CROWN_ORGANISATION_TYPES = ["local", "nhs_local", "nhs_gp", "emergency_service", "school_or_college"]
NHS_ORGANISATION_TYPES = ["nhs_central", "nhs_local", "nhs_gp"]


class OrganisationTypes(db.Model):
    __tablename__ = "organisation_types"

    name = db.Column(db.String(255), primary_key=True)
    is_crown = db.Column(db.Boolean, nullable=True)
    annual_free_sms_fragment_limit = db.Column(db.BigInteger, nullable=False)


class Organisation(db.Model):
    __tablename__ = "organisation"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=False)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    agreement_signed = db.Column(db.Boolean, nullable=True)
    agreement_signed_at = db.Column(db.DateTime, nullable=True)
    agreement_signed_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        nullable=True,
    )
    agreement_signed_by = db.relationship("User")
    agreement_signed_on_behalf_of_name = db.Column(db.String(255), nullable=True)
    agreement_signed_on_behalf_of_email_address = db.Column(db.String(255), nullable=True)
    agreement_signed_version = db.Column(db.Float, nullable=True)
    crown = db.Column(db.Boolean, nullable=True)
    organisation_type = db.Column(
        db.String(255),
        db.ForeignKey("organisation_types.name"),
        unique=False,
        nullable=True,
    )
    request_to_go_live_notes = db.Column(db.Text)

    domains = db.relationship(
        "Domain",
    )

    notes = db.Column(db.Text, nullable=True)

    @property
    def live_services(self):
        return [service for service in self.services if service.active and not service.restricted]

    @property
    def domain_list(self):
        return [domain.domain for domain in self.domains]

    def serialize(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "active": self.active,
            "crown": self.crown,
            "organisation_type": self.organisation_type,
            "agreement_signed": self.agreement_signed,
            "agreement_signed_at": self.agreement_signed_at,
            "agreement_signed_by_id": self.agreement_signed_by_id,
            "agreement_signed_on_behalf_of_name": self.agreement_signed_on_behalf_of_name,
            "agreement_signed_on_behalf_of_email_address": self.agreement_signed_on_behalf_of_email_address,
            "agreement_signed_version": self.agreement_signed_version,
            "domains": self.domain_list,
            "request_to_go_live_notes": self.request_to_go_live_notes,
            "count_of_live_services": len(self.live_services),
            "notes": self.notes,
        }

    def serialize_for_list(self):
        return {
            "name": self.name,
            "id": str(self.id),
            "active": self.active,
            "count_of_live_services": len(self.live_services),
            "domains": self.domain_list,
            "organisation_type": self.organisation_type,
        }


class Service(db.Model, Versioned):
    __tablename__ = "services"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=True)
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    organisation_type = db.Column(
        db.String(255),
        db.ForeignKey("organisation_types.name"),
        unique=False,
        nullable=True,
    )
    crown = db.Column(db.Boolean, index=False, nullable=True)
    go_live_user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    go_live_user = db.relationship("User", foreign_keys=[go_live_user_id])
    go_live_at = db.Column(db.DateTime, nullable=True)

    organisation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organisation.id"), index=True, nullable=True)
    organisation = db.relationship("Organisation", backref="services")

    notes = db.Column(db.Text, nullable=True)

    allowed_broadcast_provider = association_proxy("service_broadcast_settings", "provider")
    broadcast_channel = association_proxy("service_broadcast_settings", "channel")

    @classmethod
    def from_json(cls, data):
        """
        Assumption: data has been validated appropriately.

        Returns a Service object based on the provided data. Deserialises created_by to created_by_id as marshmallow
        would.
        """
        # validate json with marshmallow
        fields = data.copy()

        fields["created_by_id"] = fields.pop("created_by")

        return cls(**fields)

    def has_permission(self, permission):
        return permission in [p.permission for p in self.permissions]

    def serialize_for_org_dashboard(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "active": self.active,
            "restricted": self.restricted,
        }

    def get_available_broadcast_providers(self):
        # There may be future checks here if we add, for example, platform admin level provider killswitches.
        if self.allowed_broadcast_provider != ALL_BROADCAST_PROVIDERS:
            return [x for x in current_app.config["ENABLED_CBCS"] if x == self.allowed_broadcast_provider]
        else:
            return current_app.config["ENABLED_CBCS"]


class ServicePermission(db.Model):
    __tablename__ = "service_permissions"

    service_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("services.id"), primary_key=True, index=True, nullable=False
    )
    permission = db.Column(
        db.String(255), db.ForeignKey("service_permission_types.name"), index=True, primary_key=True, nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    service_permission_types = db.relationship(Service, backref=db.backref("permissions", cascade="all, delete-orphan"))

    def __repr__(self):
        return "<{} has service permission: {}>".format(self.service_id, self.permission)


MOBILE_TYPE = "mobile"
EMAIL_TYPE = "email"
SMS_TYPE = "sms"


class ServiceInboundApi(db.Model, Versioned):
    __tablename__ = "service_inbound_api"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, nullable=False, unique=True)
    service = db.relationship("Service", backref="inbound_api")
    url = db.Column(db.String(), nullable=False)
    _bearer_token = db.Column("bearer_token", db.String(), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.relationship("User")
    updated_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)

    @property
    def bearer_token(self):
        if self._bearer_token:
            return encryption.decrypt(self._bearer_token)
        return None

    @bearer_token.setter
    def bearer_token(self, bearer_token):
        if bearer_token:
            self._bearer_token = encryption.encrypt(str(bearer_token))

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "url": self.url,
            "updated_by_id": str(self.updated_by_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ServiceCallbackApi(db.Model, Versioned):
    __tablename__ = "service_callback_api"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, nullable=False)
    service = db.relationship("Service", backref="service_callback_api")
    url = db.Column(db.String(), nullable=False)
    callback_type = db.Column(db.String(), db.ForeignKey("service_callback_type.name"), nullable=True)
    _bearer_token = db.Column("bearer_token", db.String(), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.relationship("User")
    updated_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)

    __table_args__ = (UniqueConstraint("service_id", "callback_type", name="uix_service_callback_type"),)

    @property
    def bearer_token(self):
        if self._bearer_token:
            return encryption.decrypt(self._bearer_token)
        return None

    @bearer_token.setter
    def bearer_token(self, bearer_token):
        if bearer_token:
            self._bearer_token = encryption.encrypt(str(bearer_token))

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "url": self.url,
            "updated_by_id": str(self.updated_by_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ServiceCallbackType(db.Model):
    __tablename__ = "service_callback_type"

    name = db.Column(db.String, primary_key=True)


class ApiKey(db.Model, Versioned):
    __tablename__ = "api_keys"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    _secret = db.Column("secret", db.String(255), unique=True, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, nullable=False)
    service = db.relationship("Service", backref="api_keys")
    key_type = db.Column(db.String(255), db.ForeignKey("key_types.name"), index=True, nullable=False)
    expiry_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    created_by = db.relationship("User")
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)

    __table_args__ = (
        Index("uix_service_to_key_name", "service_id", "name", unique=True, postgresql_where=expiry_date.is_(None)),
    )

    @property
    def secret(self):
        if self._secret:
            return encryption.decrypt(self._secret)
        return None

    @secret.setter
    def secret(self, secret):
        if secret:
            self._secret = encryption.encrypt(str(secret))


KEY_TYPE_NORMAL = "normal"
KEY_TYPE_TEAM = "team"
KEY_TYPE_TEST = "test"


class KeyTypes(db.Model):
    __tablename__ = "key_types"

    name = db.Column(db.String(255), primary_key=True)


class TemplateFolder(db.Model):
    __tablename__ = "template_folder"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    parent_id = db.Column(UUID(as_uuid=True), db.ForeignKey("template_folder.id"), nullable=True)

    service = db.relationship("Service", backref="all_template_folders")
    parent = db.relationship("TemplateFolder", remote_side=[id], backref="subfolders")
    users = db.relationship(
        "ServiceUser",
        uselist=True,
        backref=db.backref("folders", foreign_keys="user_folder_permissions.c.template_folder_id"),
        secondary="user_folder_permissions",
        primaryjoin="TemplateFolder.id == user_folder_permissions.c.template_folder_id",
    )

    __table_args__ = (UniqueConstraint("id", "service_id", name="ix_id_service_id"), {})

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "service_id": self.service_id,
            "users_with_permission": self.get_users_with_permission(),
        }

    def is_parent_of(self, other):
        while other.parent is not None:
            if other.parent == self:
                return True
            other = other.parent
        return False

    def get_users_with_permission(self):
        service_users = self.users
        users_with_permission = [str(service_user.user_id) for service_user in service_users]

        return users_with_permission


template_folder_map = db.Table(
    "template_folder_map",
    db.Model.metadata,
    # template_id is a primary key as a template can only belong in one folder
    db.Column("template_id", UUID(as_uuid=True), db.ForeignKey("templates.id"), primary_key=True, nullable=False),
    db.Column("template_folder_id", UUID(as_uuid=True), db.ForeignKey("template_folder.id"), nullable=False),
)


PRECOMPILED_TEMPLATE_NAME = "Pre-compiled PDF"


class TemplateBase(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        if "template_type" in kwargs:
            self.template_type = kwargs.pop("template_type")

        super().__init__(**kwargs)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(template_types, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    subject = db.Column(db.Text)
    postage = db.Column(db.String, nullable=True)
    broadcast_data = db.Column(JSONB(none_as_null=True), nullable=True)

    @declared_attr
    def service_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, nullable=False)

    @declared_attr
    def created_by_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)

    @declared_attr
    def created_by(cls):
        return db.relationship("User")

    def _as_utils_template(self):
        if self.template_type == BROADCAST_TYPE:
            return BroadcastMessageTemplate(self.__dict__)

    def serialize_for_v2(self):
        serialized = {
            "id": str(self.id),
            "type": self.template_type,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
            "created_by": self.created_by.email_address,
            "version": self.version,
            "body": self.content,
            "name": self.name,
        }

        return serialized


class Template(TemplateBase):
    __tablename__ = "templates"

    service = db.relationship("Service", backref="templates")
    version = db.Column(db.Integer, default=0, nullable=False)

    folder = db.relationship(
        "TemplateFolder",
        secondary=template_folder_map,
        uselist=False,
        # eagerly load the folder whenever the template object is fetched
        lazy="joined",
        backref=db.backref("templates"),
    )

    def get_link(self):
        # TODO: use "/v2/" route once available
        return url_for(
            "template.get_template_by_id_and_service_id",
            service_id=self.service_id,
            template_id=self.id,
            _external=True,
        )

    @classmethod
    def from_json(cls, data, folder):
        """
        Assumption: data has been validated appropriately.
        Returns a Template object based on the provided data.
        """
        fields = data.copy()

        fields["created_by_id"] = fields.pop("created_by")
        fields["service_id"] = fields.pop("service")
        fields["folder"] = folder
        return cls(**fields)


class TemplateHistory(TemplateBase):
    __tablename__ = "templates_history"

    service = db.relationship("Service")
    version = db.Column(db.Integer, primary_key=True, nullable=False)

    def get_link(self):
        return url_for("v2_template.get_template_by_id", template_id=self.id, version=self.version, _external=True)


VERIFY_CODE_TYPES = [EMAIL_TYPE, SMS_TYPE]


class VerifyCode(db.Model):
    __tablename__ = "verify_codes"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)
    user = db.relationship("User", backref=db.backref("verify_codes", lazy="dynamic"))
    _code = db.Column(db.String, nullable=False)
    code_type = db.Column(
        db.Enum(*VERIFY_CODE_TYPES, name="verify_code_types"), index=False, unique=False, nullable=False
    )
    expiry_datetime = db.Column(db.DateTime, nullable=False)
    code_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)

    @property
    def code(self):
        return self._code

    @code.setter
    def code(self, cde):
        self._code = cde

    def check_code(self, cde):
        return cde == self._code


INVITE_PENDING = "pending"
INVITE_ACCEPTED = "accepted"
INVITE_CANCELLED = "cancelled"
INVITED_USER_STATUS_TYPES = [INVITE_PENDING, INVITE_ACCEPTED, INVITE_CANCELLED]


class InviteStatusType(db.Model):
    __tablename__ = "invite_status_type"

    name = db.Column(db.String, primary_key=True)


class InvitedUser(db.Model):
    __tablename__ = "invited_users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)
    from_user = db.relationship("User")
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, unique=False)
    service = db.relationship("Service")
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    status = db.Column(
        db.Enum(*INVITED_USER_STATUS_TYPES, name="invited_users_status_types"), nullable=False, default=INVITE_PENDING
    )
    permissions = db.Column(db.String, nullable=False)
    auth_type = db.Column(db.String, db.ForeignKey("auth_type.name"), index=True, nullable=False, default=SMS_AUTH_TYPE)
    folder_permissions = db.Column(JSONB(none_as_null=True), nullable=False, default=[])

    # would like to have used properties for this but haven't found a way to make them
    # play nice with marshmallow yet
    def get_permissions(self):
        return self.permissions.split(",")

    def serialize(self):
        return {
            "id": str(self.id),
            "email_address": self.email_address,
            "user_id": str(self.user_id),
            "service_id": str(self.service_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "status": self.status,
            "auth_type": self.auth_type,
        }


class InvitedOrganisationUser(db.Model):
    __tablename__ = "invited_organisation_users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    invited_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    invited_by = db.relationship("User")
    organisation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organisation.id"), nullable=False)
    organisation = db.relationship("Organisation")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

    status = db.Column(db.String, db.ForeignKey("invite_status_type.name"), nullable=False, default=INVITE_PENDING)

    def serialize(self):
        return {
            "id": str(self.id),
            "email_address": self.email_address,
            "invited_by": str(self.invited_by_id),
            "organisation": str(self.organisation_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "status": self.status,
        }


# Service Permissions
MANAGE_USERS = "manage_users"
MANAGE_TEMPLATES = "manage_templates"
MANAGE_SETTINGS = "manage_settings"
MANAGE_API_KEYS = "manage_api_keys"
PLATFORM_ADMIN = "platform_admin"
VIEW_ACTIVITY = "view_activity"
CREATE_BROADCASTS = "create_broadcasts"
APPROVE_BROADCASTS = "approve_broadcasts"
CANCEL_BROADCASTS = "cancel_broadcasts"
REJECT_BROADCASTS = "reject_broadcasts"

# List of permissions
PERMISSION_LIST = [
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    MANAGE_API_KEYS,
    PLATFORM_ADMIN,
    VIEW_ACTIVITY,
    CREATE_BROADCASTS,
    APPROVE_BROADCASTS,
    CANCEL_BROADCASTS,
    REJECT_BROADCASTS,
]


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Service id is optional, if the service is omitted we will assume the permission is not service specific.
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, unique=False, nullable=True)
    service = db.relationship("Service")
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False)
    user = db.relationship("User")
    permission = db.Column(
        db.Enum(*PERMISSION_LIST, name="permission_types"), index=False, unique=False, nullable=False
    )
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint("service_id", "user_id", "permission", name="uix_service_user_permission"),)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    data = db.Column(JSON, nullable=False)


class AuthType(db.Model):
    __tablename__ = "auth_type"

    name = db.Column(db.String, primary_key=True)


class BroadcastStatusType(db.Model):
    __tablename__ = "broadcast_status_type"
    DRAFT = "draft"
    PENDING_APPROVAL = "pending-approval"
    REJECTED = "rejected"
    BROADCASTING = "broadcasting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TECHNICAL_FAILURE = "technical-failure"

    STATUSES = [DRAFT, PENDING_APPROVAL, REJECTED, BROADCASTING, COMPLETED, CANCELLED, TECHNICAL_FAILURE]

    # a broadcast message can be edited while in one of these states
    PRE_BROADCAST_STATUSES = [DRAFT, PENDING_APPROVAL, REJECTED]
    LIVE_STATUSES = [BROADCASTING, COMPLETED, CANCELLED]

    # these are only the transitions we expect to administer via the API code.
    ALLOWED_STATUS_TRANSITIONS = {
        DRAFT: {PENDING_APPROVAL},
        PENDING_APPROVAL: {REJECTED, DRAFT, BROADCASTING},
        REJECTED: {DRAFT, PENDING_APPROVAL},
        BROADCASTING: {COMPLETED, CANCELLED},
        COMPLETED: {},
        CANCELLED: {},
        TECHNICAL_FAILURE: {},
    }

    name = db.Column(db.String, primary_key=True)


class BroadcastMessage(db.Model):
    """
    This is for creating a message, viewing it in notify, adding areas, approvals, drafts, etc. Notify logic before
    hitting send.
    """

    __tablename__ = "broadcast_message"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["templates_history.id", "templates_history.version"],
        ),
        {},
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"))
    service = db.relationship("Service", backref="broadcast_messages")

    template_id = db.Column(UUID(as_uuid=True), nullable=True)
    template_version = db.Column(db.Integer, nullable=True)
    template = db.relationship("TemplateHistory", backref="broadcast_messages")

    _personalisation = db.Column(db.String, nullable=True)
    content = db.Column(db.String, nullable=False)
    # defaults to empty list
    areas = db.Column(JSONB(none_as_null=True), nullable=False, default=list)

    status = db.Column(
        db.String, db.ForeignKey("broadcast_status_type.name"), nullable=False, default=BroadcastStatusType.DRAFT
    )

    duration = db.Column(db.Interval, nullable=True)  # isn't updated if user cancels

    # these times are related to the actual broadcast, rather than auditing purposes
    starts_at = db.Column(db.DateTime, nullable=True)
    finishes_at = db.Column(db.DateTime, nullable=True)  # also isn't updated if user cancels

    # these times correspond to when
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    approved_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    cancelled_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])

    created_by_api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey("api_keys.id"), nullable=True)
    cancelled_by_api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey("api_keys.id"), nullable=True)
    created_by_api_key = db.relationship("ApiKey", foreign_keys=[created_by_api_key_id])
    cancelled_by_api_key = db.relationship("ApiKey", foreign_keys=[cancelled_by_api_key_id])

    reference = db.Column(db.String(255), nullable=True)
    cap_event = db.Column(db.String(255), nullable=True)

    stubbed = db.Column(db.Boolean, nullable=False)

    CheckConstraint("created_by_id is not null or created_by_api_key_id is not null")

    @property
    def personalisation(self):
        if self._personalisation:
            return encryption.decrypt(self._personalisation)
        return {}

    @personalisation.setter
    def personalisation(self, personalisation):
        self._personalisation = encryption.encrypt(personalisation or {})

    def serialize(self):
        return {
            "id": str(self.id),
            "reference": self.reference,
            "cap_event": self.cap_event,
            "service_id": str(self.service_id),
            "template_id": str(self.template_id) if self.template else None,
            "template_version": self.template_version,
            "template_name": self.template.name if self.template else None,
            "personalisation": self.personalisation if self.template else None,
            "content": self.content,
            "areas": self.areas,
            "status": self.status,
            "duration": get_interval_seconds_or_none(self.duration),
            "starts_at": get_dt_string_or_none(self.starts_at),
            "finishes_at": get_dt_string_or_none(self.finishes_at),
            "created_at": get_dt_string_or_none(self.created_at),
            "approved_at": get_dt_string_or_none(self.approved_at),
            "cancelled_at": get_dt_string_or_none(self.cancelled_at),
            "updated_at": get_dt_string_or_none(self.updated_at),
            "created_by_id": get_uuid_string_or_none(self.created_by_id),
            "approved_by_id": get_uuid_string_or_none(self.approved_by_id),
            "cancelled_by_id": get_uuid_string_or_none(self.cancelled_by_id),
        }


class BroadcastEventMessageType:
    ALERT = "alert"
    UPDATE = "update"
    CANCEL = "cancel"

    MESSAGE_TYPES = [ALERT, UPDATE, CANCEL]


class BroadcastEvent(db.Model):
    """
    This table represents an instruction that we will send to the broadcast providers. It directly correlates with an
    instruction from the admin - to broadcast a message, to cancel an existing message, or to update an existing one.

    We should be able to create the complete CAP message without joining from this to any other tables, eg
    template, service, or broadcast_message.

    The only exception to this is that we will have to join to itself to find other broadcast_events with the
    same broadcast_message_id when building up the `<references>` xml field for updating/cancelling an existing message.

    As such, this shouldn't have foreign keys to things that can change or be deleted.
    """

    __tablename__ = "broadcast_event"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"))
    service = db.relationship("Service")

    broadcast_message_id = db.Column(UUID(as_uuid=True), db.ForeignKey("broadcast_message.id"), nullable=False)
    broadcast_message = db.relationship("BroadcastMessage", backref="events")

    # this is used for <sent> in the cap xml
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

    # msgType. alert, cancel, or update. (other options in the spec are "ack" and "error")
    message_type = db.Column(db.String, nullable=False)

    # this will be json containing anything that isnt hardcoded in utils/cbc proxy. for now just body but may grow to
    # include, eg, title, headline, instructions.
    transmitted_content = db.Column(JSONB(none_as_null=True), nullable=True)
    # unsubstantiated reckon: even if we're sending a cancel, we'll still need to provide areas
    transmitted_areas = db.Column(JSONB(none_as_null=True), nullable=False, default=list)
    transmitted_sender = db.Column(db.String(), nullable=False)

    # we may only need this starts_at if this is scheduled for the future. Interested to see how this affects
    # updates/cancels (ie: can you schedule an update for the future?)
    transmitted_starts_at = db.Column(db.DateTime, nullable=True)
    transmitted_finishes_at = db.Column(db.DateTime, nullable=True)

    @property
    def reference(self):
        notify_email_domain = current_app.config["NOTIFY_EMAIL_DOMAIN"]
        return f"https://www.{notify_email_domain}/," f"{self.id}," f"{self.sent_at_as_cap_datetime_string}"

    @property
    def sent_at_as_cap_datetime_string(self):
        return self.formatted_datetime_for("sent_at")

    @property
    def transmitted_finishes_at_as_cap_datetime_string(self):
        return self.formatted_datetime_for("transmitted_finishes_at")

    def formatted_datetime_for(self, property_name):
        return self.convert_naive_utc_datetime_to_cap_standard_string(getattr(self, property_name))

    @staticmethod
    def convert_naive_utc_datetime_to_cap_standard_string(dt):
        """
        As defined in section 3.3.2 of
        http://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html
        They define the standard "YYYY-MM-DDThh:mm:ssXzh:zm", where X is
        `+` if the timezone is > UTC, otherwise `-`
        """
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}-00:00"

    def get_provider_message(self, provider):
        return next(
            (provider_message for provider_message in self.provider_messages if provider_message.provider == provider),
            None,
        )

    def get_earlier_provider_messages(self, provider):
        """
        Get the previous message for a provider. These are different per provider, as the identifiers are different.
        Return the full provider_message object rather than just an identifier, since the different providers expect
        reference to contain different things - let the cbc_proxy work out what information is relevant.
        """
        from app.dao.broadcast_message_dao import (
            get_earlier_events_for_broadcast_event,
        )

        earlier_events = [event for event in get_earlier_events_for_broadcast_event(self.id)]
        ret = []
        for event in earlier_events:
            provider_message = event.get_provider_message(provider)
            if provider_message is None:
                # TODO: We should figure out what to do if a previous message hasn't been sent out yet.
                # We don't want to not cancel a message just because it's stuck in a queue somewhere.
                # This exception should probably be named, and then should be caught further up and handled
                # appropriately.
                raise Exception(
                    f"Cannot get earlier message references for event {self.id}, previous event {event.id} has not "
                    + f' been sent to provider "{provider}" yet'
                )
            ret.append(provider_message)
        return ret

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "broadcast_message_id": str(self.broadcast_message_id),
            # sent_at is required by BroadcastMessageTemplate.from_broadcast_event
            "sent_at": self.sent_at.strftime(DATETIME_FORMAT),
            "message_type": self.message_type,
            "transmitted_content": self.transmitted_content,
            "transmitted_areas": self.transmitted_areas,
            "transmitted_sender": self.transmitted_sender,
            "transmitted_starts_at": get_dt_string_or_none(self.transmitted_starts_at),
            # transmitted_finishes_at is required by BroadcastMessageTemplate.from_broadcast_event
            "transmitted_finishes_at": self.transmitted_finishes_at.strftime(DATETIME_FORMAT),
        }


class BroadcastProvider:
    EE = "ee"
    VODAFONE = "vodafone"
    THREE = "three"
    O2 = "o2"

    PROVIDERS = [EE, VODAFONE, THREE, O2]


ALL_BROADCAST_PROVIDERS = "all"


class BroadcastProviderMessageStatus:
    TECHNICAL_FAILURE = "technical-failure"  # Couldn’t send (cbc proxy 5xx/4xx)
    SENDING = "sending"  # Sent to cbc, awaiting response
    ACK = "returned-ack"  # Received ack response
    ERR = "returned-error"  # Received error response

    STATES = [TECHNICAL_FAILURE, SENDING, ACK, ERR]


class BroadcastProviderMessage(db.Model):
    """
    A row in this table represents the XML blob sent to a single provider.
    """

    __tablename__ = "broadcast_provider_message"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    broadcast_event_id = db.Column(UUID(as_uuid=True), db.ForeignKey("broadcast_event.id"))
    broadcast_event = db.relationship("BroadcastEvent", backref="provider_messages")

    # 'ee', 'three', 'vodafone', etc
    provider = db.Column(db.String)

    status = db.Column(db.String)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    UniqueConstraint(broadcast_event_id, provider)

    message_number = association_proxy("broadcast_provider_message_number", "broadcast_provider_message_number")


class BroadcastProviderMessageNumber(db.Model):
    """
    To send IBAG messages via the CBC proxy to Nokia CBC appliances, Notify must generate and store a numeric
    message_number alongside the message ID (GUID).
    Subsequent messages (Update, Cancel) in IBAG format must reference the original message_number & message_id.
    This model relates broadcast_provider_message_id to that numeric message_number.
    """

    __tablename__ = "broadcast_provider_message_number"

    sequence = Sequence("broadcast_provider_message_number_seq")
    broadcast_provider_message_number = db.Column(
        db.Integer, sequence, server_default=sequence.next_value(), primary_key=True
    )
    broadcast_provider_message_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("broadcast_provider_message.id"), nullable=False
    )
    broadcast_provider_message = db.relationship(
        "BroadcastProviderMessage", backref=db.backref("broadcast_provider_message_number", uselist=False)
    )


class ServiceBroadcastSettings(db.Model):
    """
    Every broadcast service should have one and only one row in this table.
    """

    __tablename__ = "service_broadcast_settings"

    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), primary_key=True, nullable=False)
    service = db.relationship(Service, backref=db.backref("service_broadcast_settings", uselist=False))
    channel = db.Column(db.String(255), db.ForeignKey("broadcast_channel_types.name"), nullable=False)
    provider = db.Column(db.String, db.ForeignKey("broadcast_provider_types.name"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)


class BroadcastChannelTypes(db.Model):
    __tablename__ = "broadcast_channel_types"

    name = db.Column(db.String(255), primary_key=True)


class BroadcastProviderTypes(db.Model):
    __tablename__ = "broadcast_provider_types"

    name = db.Column(db.String(255), primary_key=True)


class ServiceBroadcastProviderRestriction(db.Model):
    """
    TODO: Drop this table as no longer used

    Most services don't send broadcasts. Of those that do, most send to all broadcast providers.
    However, some services don't send to all providers. These services are test services that we or the providers
    themselves use.

    This table links those services. There should only be one row per service in this table, and this is enforced by
    the service_id being a primary key.
    """

    __tablename__ = "service_broadcast_provider_restriction"

    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey("services.id"), primary_key=True, nullable=False)
    service = db.relationship(Service, backref=db.backref("service_broadcast_provider_restriction", uselist=False))

    provider = db.Column(db.String, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)


class WebauthnCredential(db.Model):
    """
    A table that stores data for registered webauthn credentials.
    """

    __tablename__ = "webauthn_credential"

    id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    user = db.relationship(User, backref=db.backref("webauthn_credentials"))

    name = db.Column(db.String, nullable=False)

    # base64 encoded CBOR. used for logging in. https://w3c.github.io/webauthn/#sctn-attested-credential-data
    credential_data = db.Column(db.String, nullable=False)

    # base64 encoded CBOR. used for auditing. https://www.w3.org/TR/webauthn-2/#authenticatorattestationresponse
    registration_response = db.Column(db.String, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    logged_in_at = db.Column(db.DateTime, nullable=True)

    def serialize(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "credential_data": self.credential_data,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
            "logged_in_at": get_dt_string_or_none(self.logged_in_at),
        }


class FeatureToggle(db.Model):
    """
    This table is used to store feature toggles that can be updated with the intention
    of changing the application's behaviour in some way, without having to run an
    entire deployment just for that change.
    """

    __tablename__ = "feature_toggles"

    name = db.Column(db.String(255), primary_key=True)
    is_enabled = db.Column(db.Boolean, nullable=False)
    display_html = db.Column(db.String, nullable=True)

    def serialize(self):
        return {"name": self.name, "is_enabled": self.is_enabled, "display_html": self.display_html}


class FailedLogin(db.Model):
    """
    This table is used to store failed logins.
    """

    __tablename__ = "failed_logins"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip = db.Column(INET)
    attempted_at = db.Column(
        db.DateTime, index=True, unique=False, nullable=False, default=datetime.datetime.now(datetime.timezone.utc)
    )

    def serialize(self):
        return {
            "id": self.id,
            "ip": self.ip,
            "attempted_at": self.attempted_at,
        }


class PasswordHistory(db.Model):
    """
    This table is used to store historic passwords.
    """

    __tablename__ = "password_history"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), default=uuid.uuid4)
    _password = db.Column(db.String, index=False, unique=False, nullable=False)
    password_changed_at = db.Column(
        db.DateTime, index=True, unique=False, nullable=False, default=datetime.datetime.now(datetime.timezone.utc)
    )

    @property
    def password(self):
        raise AttributeError("Password not readable")

    @password.setter
    def password(self, password):
        self._password = hashpw(password)

    def check_password(self, password):
        return check_hash(password, self._password)

    def serialize(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "_password": self._password,
            "password_changed_at": self.password_changed_at,
        }


class CommonPasswords(db.Model):
    """
    This table is used to store common passwords.
    """

    __tablename__ = "common_passwords"

    password = db.Column(db.String, primary_key=True, index=True, unique=True, nullable=False)

    def serialize(self):
        return {
            "password": self.password,
        }
