from datetime import datetime

from app.commands import audit_broadcast_areas, local_dev_broadcast_permissions
from app.dao.services_dao import dao_add_user_to_service
from app.models import BROADCAST_TYPE, BroadcastMessage, BroadcastStatusType
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
