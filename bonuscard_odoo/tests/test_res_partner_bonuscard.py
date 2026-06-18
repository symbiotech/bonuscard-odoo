from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResPartnerBonuscard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env["res.partner"]
        cls.instance = cls.env["bonuscard.connector.instance"].create(
            {
                "name": "Test Bonuscard",
                "api_base_url": "https://web.bonuscard.com/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )

    def test_refresh_bonuscard_status_links_single_match(self):
        partner = self.partner_model.create(
            {
                "name": "Test Testsson",
                "phone": "+46707654321",
                "email": "test.testsson@example.com",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 1,
                    "name": "Test Testsson",
                    "phoneNumber": "+46707654321",
                    "email": "test.testsson@example.com",
                    "recruitmentCode": "WLKT6",
                }
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "WLKT6")

    def test_refresh_bonuscard_status_marks_not_found(self):
        partner = self.partner_model.create(
            {
                "name": "Missing Customer",
                "phone": "+46709999999",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "not_found")
        self.assertFalse(partner.bonuscard_recruitment_code)

    def test_refresh_bonuscard_status_marks_ambiguous(self):
        partner = self.partner_model.create(
            {
                "name": "Test Testsson",
                "phone": "+46707654321",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {"id": 1, "name": "Test Testsson", "phoneNumber": "+46707654321"},
                {"id": 2, "name": "Test Testsson", "phoneNumber": "+46707654321"},
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "ambiguous")

    def test_get_bonuscard_status_for_pos_returns_serializable_payload(self):
        partner = self.partner_model.create(
            {
                "name": "POS Customer",
                "email": "pos@example.com",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 8,
                    "name": "POS Customer",
                    "email": "pos@example.com",
                    "recruitmentCode": "POS123",
                }
            ],
        ):
            result = self.partner_model.get_bonuscard_status_for_pos(partner.id)

        self.assertEqual(result["status"], "linked")
        self.assertEqual(result["recruitment_code"], "POS123")

    def test_refresh_bonuscard_status_links_by_mobile_when_both_phone_and_mobile_set(
        self,
    ):
        # Ensure this test only runs when the `mobile` field is available so it
        # truly verifies mobile-based matching rather than falling back to phone.
        if not self.partner_model._fields.get("mobile"):
            self.skipTest(
                "res.partner has no 'mobile' field; cannot test mobile-specific behavior."
            )

        partner_values = {
            "name": "Mobile Customer",
            "phone": "+46701111111",
            "mobile": "+46709876543",
            "email": "mobile@example.com",
        }
        matched_phone = partner_values["mobile"]

        partner = self.partner_model.create(partner_values)

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 42,
                    "name": "Mobile Customer",
                    "phoneNumber": matched_phone,
                    "email": "mobile@example.com",
                    "recruitmentCode": "MOB123",
                }
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "MOB123")

    def test_refresh_bonuscard_status_raises_if_no_instance(self):
        self.instance.active = False
        partner = self.partner_model.create(
            {"name": "No Instance", "email": "none@example.com"}
        )

        with self.assertRaises(UserError):
            partner.action_refresh_bonuscard_status()

        self.instance.active = True

    def test_register_to_bonuscard_links_customer(self):
        partner = self.partner_model.create(
            {
                "name": "Register Customer",
                "phone": "+46707654321",
            }
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
                return_value=[],
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._register_customer",
                return_value={
                    "customer": {
                        "id": 7,
                        "name": "Register Customer",
                        "phoneNumber": "+46707654321",
                        "recruitmentCode": "REG123",
                    }
                },
            ),
        ):
            action = partner.action_register_to_bonuscard()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "REG123")
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")
        self.assertIn("REG123", action["params"]["message"])

    def test_register_to_bonuscard_rechecks_before_registering_if_customer_already_exists(
        self,
    ):
        partner = self.partner_model.create(
            {
                "name": "Existing Bonuscard Customer",
                "phone": "+46707654321",
            }
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
                return_value=[
                    {
                        "id": 7,
                        "name": "Existing Bonuscard Customer",
                        "phoneNumber": "+46707654321",
                        "recruitmentCode": "REG123",
                    }
                ],
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._register_customer",
                side_effect=AssertionError(
                    "Register should not be called when the customer is already present."
                ),
            ),
        ):
            action = partner.action_register_to_bonuscard()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "REG123")
        self.assertEqual(action["params"]["type"], "info")
        self.assertIn("already registered", action["params"]["message"].lower())

    def test_register_to_bonuscard_raises_user_error_on_api_failure(self):
        partner = self.partner_model.create(
            {
                "name": "Register Error",
                "phone": "+46707654321",
            }
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
                return_value=[],
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._register_customer",
                return_value={
                    "error": True,
                    "messages": ["Already registered to Bonuscard."],
                },
            ),
        ):
            with self.assertRaises(UserError) as exc:
                partner.action_register_to_bonuscard()

        self.assertIn("Already registered to Bonuscard.", str(exc.exception))
        # When an exception is raised, the transaction rolls back, so status remains unchanged
        self.assertEqual(partner.bonuscard_status, "not_checked")
