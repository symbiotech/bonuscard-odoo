import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    def _get_company_instance(self, company):
        domain = [("active", "=", True)]
        if company:
            domain.append(("company_id", "=", company.id))
        instance = (
            self.env["bonuscard.connector.instance"].sudo().search(domain, limit=1)
        )
        return instance

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
        self,
        instance,
        endpoint="",
        method="GET",
        payload=None,
        authenticated=True,
        params=None,
    ):
        instance.ensure_one()
        url = instance._build_url(endpoint)
        if params:
            url = f"{url}?{urlencode(params)}"
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
            raise BonuscardHttpError(
                self.env._("Bonuscard API HTTP error: %s", message or err.reason),
                status_code=err.code,
            ) from err
        except URLError as err:
            raise UserError(
                self.env._("Bonuscard API connection error: %s", err.reason)
            ) from err

        self._raise_on_api_error(decoded_response)
        return decoded_response

    def check_access_rights(self, operation, raise_exception=True):
        """Grant read access on this abstract service model for RPC calls.

        POS invokes :meth:`validate_purchase_for_pos` via ``call_kw``, which
        enforces model access rights (typically requiring ``read`` on the
        model). Since this is an abstract service model without an
        ``ir.model.access`` entry, we explicitly allow ``read`` while
        delegating other operations to the superclass.
        """
        if operation == "read":
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    def test_connection(self, instance):
        instance.ensure_one()

        try:
            return self.request(instance, endpoint="", method="GET")
        except BonuscardHttpError as err:
            if err.status_code in (404, 405):
                return {"reachable": True}
            raise

    def search_customers(self, instance, query):
        instance.ensure_one()
        if not query:
            return []
        payload = self.request(
            instance,
            endpoint="SearchCustomers",
            method="GET",
            params={"query": query},
        )
        return payload.get("customers") or []

    def validate_purchase(
        self,
        instance,
        customer_identifier,
        checkout_items,
        transaction_identifier=None,
        codes=None,
    ):
        instance.ensure_one()
        body = {
            "customerIdentifier": customer_identifier,
            "checkoutItems": checkout_items,
        }
        if transaction_identifier:
            body["transactionIdentifier"] = transaction_identifier
        if codes:
            body["codes"] = codes
        return self.request(
            instance, endpoint="ValidatePurchase", method="POST", payload=body
        )

    @api.model
    def validate_purchase_for_pos(
        self, partner_id, order_lines, transaction_identifier=None
    ):
        """Called from POS JS before payment to apply Bonuscard discounts.

        Args:
            partner_id: int – the POS partner's id
            order_lines: list of {product_id, qty, price_unit}
            transaction_identifier: str or None – preserved across calls

        Returns a dict with keys: error, messages, transactionIdentifier,
        totalDiscount, resultItems (or error keys on failure).
        """
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return {
                "error": True,
                "messages": [self.env._("Partner not found.")],
            }

        commercial_partner = partner.commercial_partner_id
        customer_identifier = commercial_partner.bonuscard_recruitment_code
        if not customer_identifier:
            return {
                "error": True,
                "messages": [
                    self.env._("Customer does not have a Bonuscard recruitment code.")
                ],
            }

        company = commercial_partner.company_id or self.env.company
        instance = self._get_company_instance(company)
        if not instance:
            return {
                "error": True,
                "messages": [
                    self.env._("No active Bonuscard connection is configured.")
                ],
            }

        if not isinstance(order_lines, list):
            return {
                "error": True,
                "messages": [self.env._("Invalid order payload from POS.")],
            }

        sanitized_lines = [line for line in order_lines if isinstance(line, dict)]
        product_ids = [
            line["product_id"] for line in sanitized_lines if line.get("product_id")
        ]
        products = {p.id: p for p in self.env["product.product"].browse(product_ids)}
        checkout_items = []
        for line in sanitized_lines:
            product = products.get(line.get("product_id"))
            if not product:
                continue
            ean = product.barcode or product.default_code
            if not ean:
                continue
            checkout_items.append(
                {
                    "ean": ean,
                    "quantity": line.get("qty", 1),
                    "pricePerItem": line.get("price_unit", 0),
                }
            )

        if not checkout_items:
            return {
                "error": True,
                "messages": [
                    self.env._(
                        "No products with a barcode or article number found in the order."
                    )
                ],
            }

        try:
            return self.validate_purchase(
                instance,
                customer_identifier,
                checkout_items,
                transaction_identifier=transaction_identifier,
            )
        except Exception as exc:  # pylint: disable=broad-except
            # POS flow must remain non-blocking: return an error payload instead
            # of raising and let the frontend continue with normal payment.
            if isinstance(exc, UserError):
                # Surface only the user-safe message from UserError subclasses.
                message = getattr(exc, "name", None) or str(exc)
            else:
                # Log unexpected errors server-side and return a generic message
                # to avoid leaking internal details to the POS frontend.
                _logger.exception(
                    "Unexpected error during Bonuscard validation for partner %s",
                    partner.id if partner else None,
                )
                message = self.env._("Bonuscard validation failed.")
            return {
                "error": True,
                "messages": [message],
            }
