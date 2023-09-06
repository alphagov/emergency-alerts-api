import json
import os
import uuid
from abc import ABC, abstractmethod

import boto3
import botocore
from emergency_alerts_utils.template import non_gsm_characters
from flask import current_app
from sqlalchemy.schema import Sequence

from app.config import BroadcastProvider
from app.utils import DATETIME_FORMAT, format_sequential_number

# The variable names in this file have specific meaning in a CAP message
#
# identifier is a unique field for each CAP message
#
# headline is a field which we are not sure if we will use
#
# description is the body of the message

# areas is a list of dicts, with the following items
# * description is a string which populates the areaDesc field
# * polygon is a list of lat/long pairs
#
# previous_provider_messages is a list of previous events (models.py::BroadcastProviderMessage)
# ie a Cancel message would have a unique event but have the event of
#    the preceeding Alert message in the previous_provider_messages field


class CBCProxyRetryableException(Exception):
    pass


class CBCProxyClient:
    _lambda_client = None
    _arn_prefix = ""

    def init_app(self, app):
        if app.config.get("CBC_PROXY_ENABLED"):
            if app.config.get("CBC_ACCOUNT_NUMBER") is not None:
                self._arn_prefix = app.config.get("CBC_ACCOUNT_NUMBER") + ":function:"
            self._lambda_client = (
                boto3.client(
                    "lambda",
                    region_name="eu-west-2",
                    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                    aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
                )
                if app.config.get("NOTIFY_ENVIRONMENT") == "development"
                else boto3.client("lambda", region_name="eu-west-2")
            )

    def get_proxy(self, provider):
        proxy_classes = {
            BroadcastProvider.EE: CBCProxyEE,
            BroadcastProvider.THREE: CBCProxyThree,
            BroadcastProvider.O2: CBCProxyO2,
            BroadcastProvider.VODAFONE: CBCProxyVodafone,
        }
        return proxy_classes[provider](self._lambda_client, self._arn_prefix)


class CBCProxyClientBase(ABC):
    CBC_A = "cbc_a"
    CBC_B = "cbc_b"

    @property
    @abstractmethod
    def primary_lambda(self):
        pass

    @property
    @abstractmethod
    def secondary_lambda(self):
        pass

    @property
    @abstractmethod
    def LANGUAGE_ENGLISH(self):
        pass

    @property
    @abstractmethod
    def LANGUAGE_WELSH(self):
        pass

    def __init__(self, lambda_client, arn_prefix):
        self._lambda_client = lambda_client
        self._arn_prefix = arn_prefix

    def send_link_test(self):
        self._send_link_test(self.primary_lambda, self.CBC_A)
        self._send_link_test(self.primary_lambda, self.CBC_B)
        self._send_link_test(self.secondary_lambda, self.CBC_A)
        self._send_link_test(self.secondary_lambda, self.CBC_B)

    def _send_link_test(
        self,
        lambda_name,
        cbc_target,
    ):
        pass

    def create_and_send_broadcast(
        self, identifier, headline, description, areas, sent, expires, channel, message_number=None
    ):
        pass

    # We have not implementated updating a broadcast
    def update_and_send_broadcast(
        self,
        identifier,
        previous_provider_messages,
        headline,
        description,
        areas,
        sent,
        expires,
        channel,
        message_number=None,
    ):
        pass

    def cancel_broadcast(
        self, identifier, previous_provider_messages, headline, description, areas, sent, expires, message_number=None
    ):
        pass

    def _invoke_lambdas_with_routing(self, payload):
        payload["cbc_target"] = self.CBC_A
        result = self._invoke_lambda(self.primary_lambda, payload)
        if result:
            return True
        self._log_lambda_info(f"Lambda {self.primary_lambda} to {self.CBC_A} failed")

        payload["cbc_target"] = self.CBC_B
        result = self._invoke_lambda(self.primary_lambda, payload)
        if result:
            return True
        self._log_lambda_info(f"Lambda {self.primary_lambda} to {self.CBC_B} failed")

        if self.secondary_lambda is None:
            raise CBCProxyRetryableException(f"{self.primary_lambda} failed (secondary lambda is unavailable)")

        payload["cbc_target"] = self.CBC_A
        result = self._invoke_lambda(self.secondary_lambda, payload)
        if result:
            return True
        self._log_lambda_info(f"Lambda {self.secondary_lambda} to {self.CBC_A} failed")

        payload["cbc_target"] = self.CBC_B
        result = self._invoke_lambda(self.secondary_lambda, payload)
        if result:
            return True
        self._log_lambda_info(f"Lambda {self.secondary_lambda} to {self.CBC_B} failed")

        error_message = f"{self.primary_lambda} and {self.secondary_lambda} lambdas failed"
        self._log_lambda_error(error_message)
        raise CBCProxyRetryableException(error_message)

    def _invoke_lambda(self, lambda_name, payload):
        payload_bytes = bytes(json.dumps(payload), encoding="utf8")
        try:
            self._log_lambda_info(f"Calling lambda {lambda_name} with payload {str(payload)[:1000]}")
            result = self._lambda_client.invoke(
                FunctionName=f"{self._arn_prefix}{lambda_name}",
                InvocationType="RequestResponse",
                Payload=payload_bytes,
            )
        except botocore.exceptions.ClientError:
            self._log_lambda_error(f"Boto3 ClientError on lambda {lambda_name}")
            success = False
            return success

        if result["StatusCode"] > 299:
            self._log_lambda_info(
                f"Error calling lambda {lambda_name} with status code { result['StatusCode']}, {result.get('Payload')}"
            )
            success = False

        elif "FunctionError" in result:
            self._log_lambda_info(
                f"Error calling lambda {lambda_name} with function error { result['Payload'].read() }"
            )
            success = False

        else:
            success = True

        return success

    def infer_language_from(self, content):
        if non_gsm_characters(content):
            return self.LANGUAGE_WELSH
        return self.LANGUAGE_ENGLISH

    def _log_lambda_info(self, msg):
        current_app.logger.info(
            {
                "source": "eas-app-api",
                "module": __name__,
                "message": msg,
            }
        )

    def _log_lambda_error(self, msg):
        current_app.logger.error(
            {
                "source": "eas-app-api",
                "module": __name__,
                "message": msg,
            }
        )


