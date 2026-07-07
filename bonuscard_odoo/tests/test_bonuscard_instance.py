from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request

from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import (
    _CONNECTION_TEST_PROBE_QUERY,
    BonuscardHttpError,
)
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardInstance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.instance_model = cls.env["bonuscard.connector.instance"]

    def test_create_connection(self):
        record = self.instance_model.create(
            {
                "name": "Test Bonuscard",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        self.assertEqual(record.connection_status, "unknown")
        self.assertEqual(record.api_culture, "en-GB")

    def test_build_basic_auth_header(self):
        record = self.instance_model.create(
            {
                "name": "Header Test",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )

        headers = record._build_headers()
        self.assertEqual(headers["Authorization"], "Basic ZGVtby11c2VyOmRlbW8tcGFzcw==")
        self.assertEqual(headers["BC-Culture"], "en-GB")

    def test_reject_invalid_base_url(self):
        with self.assertRaises(ValidationError):
            self.instance_model.create(
                {
                    "name": "Invalid URL",
                    "api_base_url": "web.bonuscard.com/api",
                    "api_username": "demo-user",
                    "api_password": "demo-pass",
                }
            )

    def test_action_test_connection_marks_status_ok(self):
        record = self.instance_model.create(
            {
                "name": "Connection OK",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._test_connection",
            return_value={"ok": True},
        ):
            action = record.action_test_connection()

        self.assertEqual(record.connection_status, "ok")
        self.assertFalse(record.last_error)
        self.assertTrue(record.last_test_at)
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")

    def test_action_test_connection_marks_status_error(self):
        record = self.instance_model.create(
            {
                "name": "Connection Error",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._test_connection",
            side_effect=UserError("Auth failed"),
        ):
            action = record.action_test_connection()

        self.assertEqual(record.connection_status, "error")
        self.assertEqual(record.last_error, "Auth failed")
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "danger")
        self.assertEqual(action["params"]["message"], "Auth failed")
        self.assertTrue(action["params"]["sticky"])

    # ------------------------------------------------------------------
    # BonuscardHttpError – custom exception carries the HTTP status code
    # ------------------------------------------------------------------

    def test_bonuscard_http_error_is_user_error(self):
        """BonuscardHttpError must be a subtype of UserError for backward compat."""
        err = BonuscardHttpError("Not Found", status_code=404)
        self.assertIsInstance(err, UserError)
        self.assertEqual(err.status_code, 404)

    def test_request_raises_bonuscard_http_error_on_http_failure(self):
        """request() wraps non-auth HTTPError in BonuscardHttpError with status code."""
        record = self.instance_model.create(
            {
                "name": "HTTP Error Test",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        http_err = HTTPError(
            url="https://web.bonuscard.com/api/",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=MagicMock(read=lambda: b"server error"),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            with self.assertRaises(BonuscardHttpError) as ctx:
                service._request(record)

        self.assertEqual(ctx.exception.status_code, 500)

    def test_test_connection_succeeds_with_authenticated_search(self):
        """test_connection succeeds when SearchCustomers accepts the credentials."""
        record = self.instance_model.create(
            {
                "name": "Auth OK",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={"customers": [], "error": False},
        ) as request_mock:
            result = service._test_connection(record)

        self.assertEqual(result, {"ok": True})
        request_mock.assert_called_once_with(
            record,
            endpoint="SearchCustomers",
            method="GET",
            params={"query": _CONNECTION_TEST_PROBE_QUERY},
        )

    def test_test_connection_raises_user_error_on_auth_failure(self):
        """test_connection fails when SearchCustomers rejects the credentials."""
        record = self.instance_model.create(
            {
                "name": "Auth Failed",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        http_err = HTTPError(
            url=f"https://web.bonuscard.com/api/SearchCustomers?query={_CONNECTION_TEST_PROBE_QUERY}",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b""),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            with self.assertRaises(UserError) as ctx:
                service._test_connection(record)

        self.assertIn("authentication failed", str(ctx.exception).lower())

    def test_action_test_connection_marks_error_on_bogus_credentials(self):
        """End-to-end: bogus credentials must not report connection_status=ok."""
        record = self.instance_model.create(
            {
                "name": "Bogus Credentials",
                "api_base_url": "https://test.bonuscard.com/api/",
                "api_username": "bogus-user",
                "api_password": "bogus-pass",
            }
        )

        http_err = HTTPError(
            url=f"https://test.bonuscard.com/api/SearchCustomers?query={_CONNECTION_TEST_PROBE_QUERY}",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b""),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            action = record.action_test_connection()

        self.assertEqual(record.connection_status, "error")
        self.assertIn("authentication failed", (record.last_error or "").lower())
        self.assertEqual(action["params"]["type"], "danger")
        self.assertIn("authentication failed", action["params"]["message"].lower())

    def test_search_customers_uses_query_params(self):
        record = self.instance_model.create(
            {
                "name": "Search Customers",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={"customers": [{"id": 1, "recruitmentCode": "WLKT6"}]},
        ) as request_mock:
            customers = service._search_customers(record, "0707654321")

        self.assertEqual(customers, [{"id": 1, "recruitmentCode": "WLKT6"}])
        request_mock.assert_called_once_with(
            record,
            endpoint="SearchCustomers",
            method="GET",
            params={"query": "0707654321"},
        )

    def test_request_converts_timeout_to_user_error(self):
        record = self.instance_model.create(
            {
                "name": "Timeout Error",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
                side_effect=TimeoutError("timed out"),
            ),
            self.assertRaises(UserError) as ctx,
        ):
            service._request(record)

        self.assertIn("Bonuscard API connection error", str(ctx.exception))

    def test_request_retries_on_transient_timeout_and_succeeds(self):
        record = self.instance_model.create(
            {
                "name": "Retry Timeout",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        response = MagicMock()
        response.read.return_value = b'{"success": true}'
        urlopen_context = MagicMock()
        urlopen_context.__enter__.return_value = response
        urlopen_context.__exit__.return_value = False

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
                side_effect=[TimeoutError("timed out"), urlopen_context],
            ),
            patch("odoo.addons.bonuscard_odoo.models.bonuscard_api_service.time.sleep"),
        ):
            result = service._request(record)

        self.assertEqual(result, {"success": True})

    def test_request_rebuilds_request_object_on_http_retry(self):
        """Each retry builds a fresh Request so POST body is not consumed."""
        record = self.instance_model.create(
            {
                "name": "Retry HTTP",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]
        payload = {"transactionIdentifier": "tx-123"}

        response = MagicMock()
        response.read.return_value = b'{"success": true}'
        urlopen_context = MagicMock()
        urlopen_context.__enter__.return_value = response
        urlopen_context.__exit__.return_value = False

        http_err = HTTPError(
            url="https://web.bonuscard.com/api/CancelPurchase",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=MagicMock(read=lambda: b""),
        )

        requests_created = []

        def track_request(*args, **kwargs):
            req = Request(*args, **kwargs)
            requests_created.append(req)
            return req

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.Request",
                side_effect=track_request,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
                side_effect=[http_err, urlopen_context],
            ) as mock_urlopen,
            patch("odoo.addons.bonuscard_odoo.models.bonuscard_api_service.time.sleep"),
        ):
            result = service._request(
                record,
                endpoint="CancelPurchase",
                method="POST",
                payload=payload,
            )

        self.assertEqual(result, {"success": True})
        self.assertEqual(len(requests_created), 2)
        self.assertIsNot(requests_created[0], requests_created[1])
        self.assertEqual(mock_urlopen.call_count, 2)
