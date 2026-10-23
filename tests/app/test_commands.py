from datetime import datetime
from io import BytesIO
from unittest.mock import Mock, patch

from geoalchemy2.shape import to_shape

from app.commands import (
    add_areas,
    audit_broadcast_areas,
    local_dev_broadcast_permissions,
)
from app.dao.services_dao import dao_add_user_to_service
from app.models import (
    BROADCAST_TYPE,
    BroadcastMessage,
    BroadcastStatusType,
    GeographyPolygons,
    GeographyType,
    GeographyVersion,
)
from tests.app.db import create_broadcast_message, create_template, create_user


def test_local_dev_broadcast_permissions(
    sample_service,
    sample_broadcast_service,
    notify_api,
):
    user = create_user()
    dao_add_user_to_service(sample_service, user)
    dao_add_user_to_service(sample_broadcast_service, user)

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) == 0

    notify_api.test_cli_runner().invoke(local_dev_broadcast_permissions, ["-u", user.id])

    assert len(user.get_permissions(sample_service.id)) == 6
    assert len(user.get_permissions(sample_broadcast_service.id)) > 0


def test_audit_broadcast_areas_reports_live_broadcasts_with_invalid_areas(sample_broadcast_service, notify_api):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    valid_areas = {
        "names": ["Manchester"],
        "simple_polygons": [[[53.48, -2.24], [53.49, -2.24], [53.49, -2.23], [53.48, -2.24]]],
    }
    starts_at = datetime(2021, 6, 15, 12, 0, 0)
    create_broadcast_message(template, areas=valid_areas, starts_at=starts_at, status=BroadcastStatusType.COMPLETED)
    missing_names = create_broadcast_message(
        template,
        areas={"simple_polygons": valid_areas["simple_polygons"]},
        starts_at=starts_at,
        status=BroadcastStatusType.CANCELLED,
    )
    no_polygons = create_broadcast_message(
        template,
        areas={"names": ["Manchester"], "simple_polygons": []},
        starts_at=starts_at,
        status=BroadcastStatusType.BROADCASTING,
    )
    stubbed = create_broadcast_message(
        template, starts_at=starts_at, stubbed=True, status=BroadcastStatusType.COMPLETED
    )
    # gov.uk/alerts only gets alerts that started on or after 25 May 2021
    before_cutoff = create_broadcast_message(
        template, starts_at=datetime(2021, 5, 24, 12, 0, 0), status=BroadcastStatusType.COMPLETED
    )
    # drafts are never published, so aren't checked
    draft = create_broadcast_message(template, status=BroadcastStatusType.DRAFT)

    result = notify_api.test_cli_runner().invoke(audit_broadcast_areas)

    assert result.exit_code == 0
    assert f"{missing_names.id} status=cancelled stubbed=False exclude=False" in result.output
    assert "    (root): 'names' is a required property" in result.output
    assert f"{no_polygons.id} status=broadcasting stubbed=False exclude=False" in result.output
    assert "    simple_polygons: [] should be non-empty" in result.output
    assert f"{stubbed.id} status=completed stubbed=True exclude=False" in result.output
    assert f"{before_cutoff.id} status=completed stubbed=False exclude=False" in result.output
    assert str(draft.id) not in result.output

    lines_for = {line.split()[0]: line for line in result.output.splitlines() if not line.startswith(" ")}
    assert lines_for[str(missing_names.id)].endswith("published=True")
    assert lines_for[str(no_polygons.id)].endswith("published=True")
    assert lines_for[str(stubbed.id)].endswith("published=False")
    assert lines_for[str(before_cutoff.id)].endswith("published=False")
    assert result.output.endswith("Checked 5 live alerts: 4 failed, 2 of them published to gov.uk/alerts\n")
    assert BroadcastMessage.query.get(missing_names.id).areas == {"simple_polygons": valid_areas["simple_polygons"]}


def test_add_areas(notify_api, notify_db_session):
    csv_data = (
        "geographic_id,name,geometry,parent_geography_id\n" 'test-area,Test area,"POLYGON ((0 0, 1 0, 1 1, 0 0))",\n'
    )

    s3 = Mock()
    s3.get_object.return_value = {
        "Body": BytesIO(csv_data.encode("utf-8")),
    }

    with patch("app.commands.boto3.client", return_value=s3):
        notify_api.test_cli_runner().invoke(add_areas)

    countries_type = GeographyType.query.filter_by(route="countries").one()
    assert countries_type.name == "Countries"

    geography_version = GeographyVersion.query.filter_by(
        geography_type_id=countries_type.id,
        version="1.0.0",
    ).one()

    assert geography_version.geography_type_id == countries_type.id
    assert geography_version.state == "active"

    polygons = GeographyPolygons.query.filter_by(
        geography_version_id=geography_version.id,
    ).all()

    polygon_row = polygons[0]
    assert polygon_row.name == "Test area"
    assert to_shape(polygon_row.geometry).wkt == "POLYGON ((0 0, 1 0, 1 1, 0 0))"