class CBCProxyOne2ManyClient(CBCProxyClientBase):
    LANGUAGE_ENGLISH = "en-GB"
    LANGUAGE_WELSH = "cy-GB"

    def _send_link_test(
        self,
        lambda_name,
        cbc_target,
    ):
        """
        link test - open up a connection to a specific provider, and send them an xml payload with a <msgType> of
        test.
        """
        payload = {
            "message_type": "test",
            "identifier": str(uuid.uuid4()),
            "message_format": "cap",
            "cbc_target": cbc_target,
        }

        self._invoke_lambda(lambda_name=lambda_name, payload=payload)

    def create_and_send_broadcast(
        self, identifier, headline, description, areas, sent, expires, channel, message_number=None
    ):
        payload = {
            "message_type": "alert",
            "identifier": identifier,
            "message_format": "cap",
            "headline": headline,
            "description": description,
            "areas": areas,
            "sent": sent,
            "expires": expires,
            "language": self.infer_language_from(description),
            "channel": channel,
        }
        self._invoke_lambdas_with_routing(payload=payload)

    def cancel_broadcast(self, identifier, previous_provider_messages, sent, message_number=None):
        payload = {
            "message_type": "cancel",
            "identifier": identifier,
            "message_format": "cap",
            "references": [
                {"message_id": str(message.id), "sent": message.created_at.strftime(DATETIME_FORMAT)}
                for message in previous_provider_messages
            ],
            "sent": sent,
        }
        self._invoke_lambdas_with_routing(payload=payload)


class CBCProxyEE(CBCProxyOne2ManyClient):
    primary_lambda = "ee-1-proxy"
    secondary_lambda = "ee-2-proxy" if os.environ.get("ENVIRONMENT") != "staging" else None


class CBCProxyThree(CBCProxyOne2ManyClient):
    primary_lambda = "three-1-proxy"
    secondary_lambda = "three-2-proxy"


class CBCProxyO2(CBCProxyOne2ManyClient):
    primary_lambda = "o2-1-proxy"
    secondary_lambda = "o2-2-proxy"


class CBCProxyVodafone(CBCProxyClientBase):
    primary_lambda = "vodafone-1-proxy"
    secondary_lambda = "vodafone-2-proxy"

    LANGUAGE_ENGLISH = "English"
    LANGUAGE_WELSH = "Welsh"

    def _send_link_test(
        self,
        lambda_name,
        cbc_target,
    ):
        """
        link test - open up a connection to a specific provider, and send them an xml payload with a <msgType> of
        test.
        """
        from app import db

        sequence = Sequence("broadcast_provider_message_number_seq")
        sequential_number = db.session.connection().execute(sequence)
        formatted_seq_number = format_sequential_number(sequential_number)

        payload = {
            "message_type": "test",
            "identifier": str(uuid.uuid4()),
            "message_number": formatted_seq_number,
            "message_format": "ibag",
            "cbc_target": cbc_target,
        }

        self._invoke_lambda(lambda_name=lambda_name, payload=payload)

    def create_and_send_broadcast(
        self, identifier, message_number, headline, description, areas, sent, expires, channel
    ):
        payload = {
            "message_type": "alert",
            "identifier": identifier,
            "message_number": message_number,
            "message_format": "ibag",
            "headline": headline,
            "description": description,
            "areas": areas,
            "sent": sent,
            "expires": expires,
            "language": self.infer_language_from(description),
            "channel": channel,
        }
        self._invoke_lambdas_with_routing(payload=payload)

    def cancel_broadcast(self, identifier, previous_provider_messages, sent, message_number):
        payload = {
            "message_type": "cancel",
            "identifier": identifier,
            "message_number": message_number,
            "message_format": "ibag",
            "references": [
                {
                    "message_id": str(message.id),
                    "message_number": format_sequential_number(message.message_number),
                    "sent": message.created_at.strftime(DATETIME_FORMAT),
                }
                for message in previous_provider_messages
            ],
            "sent": sent,
        }
        self._invoke_lambdas_with_routing(payload=payload)
