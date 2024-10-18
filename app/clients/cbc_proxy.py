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

aws_region = os.environ.get("AWS_REGION", "eu-west-2")


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
                    region_name=aws_region,
                    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                    aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
                )
                if app.config.get("HOST") == "local"
                else boto3.client("lambda", region_name=aws_region)
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

        payload["cbc_target"] = self.CBC_B
        result = self._invoke_lambda(self.primary_lambda, payload)
        if result:
            return True

        if not self.secondary_lambda:
            error_message = f"{self.primary_lambda} failed and no secondary lambda defined"
            current_app.logger.info(error_message, extra={"python_module": __name__})
            raise CBCProxyRetryableException(error_message)

        payload["cbc_target"] = self.CBC_A
        result = self._invoke_lambda(self.secondary_lambda, payload)
        if result:
            return True

        payload["cbc_target"] = self.CBC_B
        result = self._invoke_lambda(self.secondary_lambda, payload)
        if result:
            return True

        error_message = f"{self.primary_lambda} and {self.secondary_lambda} lambdas failed"
        current_app.logger.info(error_message, extra={"python_module": __name__})
        raise CBCProxyRetryableException(error_message)

    def _invoke_lambda(self, lambda_name, payload):
        payload_bytes = bytes(json.dumps(payload), encoding="utf8")
        try:
            current_app.logger.info(
                f"Calling lambda {lambda_name}",
                extra={
                    "lambda_payload": str(payload)[:1000],
                    "lambda_invocation_type": "RequestResponse",
                    "lambda_arn": f"{self._arn_prefix}{lambda_name}",
                },
            )
            response = self._lambda_client.invoke(
                FunctionName=f"{self._arn_prefix}{lambda_name}",
                InvocationType="RequestResponse",
                Payload=payload_bytes,
            )
        except botocore.exceptions.ClientError:
            current_app.logger.error(f"Boto3 ClientError on lambda {lambda_name}", extra={"python_module": __name__})
            success = False
            return success

        if response["StatusCode"] > 299:
            current_app.logger.info(
                f"Error calling lambda {lambda_name}",
                extra={
                    "python_module": __name__,
                    "status_code": response["StatusCode"],
                    "result_payload": _convert_lambda_payload_to_json(response.get("Payload").read()),
                },
            )
            success = False

        elif "FunctionError" in response:
            current_app.logger.info(
                f"FunctionError calling lambda {lambda_name}",
                extra={
                    "python_module": __name__,
                    "status_code": response["StatusCode"],
                    "result_payload": _convert_lambda_payload_to_json(response.get("Payload").read()),
                },
            )
            success = False

        else:
            target = payload["cbc_target"]
            current_app.logger.info(
                f"Success calling lambda {lambda_name} with CBC target {target}",
                extra={
                    "python_module": __name__,
                    "status_code": response["StatusCode"],
                },
            )
            success = True

        return success

    def infer_language_from(self, content):
        if non_gsm_characters(content):
            return self.LANGUAGE_WELSH
        return self.LANGUAGE_ENGLISH


def _convert_lambda_payload_to_json(byte_string):
    json_string = byte_string.decode("utf-8").replace('\\"', "").replace("\\n", "").replace("\\", "").strip()
    reduced_whitespace = " ".join(json_string.split())
    return json.loads(reduced_whitespace)


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
