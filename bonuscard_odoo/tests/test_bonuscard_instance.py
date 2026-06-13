from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import BonuscardHttpError
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
            return_value={"reachable": True},
        ):
            record.action_test_connection()

        self.assertEqual(record.connection_status, "ok")
        self.assertFalse(record.last_error)
        self.assertTrue(record.last_test_at)

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
            record.action_test_connection()

        self.assertEqual(record.connection_status, "error")
        self.assertEqual(record.last_error, "Auth failed")

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

    def test_test_connection_returns_reachable_on_404(self):
        """test_connection returns {'reachable': True} when the server returns 404."""
        record = self.instance_model.create(
            {
                "name": "404 Reachable",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        http_err = HTTPError(
            url="https://web.bonuscard.com/api/",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=MagicMock(read=lambda: b""),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            result = service._test_connection(record)

        self.assertEqual(result, {"reachable": True})

    def test_test_connection_returns_reachable_on_405(self):
        """test_connection returns {'reachable': True} when the server returns 405."""
        record = self.instance_model.create(
            {
                "name": "405 Reachable",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )
        service = self.env["bonuscard.api.service"]

        http_err = HTTPError(
            url="https://web.bonuscard.com/api/",
            code=405,
            msg="Method Not Allowed",
            hdrs={},
            fp=MagicMock(read=lambda: b""),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            result = service._test_connection(record)

        self.assertEqual(result, {"reachable": True})

    def test_test_connection_reraises_other_http_errors(self):
        """test_connection re-raises BonuscardHttpError for status codes other than 404/405."""
        record = self.instance_model.create(
            {
                "name": "500 Error",
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
            fp=MagicMock(read=lambda: b""),
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.urlopen",
            side_effect=http_err,
        ):
            with self.assertRaises(BonuscardHttpError) as ctx:
                service._test_connection(record)

        self.assertEqual(ctx.exception.status_code, 500)

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
