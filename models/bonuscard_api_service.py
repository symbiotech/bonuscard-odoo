import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import models
from odoo.exceptions import UserError


class BonuscardHttpError(UserError):
    """Raised when the Bonuscard API returns an HTTP error response.

    Extends :class:`~odoo.exceptions.UserError` so that existing code paths
    that catch ``UserError`` continue to work, while also exposing the raw
    HTTP *status_code* so that callers can branch on the numeric code rather
    than parsing the human-readable message string.
    """

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class BonuscardApiService(models.AbstractModel):
    _name = "bonuscard.api.service"
    _description = "Bonuscard API Service"

    def _decode_response(self, response):
        raw_data = response.read().decode("utf-8")
        if not raw_data:
            return {}

        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            return {"raw": raw_data}

    def _extract_error_messages(self, payload):
        messages = (
            payload.get("messages")
            or payload.get("errorMessages")
            or payload.get("errors")
        )
        if isinstance(messages, str):
            return [messages]
        if isinstance(messages, list):
            return [str(message) for message in messages if message]
        return []

    def _raise_on_api_error(self, payload):
        if not isinstance(payload, dict) or not payload.get("error"):
            return

        error_code = (
            payload.get("errorCode") or payload.get("code") or self.env._("unknown")
        )
        messages = self._extract_error_messages(payload)
        if messages:
            raise UserError(
                self.env._(
                    "Bonuscard API error (%s): %s", error_code, " | ".join(messages)
                )
            )

        raise UserError(self.env._("Bonuscard API error (%s).", error_code))

    def request(
        self, instance, endpoint="", method="GET", payload=None, authenticated=True
    ):
        instance.ensure_one()
        url = instance._build_url(endpoint)
        body = None
        headers = {}

        if authenticated:
            headers.update(instance._build_headers())
        else:
            headers["Accept"] = "application/json"

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, data=body, headers=headers, method=method)
        timeout = int(instance.request_timeout or 20)

        try:
            with urlopen(request, timeout=timeout) as response:
                decoded_response = self._decode_response(response)
        except HTTPError as err:
            message = err.read().decode("utf-8", errors="ignore")
            if err.code in (401, 403):
                raise UserError(
                    self.env._(
                        "Bonuscard authentication failed. Check the API username and password."
                    )
                ) from err
            raise UserError(
                self.env._("Bonuscard API HTTP error: %s", message or err.reason)
            ) from err
        except URLError as err:
            raise UserError(
                self.env._("Bonuscard API connection error: %s", err.reason)
            ) from err

        self._raise_on_api_error(decoded_response)
        return decoded_response

    def test_connection(self, instance):
        instance.ensure_one()

        try:
            return self.request(instance, endpoint="", method="GET")
        except BonuscardHttpError as err:
            if err.status_code in (404, 405):
                return {"reachable": True}
            raise
