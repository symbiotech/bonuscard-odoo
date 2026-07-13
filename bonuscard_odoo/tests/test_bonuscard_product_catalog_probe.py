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
        return self.env["product.product"].create(defaults)

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

    def test_classify_in_catalog_with_transaction(self):
        status, _note = self.service._classify_catalog_probe_response(
            {
                "error": False,
                "transactionIdentifier": "TX001",
                "messages": ["Discount available."],
            }
        )
        self.assertEqual(status, "in_catalog")

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
                "checkoutItems": [{"ean": "8710000009021"}],
                "resultItems": [{"ean": "8710000009022"}],
            },
            probe_ean="8710000009022",
            anchor_ean="8710000009021",
        )
        self.assertEqual(status, "not_in_catalog")

    def test_probe_known_product_cancels_transaction(self):
        product = self._create_product(barcode="8710000009001")
        validate_payload = {
            "error": False,
            "transactionIdentifier": "TXPROBE1",
            "messages": ["Product recognized."],
        }

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
            {
                "error": False,
                "transactionIdentifier": "TXBATCH1",
                "messages": ["Product recognized."],
            },
            {
                "error": False,
                "transactionIdentifier": "TXBATCH2",
                "messages": ["Product recognized."],
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
            {
                "error": False,
                "transactionIdentifier": "TXBATCH2",
                "messages": ["Product recognized."],
            },
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
            {
                "error": False,
                "transactionIdentifier": "TXBATCH2",
                "messages": ["Product recognized."],
            },
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
            {
                "error": False,
                "transactionIdentifier": "TXUNLOCK3",
                "messages": ["Product recognized."],
            },
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

    def test_probe_batch_uses_last_in_catalog_ean_for_unlock(self):
        products = [
            self._create_product(barcode="8710000009040"),
            self._create_product(barcode="8710000009041"),
            self._create_product(barcode="8710000009042"),
            self._create_product(barcode="8710000009043"),
        ]
        validate_payloads = [
            {
                "error": False,
                "transactionIdentifier": "TXLAST1",
                "messages": ["Product recognized."],
            },
            {
                "error": False,
                "messages": [
                    "No valid products found. The transaction has been cancelled."
                ],
            },
            {
                "error": False,
                "transactionIdentifier": "TXLAST2",
                "messages": ["Product recognized."],
            },
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
            {
                "error": False,
                "transactionIdentifier": "TXUNLOCK1",
                "messages": ["Product recognized."],
            },
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
        validate_payload = {
            "error": False,
            "transactionIdentifier": "TXPROBE2",
            "messages": ["Product recognized."],
        }

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
        validate_payload = {
            "error": False,
            "transactionIdentifier": "TXBATCH3",
            "messages": ["Product recognized."],
        }

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
        self.assertEqual(mock_cancel.call_count, 2)
        mock_cancel.assert_any_call(self.instance, "TXBATCH3")

    def test_bulk_probe_retries_cancel_and_continues_batch(self):
        products = [
            self._create_product(barcode="8710000009023"),
            self._create_product(barcode="8710000009024"),
        ]
        validate_payloads = [
            {
                "error": False,
                "transactionIdentifier": "TXRETRY1",
                "messages": ["Product recognized."],
            },
            {
                "error": False,
                "transactionIdentifier": "TXRETRY2",
                "messages": ["Product recognized."],
            },
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
        tmpl = self.env["product.template"].create(
            {
                "name": "Probe Template",
                "barcode": "8710000009020",
                "list_price": 10.0,
            }
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
        tmpl = self.env["product.template"].create(
            {
                "name": "Probe Note Template",
                "barcode": "8710000009030",
                "list_price": 10.0,
            }
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
