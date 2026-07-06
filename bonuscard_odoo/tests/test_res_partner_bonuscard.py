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

    def test_refresh_bonuscard_status_does_not_link_on_name_only_when_contact_details_differ(
        self,
    ):
        partner = self.partner_model.create({"name": "John Smith"})

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 1,
                    "name": "John Smith",
                    "phoneNumber": "+46701111111",
                }
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "not_found")

    def test_refresh_bonuscard_status_links_on_name_when_no_contact_details_exist(self):
        partner = self.partner_model.create({"name": "Walk In Customer"})

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 2,
                    "name": "Walk In Customer",
                    "recruitmentCode": "WALK1",
                }
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "WALK1")

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

    def test_refresh_bonuscard_status_raises_if_no_instance(self):
        self.instance.active = False
        partner = self.partner_model.create(
            {"name": "No Instance", "email": "none@example.com"}
        )

        with self.assertRaises(UserError):
            partner.action_refresh_bonuscard_status()

        self.instance.active = True

    def test_clear_bonuscard_link_also_resets_company_when_phone_matches(self):
        """When a contact and its commercial partner share the same phone number they
        represent the same Bonuscard entity (phone is the unique identifier on the
        Bonuscard side).  Clearing the contact must therefore also clear the company so
        that stale 'linked' data cannot survive on the commercial partner record."""
        company = self.partner_model.create(
            {
                "name": "Company",
                "is_company": True,
                "phone": "+46707654321",
            }
        )
        company._write_bonuscard_status(
            "linked",
            customer={"recruitmentCode": "COMP123", "id": 1},
        )
        partner = self.partner_model.create(
            {
                "name": "Company Contact",
                "parent_id": company.id,
                "phone": "+46707654321",
            }
        )
        partner._write_bonuscard_status(
            "linked",
            customer={"recruitmentCode": "COMP123", "id": 1},
        )

        partner.action_clear_bonuscard_link()

        self.assertEqual(partner.bonuscard_status, "not_checked")
        self.assertFalse(partner.bonuscard_recruitment_code)
        self.assertEqual(company.bonuscard_status, "not_checked")
        self.assertFalse(company.bonuscard_recruitment_code)

    def test_clear_bonuscard_link_does_not_reset_company_when_phone_differs(self):
        """A contact with a different phone number is a distinct Bonuscard entity.
        Clearing the contact must not touch the commercial partner."""
        company = self.partner_model.create(
            {
                "name": "Company",
                "is_company": True,
                "phone": "+46700000001",
            }
        )
        company._write_bonuscard_status(
            "linked",
            customer={"recruitmentCode": "COMP999", "id": 2},
        )
        partner = self.partner_model.create(
            {
                "name": "Company Contact",
                "parent_id": company.id,
                "phone": "+46700000002",
            }
        )
        partner._write_bonuscard_status(
            "linked",
            customer={"recruitmentCode": "CONT999", "id": 3},
        )

        partner.action_clear_bonuscard_link()

        self.assertEqual(partner.bonuscard_status, "not_checked")
        # company must remain untouched
        self.assertEqual(company.bonuscard_status, "linked")
        self.assertEqual(company.bonuscard_recruitment_code, "COMP999")

    def test_refresh_bonuscard_status_also_updates_company_when_phone_matches(self):
        """Refreshing a contact must propagate the result to the commercial partner
        when both share the same phone (same Bonuscard entity)."""
        company = self.partner_model.create(
            {
                "name": "Company",
                "is_company": True,
                "phone": "+46707654321",
            }
        )
        partner = self.partner_model.create(
            {
                "name": "Company Contact",
                "parent_id": company.id,
                "phone": "+46707654321",
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 5,
                    "name": "Company Contact",
                    "phoneNumber": "+46707654321",
                    "recruitmentCode": "SHARED01",
                }
            ],
        ):
            partner.action_refresh_bonuscard_status()

        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "SHARED01")
        self.assertEqual(company.bonuscard_status, "linked")
        self.assertEqual(company.bonuscard_recruitment_code, "SHARED01")

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
        self.assertIn("an SMS", action["params"]["message"])

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

    def test_register_to_bonuscard_sanitizes_unexpected_exception(self):
        partner = self.partner_model.create(
            {
                "name": "Register Unexpected Error",
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
                side_effect=RuntimeError("secret internal error"),
            ),
        ):
            with self.assertRaises(UserError) as exc:
                partner.action_register_to_bonuscard()

        message = str(exc.exception)
        self.assertIn("Bonuscard registration failed", message)
        self.assertIn("Please try again or contact support", message)
        self.assertNotIn("secret internal error", message)
