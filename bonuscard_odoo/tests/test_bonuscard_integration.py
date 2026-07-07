import os
import uuid
from pathlib import Path
from unittest import SkipTest

from odoo.tests import TransactionCase, tagged


def _load_dotenv_if_present():
    """Load simple KEY=VALUE pairs from .env if env vars are not already set."""
    candidate_paths = [
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    dotenv_path = next((path for path in candidate_paths if path.exists()), None)
    if not dotenv_path:
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@tagged("bonuscard_integration", "post_install", "-at_install")
class TestBonuscardIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _load_dotenv_if_present()

        cls.api_base_url = os.getenv("BONUSCARD_TEST_API_BASE_URL", "").strip()
        cls.api_username = os.getenv("BONUSCARD_TEST_USERNAME", "").strip()
        cls.api_password = os.getenv("BONUSCARD_TEST_PASSWORD", "").strip()
        cls.api_culture = (
            os.getenv("BONUSCARD_TEST_CULTURE", "en-GB").strip() or "en-GB"
        )

        missing_vars = [
            name
            for name, value in [
                ("BONUSCARD_TEST_API_BASE_URL", cls.api_base_url),
                ("BONUSCARD_TEST_USERNAME", cls.api_username),
                ("BONUSCARD_TEST_PASSWORD", cls.api_password),
            ]
            if not value
        ]
        if missing_vars:
            raise SkipTest(
                f"Integration test skipped. Missing variables: {', '.join(missing_vars)}"
            )

    def _create_integration_instance(self):
        return self.env["bonuscard.connector.instance"].create(
            {
                "name": "Bonuscard Integration Test",
                "api_base_url": self.api_base_url,
                "api_username": self.api_username,
                "api_password": self.api_password,
                "api_culture": self.api_culture,
            }
        )

    def _create_partner_with_recruitment_code(self, recruitment_code):
        partner = self.env["res.partner"].create(
            {"name": "Bonuscard Integration Customer"}
        )
        commercial = partner.commercial_partner_id
        commercial.write({"bonuscard_recruitment_code": recruitment_code})
        return partner

    def _create_product_with_barcode(self, barcode):
        return self.env["product.product"].create(
            {
                "name": "Non-Bonuscard Integration Product",
                "barcode": barcode,
                "list_price": 10.0,
            }
        )

    def _validate_pos_order_line(self, partner, product, transaction_identifier=None):
        service = self.env["bonuscard.api.service"]
        return service.validate_purchase_for_pos(
            partner.id,
            [{"product_id": product.id, "qty": 1, "price_unit": 10.0}],
            transaction_identifier=transaction_identifier,
        )

    def _cancel_transaction(self, transaction_identifier):
        service = self.env["bonuscard.api.service"]
        return service.cancel_purchase_for_pos(transaction_identifier)

    def test_live_test_connection_with_env_credentials(self):
        instance = self._create_integration_instance()
        instance.action_test_connection()
        self.assertEqual(instance.connection_status, "ok")

    def test_register_customer_with_phone_number(self):
        """Test RegisterCustomer endpoint with a valid phone number."""
        instance = self._create_integration_instance()
        service = self.env["bonuscard.api.service"]
        phone_number = os.getenv("BONUSCARD_TEST_PHONE_FOR_REGISTRATION", "").strip()
        if not phone_number:
            self.skipTest(
                "RegisterCustomer test skipped. Missing BONUSCARD_TEST_PHONE_FOR_REGISTRATION"
            )

        result = service._register_customer(instance, phone_number=phone_number)
        self.assertFalse(result.get("error"), f"API error: {result.get('messages')}")
        self.assertIn("customer", result)
        self.assertIn("phoneNumber", result["customer"])
        self.assertIn("recruitmentCode", result["customer"])

    def test_cancel_purchase_releases_zero_discount_validate_lock(self):
        """CancelPurchase must release a zero-discount ValidatePurchase lock.

        Products on the Bonuscard API can validate with totalDiscount=0 while
        still needing FinalizePurchase to register the sale (e.g. accumulation
        programs). This test verifies CancelPurchase clears the customer lock
        when a pending transaction must be aborted instead of finalized.
        """
        recruitment_code = os.getenv("BONUSCARD_TEST_CONSUMER", "").strip()
        zero_discount_ean = (
            os.getenv("BONUSCARD_TEST_ZERO_DISCOUNT_EAN", "").strip()
            or os.getenv("BONUSCARD_TEST_NON_BONUSCARD_EAN", "").strip()
        )
        if not recruitment_code:
            self.skipTest(
                "Zero-discount lock test skipped. Missing BONUSCARD_TEST_CONSUMER"
            )
        if not zero_discount_ean:
            self.skipTest(
                "Zero-discount lock test skipped. Missing BONUSCARD_TEST_ZERO_DISCOUNT_EAN"
            )

        self._create_integration_instance()
        partner = self._create_partner_with_recruitment_code(recruitment_code)
        product = self._create_product_with_barcode(zero_discount_ean)
        first_tx = uuid.uuid4().hex

        first_validate = self._validate_pos_order_line(
            partner, product, transaction_identifier=first_tx
        )
        if first_validate.get("errorCode") == 2:
            self.skipTest(
                "Sandbox customer is already locked. Wait for the open transaction to "
                "expire or cancel it manually, then re-run this test."
            )
        self.assertFalse(
            first_validate.get("error"),
            f"Initial validate failed: {first_validate.get('messages')} ({first_validate})",
        )
        transaction_id = first_validate.get("transactionIdentifier") or first_tx
        cleanup_tx = None
        try:
            self.assertEqual(
                float(first_validate.get("totalDiscount") or 0),
                0.0,
                f"Expected a zero-discount validation for {zero_discount_ean}: {first_validate}",
            )

            # A second validation for the same customer without releasing the first
            # transaction reproduces the customer-lock failure seen in POS.
            second_validate = self._validate_pos_order_line(
                partner,
                product,
                transaction_identifier=uuid.uuid4().hex,
            )
            self.assertTrue(
                second_validate.get("error"),
                "Expected a lock error while the first transaction remains open",
            )
            self.assertEqual(
                second_validate.get("errorCode"),
                2,
                f"Expected Bonuscard error code 2, got: {second_validate.get('messages')}",
            )

            cancel_result = self._cancel_transaction(transaction_id)
            self.assertFalse(
                cancel_result.get("error"),
                f"CancelPurchase failed: {cancel_result.get('messages')}",
            )

            third_validate = self._validate_pos_order_line(
                partner, product, transaction_identifier=uuid.uuid4().hex
            )
            self.assertFalse(
                third_validate.get("error"),
                f"Customer still locked after cancel: {third_validate.get('messages')}",
            )
            self.assertNotEqual(
                third_validate.get("errorCode"),
                2,
                "Customer lock error persisted after cancel",
            )

            cleanup_tx = third_validate.get("transactionIdentifier")
        finally:
            for tx in {transaction_id, cleanup_tx}:
                if tx:
                    self._cancel_transaction(tx)
