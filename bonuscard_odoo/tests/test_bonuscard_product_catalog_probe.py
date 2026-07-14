from unittest.mock import patch

from odoo.addons.bonuscard_odoo.models.bonuscard_api_service import BonuscardApiError
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardProductCatalogProbe(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["bonuscard.api.service"]
        cls.manager_group = cls.env.ref("bonuscard_odoo.bonuscard_odoo_group_manager")
        cls.env.user.write({"group_ids": [(4, cls.manager_group.id)]})
        cls.instance = cls.env["bonuscard.connector.instance"].create(
            {
                "name": "Catalog Probe Test",
                "api_base_url": "https://example.invalid/api/",
                "api_username": "demo-user",
                "api_password": "demo-pass",
                "is_current": True,
                "catalog_probe_customer_identifier": "PROBE01",
                "catalog_probe_price": 100.0,
            }
        )

    def _create_product(self, **values):
        defaults = {
            "name": "Probe Test Product",
            "list_price": 10.0,
            "available_in_pos": True,
        }
        defaults.update(values)
        product = (
            self.env["product.product"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(defaults)
        )
        return self.env["product.product"].browse(product.ids)

    def _recognized_checkout_response(self, ean, transaction_id="TX001", messages=None):
        return {
            "error": False,
            "transactionIdentifier": transaction_id,
            "messages": messages or ["Product recognized."],
            "checkoutItems": [
                {
                    "ean": ean,
                    "identifier": "1",
                    "description": "Catalog product",
                }
            ],
        }

    def test_classify_not_in_catalog_without_transaction(self):
        status, note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            }
        )
        self.assertEqual(status, "not_in_catalog")
        self.assertIn("No valid products", note)

    def test_classify_transaction_only_is_not_in_catalog(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TX001",
                "messages": ["Discount available."],
            },
            probe_ean="8710000009001",
        )
        self.assertEqual(status, "not_in_catalog")

    def test_classify_in_catalog_requires_confirmed_probe_checkout_item(self):
        status, _note = self.service._classify_catalog_probe_response(
            self._recognized_checkout_response("8710000009001", "TXCONF1"),
            probe_ean="8710000009001",
        )
        self.assertEqual(status, "in_catalog")

    def test_classify_transaction_without_confirmed_probe_is_not_in_catalog(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TXECHO1",
                "messages": ["Transaction opened."],
                "checkoutItems": [{"ean": "8710000009002", "quantity": 1}],
            },
            probe_ean="8710000009002",
        )
        self.assertEqual(status, "not_in_catalog")

    def test_classify_anchor_echoed_probe_without_metadata_is_not_in_catalog(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TXECHO2",
                "messages": ["Discount applied."],
                "checkoutItems": [
                    {
                        "ean": "8710000009021",
                        "identifier": "9",
                        "description": "Known anchor product",
                    },
                    {"ean": "8710000009022", "quantity": 1, "pricePerItem": 100.0},
                ],
            },
            probe_ean="8710000009022",
            anchor_ean="8710000009021",
        )
        self.assertEqual(status, "not_in_catalog")

    def test_classify_anchor_only_uses_catalog_note_not_loyalty_message(self):
        status, note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TXANCHOR",
                "messages": [
                    "Created a new card of the type 'KRAFFT bonuskort' and added one purchase."
                ],
                "checkoutItems": [
                    {
                        "ean": "8710000009021",
                        "identifier": "9",
                        "description": "Known anchor product",
                    }
                ],
            },
            probe_ean="8710000009022",
            anchor_ean="8710000009021",
        )
        self.assertEqual(status, "not_in_catalog")
        self.assertIn("not found", note.lower())
        self.assertNotIn("bonuskort", note.lower())

    def test_classify_ambiguous_response_leaves_unchanged(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "messages": ["Something unexpected happened."],
            }
        )
        self.assertEqual(status, "unchanged")

    def test_classify_api_error_returns_error(self):
        status, note = self.service._classify_catalog_probe_response(
            {
                "error": True,
                "errorCode": 4,
                "messages": ["Customer not eligible."],
            }
        )
        self.assertEqual(status, "error")
        self.assertIn("Customer not eligible", note)

    def test_classify_anchor_ignores_result_items(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TXANCHOR",
                "messages": ["Discount applied."],
                "checkoutItems": [
                    {
                        "ean": "8710000009021",
                        "identifier": "9",
                        "description": "Known anchor product",
                    }
                ],
                "resultItems": [{"ean": "8710000009022"}],
            },
            probe_ean="8710000009022",
            anchor_ean="8710000009021",
        )
        self.assertEqual(status, "not_in_catalog")

    def test_probe_known_product_cancels_transaction(self):
        product = self._create_product(barcode="8710000009001")
        validate_payload = self._recognized_checkout_response(
            "8710000009001", "TXPROBE1"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ) as mock_validate,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ) as mock_cancel,
        ):
            result = self.service.probe_product_catalog_status(self.instance, product)

        self.assertEqual(result["status"], "in_catalog")
        self.assertIsNone(result["transaction_identifier"])
        mock_validate.assert_called_once()
        sent_items = mock_validate.call_args.args[2]
        self.assertEqual(
            sent_items,
            [{"ean": "8710000009001", "quantity": 1, "pricePerItem": 100.0}],
        )
        self.assertIsNone(mock_validate.call_args.kwargs.get("transaction_identifier"))
        mock_cancel.assert_called_once_with(self.instance, "TXPROBE1")

    def test_probe_batch_cancels_each_open_transaction(self):
        products = [
            self._create_product(barcode="8710000009014"),
            self._create_product(barcode="8710000009015"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009014", "TXBATCH1"),
            self._recognized_checkout_response("8710000009015", "TXBATCH2"),
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ) as mock_validate,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ) as mock_cancel,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["in_catalog"], 2)
        self.assertEqual(products[0].bonuscard_catalog_status, "in_catalog")
        self.assertEqual(products[1].bonuscard_catalog_status, "in_catalog")
        self.assertEqual(mock_validate.call_count, 2)
        self.assertIsNone(
            mock_validate.call_args_list[0].kwargs.get("transaction_identifier")
        )
        self.assertIsNone(
            mock_validate.call_args_list[1].kwargs.get("transaction_identifier")
        )
        self.assertEqual(mock_cancel.call_count, 2)
        mock_cancel.assert_any_call(self.instance, "TXBATCH1")
        mock_cancel.assert_any_call(self.instance, "TXBATCH2")

    def test_probe_batch_skips_cancel_when_bonuscard_cancels_transaction(self):
        products = [
            self._create_product(barcode="8710000009016"),
            self._create_product(barcode="8710000009017"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009016", "TXBATCH2"),
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ) as mock_validate,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ) as mock_cancel,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
                return_value=True,
            ) as mock_release,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["in_catalog"], 1)
        self.assertEqual(summary["not_in_catalog"], 1)
        self.assertEqual(mock_validate.call_count, 2)
        self.assertIsNone(
            mock_validate.call_args_list[1].kwargs.get("transaction_identifier")
        )
        mock_cancel.assert_called_once_with(self.instance, "TXBATCH2")
        mock_release.assert_called_once_with(self.instance, "8710000009016")

    def test_probe_batch_unlock_failure_does_not_double_count(self):
        products = [
            self._create_product(barcode="8710000009016"),
            self._create_product(barcode="8710000009017"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009016", "TXBATCH2"),
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
                side_effect=BonuscardApiError("Unlock failed", error_code=4),
            ),
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["in_catalog"], 1)
        self.assertEqual(summary["not_in_catalog"], 1)
        self.assertEqual(summary["error"], 0)
        self.assertIn("unlock raised an error", summary.get("message", ""))

    def test_probe_batch_unlock_false_result_surfaces_summary_warning(self):
        products = [
            self._create_product(barcode="8710000009030"),
            self._create_product(barcode="8710000009031"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009030", "TXUNLOCK3"),
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
                return_value=False,
            ),
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 2)
        self.assertIn("could not confirm", summary.get("message", "").lower())

    def test_bulk_probe_skips_unlock_release_on_error_status(self):
        product = self._create_product(barcode="8710000009050")
        validate_payload = self._recognized_checkout_response(
            "8710000009050", "TXERROR1"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=UserError("Cancel failed."),
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
            ) as mock_release,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["error"], 1)
        mock_release.assert_not_called()

    def test_bulk_probe_warns_when_no_unlock_ean_after_unknown_product(self):
        product = self._create_product(barcode="8710000009051")
        validate_payload = {
            "error": False,
            "messages": [
                "No valid products found. The transaction has been cancelled."
            ],
        }

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
            ) as mock_release,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["not_in_catalog"], 1)
        mock_release.assert_not_called()
        self.assertIn("no in-catalog ean", summary.get("message", "").lower())

    def test_probe_batch_uses_last_in_catalog_ean_for_unlock(self):
        products = [
            self._create_product(barcode="8710000009040"),
            self._create_product(barcode="8710000009041"),
            self._create_product(barcode="8710000009042"),
            self._create_product(barcode="8710000009043"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009040", "TXLAST1"),
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
            self._recognized_checkout_response("8710000009042", "TXLAST2"),
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
                return_value=True,
            ) as mock_release,
        ):
            self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(mock_release.call_count, 2)
        mock_release.assert_any_call(self.instance, "8710000009040")
        mock_release.assert_any_call(self.instance, "8710000009042")

    def test_probe_not_in_catalog_clears_open_transaction_identifier(self):
        product = self._create_product(barcode="8710000009018")
        validate_payload = {
            "error": False,
            "messages": [
                "No valid products found. The transaction has been cancelled."
            ],
        }

        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
            return_value=validate_payload,
        ):
            result = self.service.probe_product_catalog_status(
                self.instance,
                product,
                transaction_identifier="TXBATCH2",
                auto_cancel=False,
            )

        self.assertEqual(result["status"], "not_in_catalog")
        self.assertIsNone(result["transaction_identifier"])

    def test_bulk_probe_uses_anchor_checkout_when_unlock_ean_configured(self):
        known = self._create_product(barcode="8710000009021")
        unknown = self._create_product(barcode="8710000009022")
        self.instance.catalog_probe_unlock_ean = "8710000009021"
        validate_payloads = [
            self._recognized_checkout_response("8710000009021", "TXUNLOCK1"),
            {
                "error": False,
                "transactionIdentifier": "TXUNLOCK2",
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
                "checkoutItems": [{"ean": "8710000009021"}],
            },
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ) as mock_validate,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                return_value={"error": False},
            ) as mock_cancel,
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._release_probe_customer_lock",
                return_value=True,
            ) as mock_release,
        ):
            self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[known.id, unknown.id],
                only_unscanned=False,
            )

        unknown_items = mock_validate.call_args_list[1].args[2]
        self.assertEqual(
            unknown_items,
            [
                {"ean": "8710000009021", "quantity": 1, "pricePerItem": 100.0},
                {"ean": "8710000009022", "quantity": 1, "pricePerItem": 100.0},
            ],
        )
        mock_release.assert_not_called()
        self.assertEqual(mock_cancel.call_count, 2)
        mock_cancel.assert_any_call(self.instance, "TXUNLOCK1")
        mock_cancel.assert_any_call(self.instance, "TXUNLOCK2")

    def test_probe_unknown_product_does_not_cancel(self):
        product = self._create_product(barcode="8710000009002")
        validate_payload = {
            "error": False,
            "messages": [
                "No valid products found. The transaction has been cancelled."
            ],
        }

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            ) as mock_cancel,
        ):
            result = self.service.probe_product_catalog_status(self.instance, product)

        self.assertEqual(result["status"], "not_in_catalog")
        mock_cancel.assert_not_called()

    def test_probe_cancel_failure_returns_error(self):
        product = self._create_product(barcode="8710000009003")
        validate_payload = self._recognized_checkout_response(
            "8710000009003", "TXPROBE2"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=UserError("Cancel failed."),
            ),
        ):
            result = self.service.probe_product_catalog_status(self.instance, product)

        self.assertEqual(result["status"], "error")
        self.assertIn("Cancel failed", result["note"])
        self.assertEqual(result["transaction_identifier"], "TXPROBE2")

    def test_bulk_probe_reports_cancel_failure_in_summary(self):
        product = self._create_product(barcode="8710000009019")
        validate_payload = self._recognized_checkout_response(
            "8710000009019", "TXBATCH3"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=UserError("Cancel failed."),
            ) as mock_cancel,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["error"], 1)
        self.assertIn("Cancel failed", product.bonuscard_catalog_probe_note)
        self.assertIn("Cancel failed", summary.get("message", ""))
        # One cancel attempt inside probe_product_catalog_status, plus two retry
        # attempts from the bulk probe loop.
        self.assertEqual(mock_cancel.call_count, 3)
        mock_cancel.assert_any_call(self.instance, "TXBATCH3")

    def test_bulk_probe_retries_cancel_and_continues_batch(self):
        products = [
            self._create_product(barcode="8710000009023"),
            self._create_product(barcode="8710000009024"),
        ]
        validate_payloads = [
            self._recognized_checkout_response("8710000009023", "TXRETRY1"),
            self._recognized_checkout_response("8710000009024", "TXRETRY2"),
        ]

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                side_effect=validate_payloads,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=[
                    UserError("Cancel failed."),
                    {"error": False},
                    {"error": False},
                ],
            ) as mock_cancel,
        ):
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=[product.id for product in products],
                only_unscanned=False,
            )

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["in_catalog"], 1)
        self.assertFalse(summary.get("message"))
        self.assertEqual(mock_cancel.call_count, 3)
        mock_cancel.assert_any_call(self.instance, "TXRETRY1")
        self.assertIn(
            "cancelled",
            (products[0].bonuscard_catalog_probe_note or "").lower(),
        )
        self.assertNotIn(
            "cancel failed",
            (products[0].bonuscard_catalog_probe_note or "").lower(),
        )

    def test_bulk_probe_updates_note_when_open_transaction_cancelled(self):
        product = self._create_product(barcode="8710000009032")
        validate_payload = self._recognized_checkout_response(
            "8710000009032", "TXNOTE1"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=[UserError("Cancel failed."), {"error": False}],
            ),
        ):
            self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        self.assertIn(
            "open catalog probe transaction cancelled.",
            (product.bonuscard_catalog_probe_note or "").lower(),
        )

    def test_bulk_probe_updates_note_when_open_transaction_cancelled_on_retry(self):
        product = self._create_product(barcode="8710000009033")
        validate_payload = self._recognized_checkout_response(
            "8710000009033", "TXNOTE2"
        )

        with (
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._validate_purchase",
                return_value=validate_payload,
            ),
            patch(
                "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
                side_effect=[
                    UserError("Cancel failed."),
                    UserError("Cancel failed."),
                    {"error": False},
                ],
            ) as mock_cancel,
        ):
            self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        self.assertEqual(mock_cancel.call_count, 3)
        self.assertIn(
            "cancelled on retry",
            (product.bonuscard_catalog_probe_note or "").lower(),
        )

    def test_cancel_catalog_probe_transaction_maps_bonuscard_api_error(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService._cancel_purchase",
            side_effect=BonuscardApiError(
                "Bonuscard API error (2): Locked to another transaction.",
                error_code=2,
            ),
        ):
            note = self.service._cancel_catalog_probe_transaction(
                self.instance, "TXPROBE3"
            )

        self.assertEqual(
            note,
            "Customer is locked to an open transaction. Please try again or restart.",
        )

    def test_product_action_updates_catalog_status(self):
        product = self._create_product(barcode="8710000009004")
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.probe_product_catalog_status",
            return_value={
                "status": "in_catalog",
                "note": "Product found in Bonuscard catalog.",
            },
        ):
            product.action_bonuscard_probe_catalog_status()

        self.assertEqual(product.bonuscard_catalog_status, "in_catalog")
        self.assertTrue(product.bonuscard_catalog_updated_at)
        self.assertEqual(
            product.bonuscard_catalog_probe_note,
            "Product found in Bonuscard catalog.",
        )

    def test_build_catalog_probe_domain_excludes_scanned_products(self):
        domain = self.env["product.product"]._build_catalog_probe_domain()
        self.assertIn(("bonuscard_catalog_status", "=", "not_set"), domain)

    def test_bulk_probe_only_scans_not_set_products(self):
        unscanned = self._create_product(barcode="8710000009010")
        scanned = self._create_product(
            barcode="8710000009011",
            bonuscard_catalog_status="not_in_catalog",
        )
        self.assertEqual(scanned.bonuscard_catalog_status, "not_in_catalog")
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_probe_catalog_status_single",
            autospec=True,
            return_value={"status": "in_catalog", "note": "ok"},
        ) as mock_probe:
            summary = self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=(unscanned | scanned).ids,
                only_unscanned=True,
            )

        self.assertEqual(summary["processed"], 1)
        mock_probe.assert_called_once_with(unscanned, self.instance)

    def test_manual_probe_processes_selected_products(self):
        product = self._create_product(
            barcode="8710000009012",
            bonuscard_catalog_status="not_in_catalog",
        )
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_probe_catalog_status_single",
            autospec=True,
            return_value={"status": "in_catalog", "note": "now in catalog"},
        ) as mock_probe:
            self.env["product.product"].action_bulk_probe_catalog_status(
                company_id=self.env.company.id,
                instance_id=self.instance.id,
                product_ids=product.ids,
                only_unscanned=False,
            )

        mock_probe.assert_called_once_with(product, self.instance)

    def test_probe_requires_manager_group(self):
        product = self._create_product(barcode="8710000009013")
        regular_user = self.env["res.users"].create(
            {
                "name": "Regular User",
                "login": "catalog_probe_user@example.com",
            }
        )
        with self.assertRaises(UserError):
            product.with_user(regular_user).action_bonuscard_probe_catalog_status()

    def test_template_probe_forwards_to_single_variant(self):
        tmpl = (
            self.env["product.template"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(
                {
                    "name": "Probe Template",
                    "barcode": "8710000009020",
                    "list_price": 10.0,
                }
            )
        )
        variant = tmpl.product_variant_id
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.probe_product_catalog_status",
            return_value={
                "status": "not_in_catalog",
                "note": "No valid products found.",
            },
        ):
            tmpl.action_bonuscard_probe_catalog_status()

        self.assertEqual(variant.bonuscard_catalog_status, "not_in_catalog")

    def test_template_probe_note_hidden_for_non_manager(self):
        user_group = self.env.ref("bonuscard_odoo.bonuscard_odoo_group_user")
        bonuscard_user = self.env["res.users"].create(
            {
                "name": "Bonuscard User",
                "login": "bonuscard_user_probe@example.com",
                "group_ids": [(6, 0, [user_group.id])],
            }
        )
        tmpl = (
            self.env["product.template"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(
                {
                    "name": "Probe Note Template",
                    "barcode": "8710000009030",
                    "list_price": 10.0,
                }
            )
        )
        variant = tmpl.product_variant_id
        variant.sudo().write(
            {
                "bonuscard_catalog_probe_note": "Secret probe message",
                "bonuscard_catalog_status": "in_catalog",
            }
        )

        tmpl_as_user = tmpl.with_user(bonuscard_user)
        self.assertFalse(tmpl_as_user.bonuscard_catalog_probe_note)
        self.assertEqual(tmpl_as_user.bonuscard_catalog_status, "in_catalog")

    def test_instance_catalog_probe_price_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.instance.write({"catalog_probe_price": 0})

    def test_create_triggers_auto_catalog_probe(self):
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            self.env["product.product"].create(
                {
                    "name": "Auto Probe Product",
                    "barcode": "8710000009100",
                    "list_price": 10.0,
                }
            )

        mock_trigger.assert_called_once()

    def test_should_auto_probe_rejects_import(self):
        self.assertFalse(
            self.env["product.product"]
            .with_context(import_file=True)
            ._bonuscard_should_auto_probe_catalog()
        )

    def test_should_auto_probe_allows_manual_create(self):
        self.assertTrue(
            self.env["product.product"]._bonuscard_should_auto_probe_catalog()
        )

    def test_auto_probe_updates_catalog_status(self):
        product = (
            self.env["product.product"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(
                {
                    "name": "Auto Probe Status Product",
                    "barcode": "8710000009101",
                    "list_price": 10.0,
                }
            )
        )
        product = self.env["product.product"].browse(product.ids)
        with patch(
            "odoo.addons.bonuscard_odoo.models.bonuscard_api_service.BonuscardApiService.probe_product_catalog_status",
            return_value={
                "status": "in_catalog",
                "note": "Product found in Bonuscard catalog.",
            },
        ):
            product._bonuscard_run_auto_catalog_probe(
                self.env.company.id,
                self.instance.id,
            )

        self.assertEqual(product.bonuscard_catalog_status, "in_catalog")
        self.assertTrue(product.bonuscard_catalog_updated_at)

    def test_auto_probe_skipped_on_import(self):
        product = self._create_product(barcode="8710000009102")
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_run_auto_catalog_probe",
        ) as mock_run:
            product.with_context(
                import_file=True
            )._bonuscard_trigger_auto_catalog_probe()

        mock_run.assert_not_called()

    def test_auto_probe_skipped_without_identifier(self):
        product = self._create_product()
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_run_auto_catalog_probe",
        ) as mock_run:
            product._bonuscard_trigger_auto_catalog_probe()

        mock_run.assert_not_called()

    def test_auto_probe_skipped_when_probe_disabled(self):
        self.instance.write({"catalog_probe_active": False})
        product = self._create_product(barcode="8710000009103")
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_run_auto_catalog_probe",
        ) as mock_run:
            product._bonuscard_trigger_auto_catalog_probe()

        mock_run.assert_not_called()

    def test_write_triggers_auto_catalog_probe_when_barcode_added(self):
        product = self._create_product()
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            product.write({"barcode": "8710000009110"})

        mock_trigger.assert_called_once()

    def test_write_triggers_auto_catalog_probe_when_default_code_added(self):
        product = self._create_product()
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            product.write({"default_code": "ART-9111"})

        mock_trigger.assert_called_once()

    def test_write_skips_probe_when_identifier_unchanged(self):
        product = self._create_product(barcode="8710000009112")
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            product.write({"name": "Renamed Product"})

        mock_trigger.assert_not_called()

    def test_write_skips_probe_when_status_already_set(self):
        product = self._create_product(
            barcode="8710000009113",
            bonuscard_catalog_status="not_in_catalog",
        )
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            product.write({"barcode": "8710000009114"})

        mock_trigger.assert_not_called()

    def test_template_write_triggers_auto_catalog_probe_when_barcode_added(self):
        tmpl = (
            self.env["product.template"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(
                {
                    "name": "Template Barcode Late",
                    "list_price": 10.0,
                }
            )
        )
        tmpl = self.env["product.template"].browse(tmpl.ids)
        with patch(
            "odoo.addons.bonuscard_odoo.models.product_product.ProductProduct._bonuscard_trigger_auto_catalog_probe",
        ) as mock_trigger:
            tmpl.write({"barcode": "8710000009120"})

        mock_trigger.assert_called_once()
