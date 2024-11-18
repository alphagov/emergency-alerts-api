import calendar
import sys
import time

import jwt


def create_jwt_token(service_id, api_key):
    """
    Create JWT token for Emergency Alerts Service API

    Tokens have standard header:
      - "typ": "JWT",
      - "alg": "HS256"

    JWT claims are:
      - iss: identifier for the target service
      - iat: 'issued at' in epoch seconds (UTC)

    Extract the 'api_key' and 'service_id' from a valid API key as follows:
        apikey_March_2024-00c99afd-e4da-4956-810d-90467f8cd446-a86a5e5a-7a29-423c-a84d-c11103cc9dae
                          <----------- service_id -----------> <------------ api_key ------------->

    Note: The JWT is valid for 30 seconds +/- any disparity between client and
          server system clocks.

    :param service_id: Identifier for the Emergency Alerts service
    :param api_key: Api key issued by the Emergency Alerts service
    :return: JWT token for this request
    """

    headers = {"typ": "JWT", "alg": "HS256"}

    claims = {"iss": service_id, "iat": calendar.timegm(time.gmtime())}

    return jwt.encode(payload=claims, key=api_key, headers=headers)


if __name__ == "__main__":
    service_id = sys.argv[1]
    api_key = sys.argv[2]
    print(create_jwt_token(service_id, api_key))
