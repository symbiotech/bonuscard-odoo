from unittest.mock import patch

from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import (
    BonuscardApiError,
    BonuscardHttpError,
)
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardValidatePurchase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["bonuscard.api.service"]
        cls.instance = cls.env["bonuscard.connector.instance"].create(
            {
                "name": "Validate Test",
                "api_base_url": "https://example.invalid/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
            }
        )

    # ------------------------------------------------------------------
    # Low-level: validate_purchase()
    # ------------------------------------------------------------------

    def test_validate_purchase_sends_correct_payload(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 2, "pricePerItem": 299}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service._validate_purchase(self.instance, "WLKT6", checkout_items)

        mock_request.assert_called_once_with(
            self.instance,
            endpoint="ValidatePurchase",
            method="POST",
            payload={
                "customerIdentifier": "WLKT6",
                "checkoutItems": checkout_items,
            },
        )

    def test_validate_purchase_includes_transaction_identifier(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 1, "pricePerItem": 100}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service._validate_purchase(
                self.instance, "WLKT6", checkout_items, transaction_identifier="TX001"
            )

        sent_payload = mock_request.call_args.kwargs["payload"]
        self.assertEqual(sent_payload["transactionIdentifier"], "TX001")

    def test_validate_purchase_includes_codes(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 1, "pricePerItem": 100}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service._validate_purchase(
                self.instance, "WLKT6", checkout_items, codes=["SOMMAR2019"]
            )

        sent_payload = mock_request.call_args.kwargs["payload"]
        self.assertEqual(sent_payload["codes"], ["SOMMAR2019"])

    def test_validate_purchase_raises_on_api_error(self):
        checkout_items = [{"ean": "bad", "quantity": 1, "pricePerItem": 1}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            side_effect=UserError("Bonuscard API error (1): Customer not found."),
        ):
            with self.assertRaises(UserError):
                self.service._validate_purchase(
                    self.instance, "UNKNOWN", checkout_items
                )

    # ------------------------------------------------------------------
    # High-level: validate_purchase_for_pos()
    # ------------------------------------------------------------------

    def _make_partner_with_code(self, name="Test Customer", recruitment_code="WLKT6"):
        partner = self.env["res.partner"].create({"name": name})
        partner.write(
            {
                "bonuscard_recruitment_code": recruitment_code,
                "bonuscard_status": "linked",
            }
        )
        return partner

    def _make_product_with_barcode(self, barcode="8710255122465", name="Test Product"):
        return self.env["product.product"].create(
            {"name": name, "barcode": barcode, "available_in_pos": True}
        )

    def test_validate_purchase_for_pos_returns_result(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 2, "price_unit": 299.0}]
        api_response = {
            "error": False,
            "transactionIdentifier": "TX001",
            "totalDiscount": 149.5,
            "resultItems": [
                {
                    "description": "Discount",
                    "quantity": 1,
                    "pricePerItem": -149.5,
                }
            ],
        }

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value=api_response,
        ) as mock_validate:
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertFalse(result.get("error"))
        self.assertEqual(result["totalDiscount"], 149.5)
        mock_validate.assert_called_once_with(
            self.instance,
            "WLKT6",
            [{"ean": "8710255122465", "quantity": 2, "pricePerItem": 299.0}],
            transaction_identifier=None,
        )

    def test_bonuscard_api_service_allows_read_access_for_rpc(self):
        self.assertTrue(self.service.has_access("read"))

    def test_bonuscard_api_service_allows_read_access_for_pos_users(self):
        pos_group = self.env.ref("point_of_sale.group_pos_user")
        user = self.env["res.users"].create(
            {
                "name": "POS User",
                "login": "pos_user@example.com",
                "group_ids": [(6, 0, [pos_group.id])],
            }
        )
        self.assertTrue(self.service.with_user(user).has_access("read"))

    def test_bonuscard_api_service_denies_read_access_for_regular_users(self):
        user = self.env["res.users"].create(
            {"name": "Regular User", "login": "regular_user@example.com"}
        )
        self.assertFalse(self.service.with_user(user).has_access("read"))

    def test_validate_purchase_for_pos_uses_default_code_when_no_barcode(self):
        partner = self._make_partner_with_code()
        product = self.env["product.product"].create(
            {
                "name": "No Barcode Product",
                "default_code": "ART123",
                "available_in_pos": True,
            }
        )
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 50.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value={
                "error": False,
                "transactionIdentifier": "TX002",
                "totalDiscount": 0,
            },
        ) as mock_validate:
            self.service.validate_purchase_for_pos(partner.id, order_lines)

        sent_items = mock_validate.call_args.args[2]
        self.assertEqual(sent_items[0]["ean"], "ART123")

    def test_validate_purchase_for_pos_skips_lines_without_ean(self):
        partner = self._make_partner_with_code()
        product_ok = self._make_product_with_barcode("EAN001", "Has EAN")
        product_no_ean = self.env["product.product"].create(
            {"name": "No EAN", "available_in_pos": True}
        )
        order_lines = [
            {"product_id": product_ok.id, "qty": 1, "price_unit": 10.0},
            {"product_id": product_no_ean.id, "qty": 1, "price_unit": 20.0},
        ]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value={
                "error": False,
                "transactionIdentifier": "TX003",
                "totalDiscount": 0,
            },
        ) as mock_validate:
            self.service.validate_purchase_for_pos(partner.id, order_lines)

        sent_items = mock_validate.call_args.args[2]
        self.assertEqual(len(sent_items), 1)
        self.assertEqual(sent_items[0]["ean"], "EAN001")

    def test_validate_purchase_for_pos_error_when_no_recruitment_code(self):
        partner = self.env["res.partner"].create({"name": "No Code Partner"})
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))

    def test_validate_purchase_for_pos_error_when_no_instance(self):
        self.instance.active = False
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.instance.active = True

    def test_validate_purchase_for_pos_error_when_no_ean_products(self):
        partner = self._make_partner_with_code()
        product = self.env["product.product"].create(
            {"name": "No EAN", "available_in_pos": True}
        )
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))

    def test_validate_purchase_for_pos_passes_transaction_identifier(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value={
                "error": False,
                "transactionIdentifier": "TX-PREV",
                "totalDiscount": 0,
            },
        ) as mock_validate:
            self.service.validate_purchase_for_pos(
                partner.id, order_lines, transaction_identifier="TX-PREV"
            )

        self.assertEqual(
            mock_validate.call_args.kwargs["transaction_identifier"], "TX-PREV"
        )

    def test_validate_purchase_for_pos_returns_error_when_validate_purchase_raises(
        self,
    ):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            side_effect=UserError("Bonuscard API unavailable"),
        ):
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard API unavailable"])

    def test_validate_purchase_for_pos_handles_api_error_code_2(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            side_effect=BonuscardApiError(
                "Bonuscard API error (2): Locked to another transaction.",
                error_code=2,
            ),
        ):
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("errorCode"), 2)
        self.assertEqual(
            result.get("messages"),
            ["Customer is locked to an open transaction. Please try again or restart."],
        )

    def test_validate_purchase_for_pos_handles_api_error_code_4(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            side_effect=BonuscardApiError(
                "Bonuscard API error (4): Account verification required.",
                error_code=4,
            ),
        ):
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["Customer needs to verify their Bonuscard account before purchasing."],
        )

    def test_validate_purchase_for_pos_returns_generic_error_when_exception_has_no_message(
        self,
    ):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            side_effect=RuntimeError(),
        ):
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard validation failed."])

    def test_validate_purchase_for_pos_error_when_order_lines_payload_invalid(self):
        partner = self._make_partner_with_code()

        result = self.service.validate_purchase_for_pos(partner.id, order_lines=None)

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Invalid order payload from POS."])

    def test_validate_purchase_for_pos_ignores_non_dict_order_lines(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode("EAN-SAFE", "Safe Product")
        order_lines = [
            None,
            "bad",
            {"product_id": product.id, "qty": 1, "price_unit": 10.0},
        ]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value={
                "error": False,
                "transactionIdentifier": "TX-SAFE",
                "totalDiscount": 0,
            },
        ) as mock_validate:
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertFalse(result.get("error"))
        mock_validate.assert_called_once_with(
            self.instance,
            "WLKT6",
            [{"ean": "EAN-SAFE", "quantity": 1, "pricePerItem": 10.0}],
            transaction_identifier=None,
        )

    def test_finalize_purchase_sends_correct_payload(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 2, "pricePerItem": 299}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={"error": False, "transactionIdentifier": "TX001"},
        ) as mock_request:
            self.service._finalize_purchase(
                self.instance,
                "WLKT6",
                "TX001",
                checkout_items,
            )

        mock_request.assert_called_once_with(
            self.instance,
            endpoint="FinalizePurchase",
            method="POST",
            payload={
                "customerIdentifier": "WLKT6",
                "transactionIdentifier": "TX001",
                "checkoutItems": checkout_items,
            },
        )

    def test_finalize_purchase_includes_note(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 1, "pricePerItem": 100}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={"error": False, "transactionIdentifier": "TX001"},
        ) as mock_request:
            self.service._finalize_purchase(
                self.instance,
                "WLKT6",
                "TX001",
                checkout_items,
                note="POS payment completed",
            )

        mock_request.assert_called_once_with(
            self.instance,
            endpoint="FinalizePurchase",
            method="POST",
            payload={
                "customerIdentifier": "WLKT6",
                "transactionIdentifier": "TX001",
                "checkoutItems": checkout_items,
                "note": "POS payment completed",
            },
        )

    def test_finalize_purchase_for_pos_transforms_pos_order_lines(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 100.0}]
        api_response = {"error": False, "transactionIdentifier": "TX001"}

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._finalize_purchase",
            return_value=api_response,
        ) as mock_finalize:
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", order_lines
            )

        self.assertFalse(result.get("error"))
        mock_finalize.assert_called_once_with(
            self.instance,
            "WLKT6",
            "TX001",
            [{"ean": "8710255122465", "quantity": 1.0, "pricePerItem": 100.0}],
        )

    def test_finalize_purchase_for_pos_no_partner(self):
        result = self.service.finalize_purchase_for_pos(0, "TX001", [])

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Partner not found."])

    def test_finalize_purchase_for_pos_no_instance(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 100.0}]
        self.instance.active = False
        try:
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", order_lines
            )

            self.assertTrue(result.get("error"))
            self.assertEqual(
                result.get("messages"),
                ["No active Bonuscard connection is configured."],
            )
        finally:
            self.instance.active = True

    def test_cancel_purchase_sends_correct_payload(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._request",
            return_value={"error": False},
        ) as mock_request:
            self.service._cancel_purchase(self.instance, "TX001")

        mock_request.assert_called_once_with(
            self.instance,
            endpoint="CancelPurchase",
            method="POST",
            payload={"transactionIdentifier": "TX001"},
        )

    def test_cancel_purchase_for_pos_returns_result(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            return_value={"error": False},
        ) as mock_cancel:
            result = self.service.cancel_purchase_for_pos("TX001")

        self.assertFalse(result.get("error"))
        mock_cancel.assert_called_once_with(self.instance, "TX001")

    def test_cancel_purchase_for_pos_uses_session_company_instance(self):
        """POS RPC flows must resolve the connector by env.company (POS session)."""
        company = self.env["res.company"].create({"name": "Other Company"})
        partner = self.env["res.partner"].create(
            {
                "name": "Other Customer",
                "company_id": company.id,
                "bonuscard_recruitment_code": "WLKT6",
                "bonuscard_status": "linked",
            }
        )
        other_instance = self.env["bonuscard.connector.instance"].create(
            {
                "name": "Other Company Instance",
                "api_base_url": "https://example.invalid/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
                "company_id": company.id,
            }
        )

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            return_value={"error": False},
        ) as mock_cancel:
            result = self.service.with_company(company).cancel_purchase_for_pos(
                "TX001", partner.id
            )

        self.assertFalse(result.get("error"))
        mock_cancel.assert_called_once_with(other_instance, "TX001")

    def test_cancel_purchase_for_pos_returns_error_when_missing_transaction_identifier(
        self,
    ):
        result = self.service.cancel_purchase_for_pos(None)

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["Missing Bonuscard transaction identifier."],
        )

    def test_cancel_purchase_for_pos_returns_error_when_no_instance(self):
        self.instance.active = False
        result = self.service.cancel_purchase_for_pos("TX001")

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["No active Bonuscard connection is configured."],
        )
        self.instance.active = True

    def test_cancel_purchase_for_pos_returns_error_when_cancel_raises(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            side_effect=UserError("Bonuscard cancel failed"),
        ):
            result = self.service.cancel_purchase_for_pos("TX001")

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard cancel failed"])

    def test_cancel_purchase_for_pos_returns_service_unavailable_on_http_error(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            side_effect=BonuscardHttpError("HTTP error", status_code=503),
        ):
            result = self.service.cancel_purchase_for_pos("TX001")

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["Bonuscard service is temporarily unavailable."],
        )

    def test_cancel_purchase_for_pos_returns_generic_error_on_unexpected_exception(
        self,
    ):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = self.service.cancel_purchase_for_pos("TX001")

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard cancel failed."])

    def test_finalize_purchase_for_pos_returns_error_when_missing_transaction_identifier(
        self,
    ):
        partner = self._make_partner_with_code()
        result = self.service.finalize_purchase_for_pos(partner.id, None, [])

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["Missing Bonuscard transaction identifier."],
        )

    def test_finalize_purchase_for_pos_returns_error_when_finalize_raises(self):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._finalize_purchase",
            side_effect=UserError("Bonuscard API unavailable"),
        ):
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", order_lines
            )

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard API unavailable"])

    def test_finalize_purchase_for_pos_accepts_api_checkout_items(self):
        partner = self._make_partner_with_code()
        checkout_items = [
            {"ean": "8710255122465", "quantity": "1", "pricePerItem": "10"}
        ]
        api_response = {"error": False, "transactionIdentifier": "TX001"}

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._finalize_purchase",
            return_value=api_response,
        ) as mock_finalize:
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", checkout_items
            )

        self.assertFalse(result.get("error"))
        mock_finalize.assert_called_once_with(
            self.instance,
            "WLKT6",
            "TX001",
            [{"ean": "8710255122465", "quantity": 1.0, "pricePerItem": 10.0}],
        )

    def test_finalize_purchase_for_pos_handles_api_error_code_2(self):
        partner = self._make_partner_with_code()
        checkout_items = [
            {"ean": "8710255122465", "quantity": "1", "pricePerItem": "10"}
        ]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._finalize_purchase",
            side_effect=BonuscardApiError(
                "Bonuscard API error (2): Locked to another transaction.",
                error_code=2,
            ),
        ):
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", checkout_items
            )

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("errorCode"), 2)
        self.assertEqual(
            result.get("messages"),
            ["Customer is locked to an open transaction. Please try again or restart."],
        )

    def test_finalize_purchase_for_pos_handles_api_error_code_4(self):
        partner = self._make_partner_with_code()
        checkout_items = [
            {"ean": "8710255122465", "quantity": "1", "pricePerItem": "10"}
        ]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._finalize_purchase",
            side_effect=BonuscardApiError(
                "Bonuscard API error (4): Account verification required.",
                error_code=4,
            ),
        ):
            result = self.service.finalize_purchase_for_pos(
                partner.id, "TX001", checkout_items
            )

        self.assertTrue(result.get("error"))
        self.assertEqual(
            result.get("messages"),
            ["Customer needs to verify their Bonuscard account before purchasing."],
        )
