import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
_REQUEST_RETRY_COUNT = 2
_REQUEST_RETRY_INITIAL_DELAY = 0.5


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


class BonuscardApiError(UserError):
    """Raised when the Bonuscard API returns a business-level error payload."""

    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


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

    def _raise_on_api_error(self, instance, payload):
        if not isinstance(payload, dict) or not payload.get("error"):
            return

        error_code = (
            payload.get("errorCode") or payload.get("code") or self.env._("unknown")
        )
        messages = self._extract_error_messages(payload)
        if messages:
            message = self.env._(
                "Bonuscard API error (%s): %s",
                error_code,
                " | ".join(messages),
            )
        else:
            message = self.env._("Bonuscard API error (%s).", error_code)

        _logger.warning(
            "Bonuscard API business error for instance %s: %s",
            instance.id,
            message,
        )

        try:
            instance.write({"last_error": message})
        except Exception:  # pylint: disable=broad-except
            _logger.exception(
                "Failed to save Bonuscard API error message to instance %s",
                instance.id,
            )

        raise BonuscardApiError(message, error_code=error_code)

    def _should_retry_error(self, err):
        if isinstance(err, HTTPError):
            if err.code in (401, 403):
                return False
            return err.code in _RETRYABLE_HTTP_STATUS_CODES or err.code >= 500
        if isinstance(err, (URLError, TimeoutError)):
            return True
        return False

    def _request(
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

        timeout = int(instance.request_timeout or 20)

        attempt = 0
        while True:
            request = Request(url=url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=timeout) as response:
                    decoded_response = self._decode_response(response)
                self._raise_on_api_error(instance, decoded_response)
                return decoded_response
            except HTTPError as err:
                if err.code in (401, 403):
                    err.read()
                    _logger.warning(
                        "Bonuscard authentication failed for request %s %s: HTTP %s",
                        method,
                        url,
                        err.code,
                        exc_info=True,
                    )
                    raise UserError(
                        self.env._(
                            "Bonuscard authentication failed. Check the API username and password."
                        )
                    ) from err
                if attempt < _REQUEST_RETRY_COUNT and self._should_retry_error(err):
                    err.read()
                    _logger.warning(
                        "Retrying Bonuscard request %s %s after HTTP %s (attempt %s)",
                        method,
                        url,
                        err.code,
                        attempt + 1,
                    )
                    attempt += 1
                    time.sleep(_REQUEST_RETRY_INITIAL_DELAY * attempt)
                    continue
                message = err.read().decode("utf-8", errors="ignore")
                _logger.warning(
                    "Bonuscard HTTP error on %s %s status=%s: %s",
                    method,
                    url,
                    err.code,
                    message or err.reason,
                    exc_info=True,
                )
                raise BonuscardHttpError(
                    self.env._("Bonuscard API HTTP error: %s", message or err.reason),
                    status_code=err.code,
                ) from err
            except (URLError, TimeoutError) as err:
                if attempt < _REQUEST_RETRY_COUNT and self._should_retry_error(err):
                    _logger.warning(
                        "Retrying Bonuscard connection %s %s after %s (attempt %s)",
                        method,
                        url,
                        getattr(err, "reason", str(err)),
                        attempt + 1,
                    )
                    attempt += 1
                    time.sleep(_REQUEST_RETRY_INITIAL_DELAY * attempt)
                    continue
                reason = getattr(err, "reason", str(err))
                _logger.warning(
                    "Bonuscard API connection error on %s %s: %s",
                    method,
                    url,
                    reason,
                    exc_info=True,
                )
                raise UserError(
                    self.env._("Bonuscard API connection error: %s", reason)
                ) from err

    def check_access(self, operation: str) -> None:
        """Grant read access on this abstract service model for RPC calls."""
        if operation == "read" and (
            self.env.user.id == SUPERUSER_ID
            or self.env.user.has_group("point_of_sale.group_pos_user")
            or self.env.user.has_group("bonuscard_odoo.bonuscard_odoo_group_user")
        ):
            return None
        return super().check_access(operation)

    def has_access(self, operation: str) -> bool:
        if operation == "read" and (
            self.env.user.id == SUPERUSER_ID
            or self.env.user.has_group("point_of_sale.group_pos_user")
            or self.env.user.has_group("bonuscard_odoo.bonuscard_odoo_group_user")
        ):
            return True
        return super().has_access(operation)

    def _test_connection(self, instance):
        instance.ensure_one()

        try:
            return self._request(instance, endpoint="", method="GET")
        except BonuscardHttpError as err:
            if err.status_code in (404, 405):
                return {"reachable": True}
            raise

    def _search_customers(self, instance, query):
        instance.ensure_one()
        if not query:
            return []
        payload = self._request(
            instance,
            endpoint="SearchCustomers",
            method="GET",
            params={"query": query},
        )
        return payload.get("customers") or []

    def _register_customer(self, instance, phone_number):
        instance.ensure_one()
        phone_number = (phone_number or "").strip()
        if not phone_number:
            return {}
        return self._request(
            instance,
            endpoint="RegisterCustomer",
            method="POST",
            params={"phoneNumber": phone_number},
        )

    def _validate_purchase(
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
        return self._request(
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
        products = {
            p.id: p for p in self.env["product.product"].browse(product_ids).exists()
        }
        checkout_items = []
        for line in sanitized_lines:
            product = products.get(line.get("product_id"))
            if not product:
                continue
            ean = product.barcode or product.default_code
            if not ean:
                continue

            qty = line.get("qty", 1)
            price_unit = line.get("price_unit", 0)
            try:
                qty = float(qty)
                price_unit = float(price_unit)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue

            checkout_items.append(
                {
                    "ean": ean,
                    "quantity": qty,
                    "pricePerItem": price_unit,
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
            return self._validate_purchase(
                instance,
                customer_identifier,
                checkout_items,
                transaction_identifier=transaction_identifier,
            )
        except BonuscardApiError as exc:
            message = self._get_bonuscard_error_message(
                exc, self.env._("Bonuscard validation failed.")
            )
            return {
                "error": True,
                "messages": [message],
            }
        except Exception as exc:  # pylint: disable=broad-except
            # POS flow must remain non-blocking: return an error payload instead
            # of raising and let the frontend continue with normal payment.
            if isinstance(exc, BonuscardHttpError):
                # Avoid sending raw HTTP response bodies to the POS frontend.
                _logger.warning(
                    "Bonuscard HTTP error during POS validation (HTTP %s) for partner %s",
                    exc.status_code,
                    partner.id,
                )
                message = self.env._("Bonuscard service is temporarily unavailable.")
            elif isinstance(exc, UserError):
                # Surface only the user-safe message from UserError subclasses.
                message = getattr(exc, "name", None) or str(exc)
            else:
                # Log unexpected errors server-side and return a generic message
                # to avoid leaking internal details to the POS frontend.
                _logger.exception(
                    "Unexpected error during Bonuscard validation for partner %s",
                    partner.id,
                )
                message = self.env._("Bonuscard validation failed.")
            return {
                "error": True,
                "messages": [message],
            }

    def _prepare_checkout_items_for_api(self, checkout_items):
        if not isinstance(checkout_items, list):
            return []

        sanitized_items = [item for item in checkout_items if isinstance(item, dict)]
        if not sanitized_items:
            return []

        product_ids = [
            item.get("product_id") for item in sanitized_items if item.get("product_id")
        ]
        products = {
            p.id: p for p in self.env["product.product"].browse(product_ids).exists()
        }

        formatted_items = []
        for item in sanitized_items:
            if (
                item.get("ean")
                and item.get("quantity") is not None
                and item.get("pricePerItem") is not None
            ):
                try:
                    quantity = float(item.get("quantity"))
                    price_per_item = float(item.get("pricePerItem"))
                except (TypeError, ValueError):
                    continue
                if quantity <= 0:
                    continue
                formatted_items.append(
                    {
                        "ean": item.get("ean"),
                        "quantity": quantity,
                        "pricePerItem": price_per_item,
                    }
                )
                continue

            product = products.get(item.get("product_id"))
            if not product:
                continue

            ean = product.barcode or product.default_code
            if not ean:
                continue

            try:
                quantity = float(item.get("qty", 1))
                price_per_item = float(item.get("price_unit", 0))
            except (TypeError, ValueError):
                continue

            if quantity <= 0:
                continue

            formatted_items.append(
                {
                    "ean": ean,
                    "quantity": quantity,
                    "pricePerItem": price_per_item,
                }
            )

        return formatted_items

    def _get_bonuscard_error_message(self, exc, default_message):
        error_code = exc.error_code
        try:
            error_code = int(error_code)
        except (TypeError, ValueError):
            error_code = None

        if error_code == 2:
            return self.env._(
                "Customer is locked to an open transaction. Please try again or restart."
            )
        if error_code == 4:
            return self.env._(
                "Customer needs to verify their Bonuscard account before purchasing."
            )
        return getattr(exc, "name", None) or str(exc) or default_message

    def _finalize_purchase(
        self,
        instance,
        customer_identifier,
        transaction_identifier,
        checkout_items,
        note=None,
        codes=None,
    ):
        instance.ensure_one()
        body = {
            "customerIdentifier": customer_identifier,
            "transactionIdentifier": transaction_identifier,
            "checkoutItems": checkout_items,
        }
        if note:
            body["note"] = note
        if codes:
            body["codes"] = codes
        return self._request(
            instance, endpoint="FinalizePurchase", method="POST", payload=body
        )

    @api.model
    def finalize_purchase_for_pos(
        self, partner_id, transaction_identifier, checkout_items
    ):
        """Called from POS JS after payment succeeds to commit Bonuscard discounts.

        Args:
            partner_id: int – the POS partner's id
            transaction_identifier: str – transaction ID from ValidatePurchase
            checkout_items: list – checkoutItems echoed by ValidatePurchase API response

        Returns a dict with the API response keys, or {error, messages} on failure.
        Never raises — returns an error dict instead.
        """
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return {
                "error": True,
                "messages": [self.env._("Partner not found.")],
            }

        customer_identifier = partner.commercial_partner_id.bonuscard_recruitment_code
        if not customer_identifier:
            return {
                "error": True,
                "messages": [
                    self.env._("Customer does not have a Bonuscard recruitment code."),
                ],
            }

        if not transaction_identifier:
            return {
                "error": True,
                "messages": [self.env._("Missing Bonuscard transaction identifier.")],
            }

        if not isinstance(checkout_items, list):
            return {
                "error": True,
                "messages": [self.env._("Invalid checkout payload from POS.")],
            }

        company = partner.commercial_partner_id.company_id or self.env.company
        instance = self._get_company_instance(company)
        if not instance:
            return {
                "error": True,
                "messages": [
                    self.env._("No active Bonuscard connection is configured."),
                ],
            }

        formatted_items = self._prepare_checkout_items_for_api(checkout_items)
        if not formatted_items:
            return {
                "error": True,
                "messages": [self.env._("Invalid checkout payload from POS.")],
            }

        try:
            return self._finalize_purchase(
                instance,
                customer_identifier,
                transaction_identifier,
                formatted_items,
            )
        except BonuscardApiError as exc:
            message = self._get_bonuscard_error_message(
                exc, self.env._("Bonuscard finalization failed.")
            )
            return {
                "error": True,
                "messages": [message],
            }
        except Exception as exc:  # pylint: disable=broad-except
            if isinstance(exc, BonuscardHttpError):
                _logger.warning(
                    "Bonuscard HTTP error during POS finalize (HTTP %s) for partner %s",
                    exc.status_code,
                    partner.id,
                )
                message = self.env._("Bonuscard service is temporarily unavailable.")
            elif isinstance(exc, UserError):
                message = getattr(exc, "name", None) or str(exc)
            else:
                _logger.exception(
                    "Unexpected error during Bonuscard finalize for partner %s",
                    partner.id,
                )
                message = self.env._("Bonuscard finalization failed.")
            return {
                "error": True,
                "messages": [message],
            }

    def _cancel_purchase(self, instance, transaction_identifier):
        instance.ensure_one()
        return self._request(
            instance,
            endpoint="CancelPurchase",
            method="POST",
            payload={"transactionIdentifier": transaction_identifier},
        )

    @api.model
    def cancel_purchase_for_pos(self, transaction_identifier, partner_id=None):
        """Called from POS JS when a pending Bonuscard purchase is canceled.

        Args:
            transaction_identifier: str – transaction ID from ValidatePurchase
            partner_id: int or None – optional POS partner id to resolve the correct company
        """
        if not transaction_identifier:
            return {
                "error": True,
                "messages": [self.env._("Missing Bonuscard transaction identifier.")],
            }

        partner = (
            self.env["res.partner"].browse(partner_id).exists() if partner_id else None
        )
        company = (
            partner.commercial_partner_id.company_id if partner else self.env.company
        ) or self.env.company
        instance = self._get_company_instance(company)
        if not instance:
            return {
                "error": True,
                "messages": [
                    self.env._("No active Bonuscard connection is configured."),
                ],
            }

        try:
            return self._cancel_purchase(instance, transaction_identifier)
        except Exception as exc:  # pylint: disable=broad-except
            if isinstance(exc, BonuscardHttpError):
                _logger.warning(
                    "Bonuscard HTTP error during POS cancel (HTTP %s) for transaction %s",
                    exc.status_code,
                    transaction_identifier,
                )
                message = self.env._("Bonuscard service is temporarily unavailable.")
            elif isinstance(exc, UserError):
                message = getattr(exc, "name", None) or str(exc)
            else:
                _logger.exception(
                    "Unexpected error during Bonuscard cancel for transaction %s",
                    transaction_identifier,
                )
                message = self.env._("Bonuscard cancel failed.")
            return {"error": True, "messages": [message]}
