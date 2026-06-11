from unittest.mock import patch

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
                "api_base_url": "https://web.bonuscard.com/api/",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service.validate_purchase(self.instance, "WLKT6", checkout_items)

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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service.validate_purchase(
                self.instance, "WLKT6", checkout_items, transaction_identifier="TX001"
            )

        sent_payload = mock_request.call_args.kwargs["payload"]
        self.assertEqual(sent_payload["transactionIdentifier"], "TX001")

    def test_validate_purchase_includes_codes(self):
        checkout_items = [{"ean": "8710255122465", "quantity": 1, "pricePerItem": 100}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.request",
            return_value={
                "error": False,
                "transactionIdentifier": "TX001",
                "totalDiscount": 0,
            },
        ) as mock_request:
            self.service.validate_purchase(
                self.instance, "WLKT6", checkout_items, codes=["SOMMAR2019"]
            )

        sent_payload = mock_request.call_args.kwargs["payload"]
        self.assertEqual(sent_payload["codes"], ["SOMMAR2019"])

    def test_validate_purchase_raises_on_api_error(self):
        checkout_items = [{"ean": "bad", "quantity": 1, "pricePerItem": 1}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.request",
            side_effect=UserError("Bonuscard API error (1): Customer not found."),
        ):
            with self.assertRaises(UserError):
                self.service.validate_purchase(self.instance, "UNKNOWN", checkout_items)

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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
        self.assertTrue(self.service.check_access_rights("read"))

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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
            side_effect=UserError("Bonuscard API unavailable"),
        ):
            result = self.service.validate_purchase_for_pos(partner.id, order_lines)

        self.assertTrue(result.get("error"))
        self.assertEqual(result.get("messages"), ["Bonuscard API unavailable"])

    def test_validate_purchase_for_pos_returns_generic_error_when_exception_has_no_message(
        self,
    ):
        partner = self._make_partner_with_code()
        product = self._make_product_with_barcode()
        order_lines = [{"product_id": product.id, "qty": 1, "price_unit": 10.0}]

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.validate_purchase",
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
