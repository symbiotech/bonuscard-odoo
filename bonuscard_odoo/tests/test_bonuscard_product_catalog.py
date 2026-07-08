from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardProductCatalog(TransactionCase):
    def _create_product(self, **values):
        defaults = {
            "name": "Catalog Test Product",
            "list_price": 10.0,
            "available_in_pos": True,
        }
        defaults.update(values)
        return self.env["product.product"].create(defaults)

    def test_default_catalog_status_is_not_set(self):
        product = self._create_product(barcode="8710000000001")
        self.assertEqual(product.bonuscard_catalog_status, "not_set")

    def test_in_catalog_requires_barcode_or_default_code(self):
        with self.assertRaises(ValidationError):
            self._create_product(bonuscard_catalog_status="in_catalog")

        product = self._create_product(
            barcode="8710000000002",
            bonuscard_catalog_status="in_catalog",
        )
        self.assertEqual(product.bonuscard_catalog_status, "in_catalog")

    def test_mark_in_catalog_action_sets_timestamp(self):
        product = self._create_product(barcode="8710000000003")
        product.action_bonuscard_mark_in_catalog()
        self.assertEqual(product.bonuscard_catalog_status, "in_catalog")
        self.assertTrue(product.bonuscard_catalog_updated_at)

    def test_mark_in_catalog_action_rejects_missing_identifier(self):
        product = self._create_product()
        with self.assertRaises(ValidationError):
            product.action_bonuscard_mark_in_catalog()

    def test_mark_not_in_catalog_action(self):
        product = self._create_product(barcode="8710000000004")
        product.action_bonuscard_mark_not_in_catalog()
        self.assertEqual(product.bonuscard_catalog_status, "not_in_catalog")

    def test_reset_catalog_status_action(self):
        product = self._create_product(
            barcode="8710000000005",
            bonuscard_catalog_status="in_catalog",
        )
        product.action_bonuscard_reset_catalog_status()
        self.assertEqual(product.bonuscard_catalog_status, "not_set")

    def test_load_pos_data_fields_includes_catalog_status(self):
        fields_list = self.env["product.product"]._load_pos_data_fields(
            self.env["pos.config"]
        )
        self.assertIn("bonuscard_catalog_status", fields_list)
