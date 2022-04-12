import json
import os

import pytest

from app.cloudfoundry_config import (
    extract_cloudfoundry_config,
    set_config_env_vars,
)


@pytest.fixture
def cloudfoundry_config():
    return {
        'postgres': [{
            'credentials': {
                'uri': 'postgres uri'
            }
        }],
        'redis': [{
            'credentials': {
                'uri': 'redis uri'
            }
        }],
        'user-provided': []
    }


@pytest.fixture
def vcap_application(os_environ):
    os.environ['VCAP_APPLICATION'] = '{"space_name": "🚀🌌"}'


def test_extract_cloudfoundry_config_populates_other_vars(cloudfoundry_config, vcap_application):
    os.environ['VCAP_SERVICES'] = json.dumps(cloudfoundry_config)
    extract_cloudfoundry_config()

    assert os.environ['SQLALCHEMY_DATABASE_URI'] == 'postgresql uri'
    assert os.environ['REDIS_URL'] == 'redis uri'
    assert os.environ['NOTIFY_ENVIRONMENT'] == '🚀🌌'
    assert os.environ['NOTIFY_LOG_PATH'] == '/home/vcap/logs/app.log'


def test_set_config_env_vars_ignores_unknown_configs(cloudfoundry_config, vcap_application):
    cloudfoundry_config['foo'] = {'credentials': {'foo': 'foo'}}
    cloudfoundry_config['user-provided'].append({
        'name': 'bar', 'credentials': {'bar': 'bar'}
    })

    set_config_env_vars(cloudfoundry_config)

    assert 'foo' not in os.environ
    assert 'bar' not in os.environ


def test_set_config_env_vars_copes_if_redis_not_set(cloudfoundry_config, vcap_application):
    del cloudfoundry_config['redis']
    set_config_env_vars(cloudfoundry_config)
    assert 'REDIS_URL' not in os.environ
