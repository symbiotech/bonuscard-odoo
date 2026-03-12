from unittest.mock import patch

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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.test_connection",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.test_connection",
            side_effect=UserError("Auth failed"),
        ):
            record.action_test_connection()

        self.assertEqual(record.connection_status, "error")
        self.assertEqual(record.last_error, "Auth failed")
