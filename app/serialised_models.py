from collections import defaultdict
from functools import partial
from threading import RLock

import cachetools
from emergency_alerts_utils.serialised_model import (
    SerialisedModel,
    SerialisedModelCollection,
)
from flask import current_app
from werkzeug.utils import cached_property

from app import db
from app.dao.api_key_dao import get_model_api_keys
from app.dao.services_dao import dao_fetch_service_by_id

caches = defaultdict(partial(cachetools.TTLCache, maxsize=1024, ttl=2))
locks = defaultdict(RLock)


def memory_cache(func):
    @cachetools.cached(
        cache=caches[func.__qualname__],
        lock=locks[func.__qualname__],
        key=ignore_first_argument_cache_key,
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def ignore_first_argument_cache_key(cls, *args, **kwargs):
    return cachetools.keys.hashkey(*args, **kwargs)


class SerialisedTemplate(SerialisedModel):
    ALLOWED_PROPERTIES = {
        "archived",
        "content",
        "id",
        "template_type",
        "version",
    }

    @classmethod
    @memory_cache
    def from_id_and_service_id(cls, template_id, service_id, version=None):
        return cls(cls.get_dict(template_id, service_id, version)["data"])

    @staticmethod
    def get_dict(template_id, service_id, version):
        from app.dao import templates_dao
        from app.schemas import template_schema

        fetched_template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id,
            version=version,
        )

        template_dict = template_schema.dump(fetched_template)
        db.session.commit()

        return {"data": template_dict}


class SerialisedService(SerialisedModel):
    ALLOWED_PROPERTIES = {
        "id",
        "name",
        "active",
        "permissions",
        "restricted",
    }

    @classmethod
    @memory_cache
    def from_id(cls, service_id):
        return cls(cls.get_dict(service_id)["data"])

    @staticmethod
    def get_dict(service_id):
        from app.schemas import service_schema

        service_dict = service_schema.dump(dao_fetch_service_by_id(service_id))
        db.session.commit()

        return {"data": service_dict}

    @cached_property
    def api_keys(self):
        return SerialisedAPIKeyCollection.from_service_id(self.id)

    @property
    def high_volume(self):
        return self.id in current_app.config["HIGH_VOLUME_SERVICE"]


class SerialisedAPIKey(SerialisedModel):
    ALLOWED_PROPERTIES = {
        "id",
        "secret",
        "expiry_date",
        "key_type",
    }


class SerialisedAPIKeyCollection(SerialisedModelCollection):
    model = SerialisedAPIKey

    @classmethod
    @memory_cache
    def from_service_id(cls, service_id):
        keys = [
            {k: getattr(key, k) for k in SerialisedAPIKey.ALLOWED_PROPERTIES} for key in get_model_api_keys(service_id)
        ]
        db.session.commit()
        return cls(keys)
