import logging
import os
import uuid
from pathlib import Path
from unittest import SkipTest

from odoo.tests import TransactionCase, tagged

_logger = logging.getLogger(__name__)


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


# Manual-only integration tests (live Bonuscard API). These are skipped by default
# unless explicitly enabled via an environment flag.
@tagged("bonuscard_integration", "post_install", "-at_install")
class TestBonuscardIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _load_dotenv_if_present()

        if os.getenv("BONUSCARD_RUN_INTEGRATION_TESTS", "").strip() != "1":
            raise SkipTest(
                "Integration tests are disabled by default. Set BONUSCARD_RUN_INTEGRATION_TESTS=1 to enable."
            )

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

    def tearDown(self):
        super().tearDown()
        if getattr(self, "_bonuscard_touches_shared_customer", False):
            self._release_shared_customer_lock()

    def _mark_shared_customer_test(self):
        """Mark that this test may lock the shared sandbox consumer."""
        self._bonuscard_touches_shared_customer = True

    def _shared_consumer_recruitment_code(self):
        return os.getenv("BONUSCARD_TEST_CONSUMER", "").strip()

    def _shared_bonuscard_ean(self):
        return os.getenv("BONUSCARD_TEST_BONUSCARD_EAN", "").strip()

    def _release_shared_customer_lock(self):
        """Best-effort unlock for the shared sandbox consumer after a test."""
        consumer = self._shared_consumer_recruitment_code()
        unlock_ean = self._shared_bonuscard_ean()
        if not consumer or not unlock_ean:
            return
        instance = self._create_integration_instance()
        instance.write(
            {
                "catalog_probe_customer_identifier": consumer,
                "catalog_probe_price": 100.0,
            }
        )
        service = self.env["bonuscard.api.service"]
        if not service._release_probe_customer_lock(instance, unlock_ean):
            _logger.warning(
                "Could not release shared Bonuscard test customer lock after %s",
                self._testMethodName,
            )

    def _create_integration_instance(self):
        return self.env["bonuscard.connector.instance"].create(
            {
                "name": "Bonuscard Integration Test",
                "api_base_url": self.api_base_url,
                "api_username": self.api_username,
                "api_password": self.api_password,
                "api_culture": self.api_culture,
                "is_current": True,
            }
        )

    def _create_partner_with_recruitment_code(self, recruitment_code):
        partner = self.env["res.partner"].create(
            {"name": "Bonuscard Integration Customer"}
        )
        commercial = partner.commercial_partner_id
        commercial.write({"bonuscard_recruitment_code": recruitment_code})
        return partner

    def _create_product_with_barcode(
        self, barcode, name="Integration Product", in_catalog=True
    ):
        values = {
            "name": name,
            "barcode": barcode,
            "list_price": 10.0,
        }
        if in_catalog:
            values["bonuscard_catalog_status"] = "in_catalog"
        return self.env["product.product"].create(values)

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

    def test_01_non_bonuscard_product_purchase_does_not_lock_customer(self):
        """Non-catalog POS lines must not lock the Bonuscard customer.

        Covers the POS scenario where a Bonuscard customer pays for products that
        are not marked in the Bonuscard catalog. No ValidatePurchase call should
        be made, and the customer must still be able to validate a normal
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

        self._mark_shared_customer_test()
        self._create_integration_instance()
        partner = self._create_partner_with_recruitment_code(recruitment_code)

        # Odoo products without barcode/article are never sent to ValidatePurchase.
        no_barcode_product = self._create_product_without_barcode()
        no_barcode_result = self._validate_pos_order_line(partner, no_barcode_product)
        self.assertTrue(
            no_barcode_result.get("error"),
            "Expected validation to stop before Bonuscard when no catalog product is present",
        )
        self.assertFalse(
            no_barcode_result.get("transactionIdentifier"),
            "No Bonuscard transaction should be opened for non-catalog products",
        )

        if non_bonuscard_ean:
            non_bonuscard_product = self._create_product_with_barcode(
                non_bonuscard_ean,
                name="Non-Bonuscard Product (unknown EAN)",
                in_catalog=False,
            )
            non_bonuscard_result = self._validate_pos_order_line(
                partner,
                non_bonuscard_product,
                transaction_identifier=uuid.uuid4().hex,
            )
            self.assertTrue(
                non_bonuscard_result.get("error"),
                "Expected non-catalog products to be ignored by Bonuscard validation",
            )
            self.assertFalse(
                non_bonuscard_result.get("transactionIdentifier"),
                "No Bonuscard transaction should be opened for non-catalog products",
            )

        self._assert_customer_not_locked(partner, bonuscard_ean)

    def _create_probe_instance(self):
        probe_customer = self._shared_consumer_recruitment_code()
        if not probe_customer:
            self.skipTest(
                "Catalog probe integration test skipped. Missing "
                "BONUSCARD_TEST_CONSUMER"
            )
        self._mark_shared_customer_test()
        instance = self._create_integration_instance()
        instance.write(
            {
                "catalog_probe_customer_identifier": probe_customer,
                "catalog_probe_price": 100.0,
                "catalog_probe_batch_size": 10,
            }
        )
        unlock_ean = os.getenv("BONUSCARD_TEST_BONUSCARD_EAN", "").strip()
        if unlock_ean:
            instance.catalog_probe_unlock_ean = unlock_ean
        return instance

    def _create_probe_product(self, barcode, name):
        existing = self.env["product.product"].search(
            [("barcode", "=", barcode)], limit=1
        )
        if existing:
            existing.write(
                {
                    "bonuscard_catalog_status": "not_set",
                    "bonuscard_catalog_probe_note": False,
                }
            )
            return existing
        return self.env["product.product"].create(
            {
                "name": name,
                "barcode": barcode,
                "list_price": 10.0,
                "bonuscard_catalog_status": "not_set",
            }
        )

    def _cancel_open_probe_transaction(self, instance, transaction_identifier):
        if not transaction_identifier:
            return
        service = self.env["bonuscard.api.service"]
        try:
            service._cancel_purchase(instance, transaction_identifier)
        except Exception:  # pylint: disable=broad-except
            _logger.warning(
                "Could not cancel open probe transaction %s during test cleanup",
                transaction_identifier,
                exc_info=True,
            )

    def _validate_probe_purchase(
        self, instance, bonuscard_ean, transaction_identifier=None
    ):
        service = self.env["bonuscard.api.service"]
        customer = instance.catalog_probe_customer_identifier
        try:
            return service._validate_purchase(
                instance,
                customer,
                [{"ean": bonuscard_ean, "quantity": 1, "pricePerItem": 100.0}],
                transaction_identifier=transaction_identifier,
            )
        except Exception as exc:  # pylint: disable=broad-except
            from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import (
                BonuscardApiError,
            )

            if isinstance(exc, BonuscardApiError):
                return {
                    "error": True,
                    "errorCode": exc.error_code,
                    "messages": [getattr(exc, "name", None) or str(exc)],
                }
            raise

    def _ensure_probe_customer_unlocked(self, instance, bonuscard_ean):
        """Best-effort unlock before catalog probe tests."""
        payload = self._validate_probe_purchase(instance, bonuscard_ean)
        if payload.get("error"):
            if payload.get("errorCode") == 2:
                self.skipTest(
                    "Probe customer is locked before the test started. "
                    "Wait for the lock to expire or cancel the open transaction "
                    f"in Bonuscard. Messages: {payload.get('messages')}"
                )
            self.fail(
                f"Could not verify probe customer is unlocked: {payload.get('messages')}"
            )
        transaction_id = payload.get("transactionIdentifier")
        self._cancel_open_probe_transaction(instance, transaction_id)

    def _assert_probe_customer_unlocked(self, instance, bonuscard_ean):
        payload = self._validate_probe_purchase(instance, bonuscard_ean)
        if payload.get("errorCode") == 2:
            self.fail(
                "Probe customer is locked after catalog probe batch: "
                f"{payload.get('messages')}"
            )
        self.assertFalse(
            payload.get("error"),
            f"Probe customer validation failed after batch: {payload.get('messages')}",
        )
        self._cancel_open_probe_transaction(
            instance, payload.get("transactionIdentifier")
        )

    def test_90_catalog_probe_batch_does_not_lock_probe_customer(self):
        """Bulk catalog probe must complete without API error code 2 mid-batch."""
        bonuscard_ean = os.getenv("BONUSCARD_TEST_BONUSCARD_EAN", "").strip()
        non_bonuscard_ean = os.getenv("BONUSCARD_TEST_NON_BONUSCARD_EAN", "").strip()
        if not bonuscard_ean:
            self.skipTest(
                "Catalog probe batch test skipped. Missing BONUSCARD_TEST_BONUSCARD_EAN"
            )
        if not non_bonuscard_ean:
            self.skipTest(
                "Catalog probe batch test skipped. Missing "
                "BONUSCARD_TEST_NON_BONUSCARD_EAN"
            )

        instance = self._create_probe_instance()
        self._ensure_probe_customer_unlocked(instance, bonuscard_ean)

        products = self.env["product.product"]
        batch = products.browse(
            [
                self._create_probe_product(bonuscard_ean, "Probe Catalog Product A").id,
                self._create_probe_product(
                    non_bonuscard_ean, "Probe Unknown Product B"
                ).id,
                self._create_probe_product(
                    "8710000000002", "Probe Unknown Product C"
                ).id,
                self._create_probe_product(
                    "8710000000003", "Probe Unknown Product D"
                ).id,
                self._create_probe_product(
                    "8710000000004", "Probe Unknown Product E"
                ).id,
            ]
        )

        summary = products.action_bulk_probe_catalog_status(
            company_id=self.env.company.id,
            instance_id=instance.id,
            product_ids=batch.ids,
            only_unscanned=False,
        )

        lock_errors = []
        for product in batch:
            note = product.bonuscard_catalog_probe_note or ""
            if "error (2)" in note.lower() or "locked" in note.lower():
                lock_errors.append(f"{product.barcode}: {note}")

        self.assertFalse(
            lock_errors,
            "Catalog probe hit customer-lock errors:\n" + "\n".join(lock_errors),
        )
        self.assertEqual(
            summary.get("error"),
            0,
            f"Unexpected probe errors in summary: {summary}",
        )
        self.assertGreater(summary.get("processed"), 0)
        self._assert_probe_customer_unlocked(instance, bonuscard_ean)

    def test_91_catalog_probe_raw_validate_reuse_vs_cancel_per_product(self):
        """Document sandbox behavior for reused vs per-product-cancel probe flows."""
        bonuscard_ean = os.getenv("BONUSCARD_TEST_BONUSCARD_EAN", "").strip()
        non_bonuscard_ean = os.getenv("BONUSCARD_TEST_NON_BONUSCARD_EAN", "").strip()
        if not bonuscard_ean or not non_bonuscard_ean:
            self.skipTest(
                "Raw catalog probe sequence skipped. Missing BONUSCARD_TEST_* EAN vars"
            )

        instance = self._create_probe_instance()
        service = self.env["bonuscard.api.service"]
        customer = instance.catalog_probe_customer_identifier
        self._ensure_probe_customer_unlocked(instance, bonuscard_ean)

        def _validate(ean, transaction_identifier=None):
            try:
                return service._validate_purchase(
                    instance,
                    customer,
                    [{"ean": ean, "quantity": 1, "pricePerItem": 100.0}],
                    transaction_identifier=transaction_identifier,
                )
            except Exception as exc:  # pylint: disable=broad-except
                from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import (
                    BonuscardApiError,
                )

                if isinstance(exc, BonuscardApiError):
                    return {
                        "error": True,
                        "errorCode": exc.error_code,
                        "messages": [getattr(exc, "name", None) or str(exc)],
                    }
                raise

        # Strategy A: reusing transactionIdentifier fails on sandbox for unknown products.
        first = _validate(bonuscard_ean)
        self.assertFalse(first.get("error"), first.get("messages"))
        tx_id = first.get("transactionIdentifier")
        self.assertTrue(tx_id, "Expected a transaction identifier from first validate")

        second = _validate(non_bonuscard_ean, transaction_identifier=tx_id)
        if second.get("errorCode") == 2:
            self._cancel_open_probe_transaction(instance, tx_id)
            _logger.info(
                "Strategy A (reuse): sandbox returned error 2 as expected: %s",
                second.get("messages"),
            )
        else:
            third_tx = second.get("transactionIdentifier") or tx_id
            if second.get("transactionIdentifier") is None and (
                "no valid products" in " ".join(second.get("messages") or []).lower()
            ):
                third_tx = None

            third = _validate(bonuscard_ean, transaction_identifier=third_tx)
            if third.get("errorCode") == 2:
                self._cancel_open_probe_transaction(instance, third_tx or tx_id)
                self.fail(
                    "Reused-transaction probe failed on third product with error 2: "
                    f"{third.get('messages')}"
                )

            self._cancel_open_probe_transaction(
                instance, third.get("transactionIdentifier") or third_tx
            )

        # Strategy B: cancel after each single-item probe still locks after unknown-only.
        self._ensure_probe_customer_unlocked(instance, bonuscard_ean)
        legacy_first = _validate(bonuscard_ean)
        self.assertFalse(legacy_first.get("error"), legacy_first.get("messages"))
        legacy_tx = legacy_first.get("transactionIdentifier")
        self._cancel_open_probe_transaction(instance, legacy_tx)

        legacy_second = _validate(non_bonuscard_ean)
        if legacy_second.get("errorCode") == 2:
            self.fail(
                "Cancel-per-product probe failed on second product with error 2: "
                f"{legacy_second.get('messages')}"
            )
        self._cancel_open_probe_transaction(
            instance, legacy_second.get("transactionIdentifier")
        )
        self._assert_probe_customer_unlocked(instance, bonuscard_ean)
