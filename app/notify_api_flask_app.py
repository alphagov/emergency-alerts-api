from flask import Flask


class NotifyApiFlaskApp(Flask):
    @property
    def is_prod(self):
        return self.config["HOST"] == "production"

    @property
    def is_test(self):
        return self.config["HOST"] == "test"

    @property
    def should_send_zendesk_alerts(self):
        return self.is_test or self.is_prod
