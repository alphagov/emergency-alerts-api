import pytest

from tests import (
    create_admin_authorization_header,
    create_service_authorization_header,
)


@pytest.mark.parametrize("endpoint", ["/", "/v2/broadcast", "/notifications"])
def test_service_request_returns_hsts_header(endpoint, client, sample_service):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.options(
        path=endpoint,
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubdomains; preload"


@pytest.mark.parametrize("endpoint", ["/", "/v2/broadcast", "/notifications"])
def test_service_request_returns_referrer_policy(endpoint, client, sample_service):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.options(
        path=endpoint,
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize(
    "endpoint",
    ["/", "/events", "/feature-toggle", "/organisations", "/platform-stats", "/service"],
)
def test_admin_request_returns_hsts_header(endpoint, client):
    auth_header = create_admin_authorization_header()
    response = client.options(
        path=endpoint,
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubdomains; preload"


@pytest.mark.parametrize(
    "endpoint", ["/", "/events", "/feature-toggle", "/organisations", "/platform-stats", "/service"]
)
def test_admin_request_returns_referrer_policy(endpoint, client):
    auth_header = create_admin_authorization_header()
    response = client.options(
        path=endpoint,
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "no-referrer"
