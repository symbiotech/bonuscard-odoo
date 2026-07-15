from datetime import timedelta
from unittest.mock import patch

from odoo import fields
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
                "is_current": True,
            }
        )
        cls.pos_config = cls._create_test_pos_config()

    @classmethod
    def _create_test_pos_config(cls):
        company = cls.env.company
        journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", company.id)],
            limit=1,
        )
        if not journal:
            journal = cls.env["account.journal"].create(
                {
                    "name": "Bonuscard Test POS Sales",
                    "type": "sale",
                    "code": "BCPOS",
                    "company_id": company.id,
                }
            )
        payment_method = cls.env["pos.payment.method"].search(
            [("company_id", "in", [company.id, False])],
            limit=1,
        )
        if not payment_method:
            cash_journal = cls.env["account.journal"].search(
                [("type", "in", ["cash", "bank"]), ("company_id", "=", company.id)],
                limit=1,
            )
            if not cash_journal:
                cash_journal = cls.env["account.journal"].create(
                    {
                        "name": "Bonuscard Test POS Cash",
                        "type": "cash",
                        "code": "BPCSH",
                        "company_id": company.id,
                    }
                )
            payment_method = cls.env["pos.payment.method"].create(
                {
                    "name": "Bonuscard Test Cash",
                    "journal_id": cash_journal.id,
                }
            )
        return cls.env["pos.config"].create(
            {
                "name": "Bonuscard Test POS",
                "journal_id": journal.id,
                "payment_method_ids": [(6, 0, payment_method.ids)],
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
        instances = self.env["bonuscard.connector.instance"].search([])
        instances.write({"active": False})
        partner = self.partner_model.create(
            {"name": "No Instance", "email": "none@example.com"}
        )

        with self.assertRaises(UserError):
            partner.action_refresh_bonuscard_status()

        instances.write({"active": True})

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

    def test_bulk_prefetch_prefers_phone_then_email(self):
        self.instance.bulk_partner_prefetch_active = True
        self.instance.bulk_partner_prefetch_ttl_hours = 24
        self.instance.bulk_partner_prefetch_batch_size = 200
        self.instance.bulk_partner_prefetch_enable_name_fallback = False

        partner = self.partner_model.create(
            {
                "name": "Phone Miss Email Hit",
                "phone": "+46701234567",
                "email": "hit@example.com",
                "customer_rank": 1,
            }
        )

        def _search_side_effect(_self, _instance, query):
            # First call: normalized phone (digits-only)
            if query == "46701234567":
                return []
            # Second call: email (lowercased)
            if query == "hit@example.com":
                return [
                    {
                        "id": 10,
                        "name": "Phone Miss Email Hit",
                        "email": "hit@example.com",
                        "recruitmentCode": "EMAIL10",
                    }
                ]
            raise AssertionError(f"Unexpected query: {query}")

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            autospec=True,
            side_effect=_search_side_effect,
        ):
            summary = self.partner_model.action_bulk_prefetch_bonuscard_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                partner_ids=[partner.id],
            )

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["processed"], 1)
        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "EMAIL10")

    def test_bulk_prefetch_name_fallback_only_when_phone_email_missing(self):
        self.instance.bulk_partner_prefetch_active = True
        self.instance.bulk_partner_prefetch_ttl_hours = 24
        self.instance.bulk_partner_prefetch_batch_size = 200
        self.instance.bulk_partner_prefetch_enable_name_fallback = True

        partner = self.partner_model.create(
            {
                "name": "Walk In Customer",
                "customer_rank": 1,
            }
        )
        domain = self.partner_model._build_bulk_prefetch_domain(
            force_refresh=False,
            enable_name_fallback=True,
            cutoff=fields.Datetime.now(),
        )
        self.assertIn(partner, self.partner_model.search(domain))

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {"id": 2, "name": "Walk In Customer", "recruitmentCode": "WALK1"}
            ],
        ) as mocked:
            summary = self.partner_model.action_bulk_prefetch_bonuscard_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                partner_ids=[partner.id],
            )

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["processed"], 1)
        self.assertEqual(mocked.call_args.args[-1], "Walk In Customer")
        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(partner.bonuscard_recruitment_code, "WALK1")

    def test_bulk_prefetch_skips_recently_synced_by_ttl(self):
        self.instance.bulk_partner_prefetch_active = True
        self.instance.bulk_partner_prefetch_ttl_hours = 24
        self.instance.bulk_partner_prefetch_batch_size = 200

        partner = self.partner_model.create(
            {
                "name": "Recently Synced",
                "phone": "+46701230000",
                "customer_rank": 1,
            }
        )
        partner._write_bonuscard_status("not_found", note="recent")

        cutoff = fields.Datetime.now() - timedelta(hours=24)
        domain = self.partner_model._build_bulk_prefetch_domain(
            force_refresh=True,
            enable_name_fallback=False,
            cutoff=cutoff,
        )
        self.assertNotIn(partner, self.partner_model.search(domain))

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            side_effect=AssertionError("Should not call API when within TTL."),
        ):
            with patch(
                "odoo.addons.bonuscard_odoo.models.res_partner.ResPartner._sync_bonuscard_status_for_bulk_prefetch",
                autospec=True,
            ) as mock_sync:
                summary = self.partner_model.action_bulk_prefetch_bonuscard_status(
                    company_id=self.env.company.id,
                    instance_id=self.instance.id,
                    partner_ids=[partner.id],
                    force_refresh=True,
                )

        self.assertTrue(summary["ok"])
        synced_partner_ids = {
            call.args[0].id for call in mock_sync.call_args_list if call.args
        }
        self.assertNotIn(partner.id, synced_partner_ids)

    def test_import_partner_from_bonuscard_for_pos_creates_partner(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 55,
                    "name": "Imported Customer",
                    "phoneNumber": "+46701239999",
                    "email": "import@example.com",
                    "recruitmentCode": "IMP55",
                }
            ],
        ):
            result = self.partner_model.import_partner_from_bonuscard_for_pos(
                self.pos_config.id, "IMP55"
            )

        partner = self.partner_model.search(
            [("bonuscard_recruitment_code", "=", "IMP55")]
        )
        self.assertEqual(len(partner), 1)
        self.assertEqual(partner.name, "Imported Customer")
        self.assertEqual(partner.bonuscard_status, "linked")
        self.assertEqual(result["res.partner"][0]["id"], partner.id)

    def test_import_partner_from_bonuscard_for_pos_links_existing_partner(self):
        partner = self.partner_model.create(
            {
                "name": "Existing Customer",
                "phone": "+46707654321",
                "customer_rank": 1,
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {
                    "id": 56,
                    "name": "Existing Customer",
                    "phoneNumber": "+46707654321",
                    "recruitmentCode": "LINK56",
                }
            ],
        ):
            result = self.partner_model.import_partner_from_bonuscard_for_pos(
                self.pos_config.id, "LINK56"
            )

        self.assertEqual(result["res.partner"][0]["id"], partner.id)
        self.assertEqual(partner.bonuscard_recruitment_code, "LINK56")
        self.assertEqual(partner.bonuscard_status, "linked")

    def test_import_partner_from_bonuscard_for_pos_rejects_ambiguous_matches(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._search_customers",
            return_value=[
                {"id": 1, "name": "A", "recruitmentCode": "AAA1"},
                {"id": 2, "name": "B", "recruitmentCode": "BBB2"},
            ],
        ):
            with self.assertRaises(UserError) as exc:
                self.partner_model.import_partner_from_bonuscard_for_pos(
                    self.pos_config.id, "customer"
                )

        self.assertIn("multiple", str(exc.exception).lower())
