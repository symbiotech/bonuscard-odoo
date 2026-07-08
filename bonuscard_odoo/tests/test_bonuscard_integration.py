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

    def _create_product_with_barcode(self, barcode, name="Integration Product"):
        return self.env["product.product"].create(
            {
                "name": name,
                "barcode": barcode,
                "list_price": 10.0,
            }
        )

    def _create_product_without_barcode(self):
        return self.env["product.product"].create(
            {
                "name": "Non-Bonuscard Product (no barcode)",
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

    def _assert_customer_not_locked(self, partner, bonuscard_ean):
        """Validate a known Bonuscard-catalog product; error code 2 means still locked."""
        product = self._create_product_with_barcode(
            bonuscard_ean, name="Bonuscard Catalog Product"
        )
        result = self._validate_pos_order_line(
            partner, product, transaction_identifier=uuid.uuid4().hex
        )
        if result.get("errorCode") == 2:
            self.fail(
                "Customer is locked after the non-Bonuscard purchase flow: "
                f"{result.get('messages')}"
            )
        self.assertFalse(
            result.get("error"),
            f"Expected a successful Bonuscard validation: {result.get('messages')}",
        )
        transaction_id = result.get("transactionIdentifier")
        if transaction_id:
            cancel_result = self._cancel_transaction(transaction_id)
            self.assertFalse(
                cancel_result.get("error"),
                f"Cleanup cancel failed: {cancel_result.get('messages')}",
            )

    def _is_non_bonuscard_validate_result(self, result):
        """True when ValidatePurchase did not leave an open Bonuscard transaction."""
        if result.get("transactionIdentifier"):
            return False
        if result.get("error"):
            return True
        message = " ".join(result.get("messages") or []).lower()
        return "no valid products" in message or "cancelled" in message

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

    def test_non_bonuscard_product_purchase_does_not_lock_customer(self):
        """Buying outside the Bonuscard catalog must not lock the customer.

        Covers the POS scenario where a Bonuscard customer pays for products that
        are not on the Bonuscard API (no barcode/article number, or a barcode that
        the API rejects). The customer must still be able to validate a normal
        Bonuscard purchase afterwards.
        """
        recruitment_code = os.getenv("BONUSCARD_TEST_CONSUMER", "").strip()
        non_bonuscard_ean = os.getenv("BONUSCARD_TEST_NON_BONUSCARD_EAN", "").strip()
        bonuscard_ean = os.getenv("BONUSCARD_TEST_BONUSCARD_EAN", "").strip()
        if not recruitment_code:
            self.skipTest("Non-Bonuscard test skipped. Missing BONUSCARD_TEST_CONSUMER")
        if not bonuscard_ean:
            self.skipTest(
                "Non-Bonuscard test skipped. Missing BONUSCARD_TEST_BONUSCARD_EAN "
                "(a barcode on the Bonuscard API used to verify the customer is not locked)"
            )

        self._create_integration_instance()
        partner = self._create_partner_with_recruitment_code(recruitment_code)

        # Odoo products without barcode/article are never sent to ValidatePurchase.
        no_barcode_product = self._create_product_without_barcode()
        no_barcode_result = self._validate_pos_order_line(partner, no_barcode_product)
        self.assertTrue(
            no_barcode_result.get("error"),
            "Expected validation to stop before Bonuscard when no barcode is present",
        )
        self.assertFalse(
            no_barcode_result.get("transactionIdentifier"),
            "No Bonuscard transaction should be opened for products without barcode",
        )

        if non_bonuscard_ean:
            # Barcoded Odoo product whose EAN is not on the Bonuscard API.
            non_bonuscard_product = self._create_product_with_barcode(
                non_bonuscard_ean, name="Non-Bonuscard Product (unknown EAN)"
            )
            non_bonuscard_txn = uuid.uuid4().hex
            non_bonuscard_result = self._validate_pos_order_line(
                partner,
                non_bonuscard_product,
                transaction_identifier=non_bonuscard_txn,
            )
            if non_bonuscard_result.get("errorCode") == 2:
                self.skipTest(
                    "Sandbox customer is already locked. Wait for the open transaction to "
                    "expire or cancel it manually, then re-run this test."
                )
            self.assertTrue(
                self._is_non_bonuscard_validate_result(non_bonuscard_result),
                "Expected ValidatePurchase to reject a non-Bonuscard catalog EAN without "
                f"leaving a transaction open: {non_bonuscard_result}",
            )
            # Sandbox may report "transaction cancelled" while the customer lock
            # remains until CancelPurchase — mirror POS afterOrderValidation release.
            release_txn = (
                non_bonuscard_result.get("transactionIdentifier") or non_bonuscard_txn
            )
            cancel_result = self._cancel_transaction(release_txn)
            self.assertFalse(
                cancel_result.get("error"),
                f"Expected non-Bonuscard flow to release the customer lock: "
                f"{cancel_result.get('messages')}",
            )

        self._assert_customer_not_locked(partner, bonuscard_ean)
