from odoo.exceptions import UserError, ValidationError
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
        product = (
            self.env["product.product"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(defaults)
        )
        return self.env["product.product"].browse(product.ids)

    def _create_template(self, **values):
        defaults = {
            "name": "Catalog Test Template",
            "list_price": 10.0,
            "available_in_pos": True,
        }
        defaults.update(values)
        tmpl = (
            self.env["product.template"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(defaults)
        )
        return self.env["product.template"].browse(tmpl.ids)

    def _create_multi_variant_template(self, **values):
        attribute = self.env["product.attribute"].create(
            {"name": "Catalog Test Attribute", "create_variant": "always"}
        )
        value_s = self.env["product.attribute.value"].create(
            {"name": "S", "attribute_id": attribute.id}
        )
        value_m = self.env["product.attribute.value"].create(
            {"name": "M", "attribute_id": attribute.id}
        )
        defaults = {
            "name": "Catalog Multi Variant Template",
            "list_price": 10.0,
            "available_in_pos": True,
            "attribute_line_ids": [
                (
                    0,
                    0,
                    {
                        "attribute_id": attribute.id,
                        "value_ids": [(6, 0, [value_s.id, value_m.id])],
                    },
                )
            ],
        }
        defaults.update(values)
        tmpl = (
            self.env["product.template"]
            .with_context(bonuscard_skip_catalog_probe=True)
            .create(defaults)
        )
        return self.env["product.template"].browse(tmpl.ids)

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

        product_with_code = self._create_product(
            default_code="ART-0001",
            bonuscard_catalog_status="in_catalog",
        )
        self.assertEqual(product_with_code.bonuscard_catalog_status, "in_catalog")

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

    def test_template_actions_forward_to_single_variant(self):
        tmpl = self._create_template(barcode="8710000000100")
        variant = tmpl.product_variant_id
        self.assertEqual(tmpl.bonuscard_catalog_status, "not_set")

        tmpl.action_bonuscard_mark_in_catalog()
        self.assertEqual(variant.bonuscard_catalog_status, "in_catalog")
        self.assertEqual(tmpl.bonuscard_catalog_status, "in_catalog")

        tmpl.action_bonuscard_mark_not_in_catalog()
        self.assertEqual(variant.bonuscard_catalog_status, "not_in_catalog")
        self.assertEqual(tmpl.bonuscard_catalog_status, "not_in_catalog")

        tmpl.action_bonuscard_reset_catalog_status()
        self.assertEqual(variant.bonuscard_catalog_status, "not_set")
        self.assertEqual(tmpl.bonuscard_catalog_status, "not_set")

    def test_template_bulk_action_updates_all_selected(self):
        tmpl1 = self._create_template(barcode="8710000001000", name="Bulk 1")
        tmpl2 = self._create_template(barcode="8710000001001", name="Bulk 2")
        (tmpl1 | tmpl2).action_bonuscard_mark_in_catalog()
        self.assertEqual(tmpl1.bonuscard_catalog_status, "in_catalog")
        self.assertEqual(tmpl2.bonuscard_catalog_status, "in_catalog")

    def test_template_catalog_status_empty_when_multiple_variants(self):
        tmpl = self._create_multi_variant_template()
        self.assertEqual(len(tmpl.product_variant_ids), 2)
        self.assertFalse(tmpl.bonuscard_catalog_status)

    def test_template_actions_reject_multiple_variants(self):
        tmpl = self._create_multi_variant_template()
        with self.assertRaises(UserError):
            tmpl.action_bonuscard_mark_in_catalog()

    def test_template_actions_reject_when_variants_enabled_for_user(self):
        tmpl = self._create_template(barcode="8710000000400")
        variant_group = self.env.ref("product.group_product_variant")
        self.env.user.write({"group_ids": [(4, variant_group.id)]})
        with self.assertRaises(UserError):
            tmpl.action_bonuscard_mark_in_catalog()
        self.env.user.write({"group_ids": [(3, variant_group.id)]})

    def test_template_write_catalog_status_updates_variant(self):
        tmpl = self._create_template(barcode="8710000000200")
        variant = tmpl.product_variant_id
        tmpl.bonuscard_catalog_status = "in_catalog"
        self.assertEqual(variant.bonuscard_catalog_status, "in_catalog")
        self.assertEqual(tmpl.bonuscard_catalog_status, "in_catalog")
        self.assertTrue(tmpl.bonuscard_catalog_updated_at)

    def test_template_write_catalog_status_requires_single_variant(self):
        tmpl = self._create_multi_variant_template()
        with self.assertRaises(UserError):
            tmpl.bonuscard_catalog_status = "in_catalog"

    def test_template_write_in_catalog_requires_identifier(self):
        tmpl = self._create_template()
        with self.assertRaises(ValidationError):
            tmpl.bonuscard_catalog_status = "in_catalog"

    def test_template_write_in_catalog_allows_default_code_only(self):
        tmpl = self._create_template(default_code="ART-0002")
        tmpl.bonuscard_catalog_status = "in_catalog"
        self.assertEqual(tmpl.product_variant_id.bonuscard_catalog_status, "in_catalog")

    def test_template_write_catalog_status_allowed_for_variant_group_user(self):
        tmpl = self._create_template(barcode="8710000000300")
        variant_group = self.env.ref("product.group_product_variant")
        self.env.user.write({"group_ids": [(4, variant_group.id)]})
        tmpl.bonuscard_catalog_status = "in_catalog"
        self.assertEqual(tmpl.product_variant_id.bonuscard_catalog_status, "in_catalog")
        self.env.user.write({"group_ids": [(3, variant_group.id)]})

    def test_load_pos_data_fields_includes_catalog_status(self):
        fields_list = self.env["product.product"]._load_pos_data_fields(
            self.env["pos.config"]
        )
        self.assertIn("bonuscard_catalog_status", fields_list)

    def test_template_load_pos_data_fields_includes_catalog_status(self):
        fields_list = self.env["product.template"]._load_pos_data_fields(
            self.env["pos.config"]
        )
        self.assertIn("bonuscard_catalog_status", fields_list)
