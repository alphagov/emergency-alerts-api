class QueueNames(object):
    PERIODIC = "periodic-tasks"
    BROADCASTS = "broadcast-tasks"
    GOVUK_ALERTS = "govuk-alerts"


class TaskNames(object):
    PUBLISH_GOVUK_ALERTS = "publish-govuk-alerts"
    TRIGGER_GOVUK_HEALTHCHECK = "trigger-govuk-alerts-healthcheck"
