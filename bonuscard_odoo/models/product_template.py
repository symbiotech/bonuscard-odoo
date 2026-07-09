from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    bonuscard_catalog_status = fields.Selection(
        selection=[
            ("not_set", "Not Set"),
            ("in_catalog", "In Bonuscard Catalog"),
            ("not_in_catalog", "Not in Bonuscard Catalog"),
        ],
        compute="_compute_bonuscard_catalog_fields",
        store=True,
        readonly=True,
        groups="bonuscard_odoo.bonuscard_odoo_group_user",
    )
    bonuscard_catalog_updated_at = fields.Datetime(
        compute="_compute_bonuscard_catalog_fields",
        store=True,
        readonly=True,
        groups="bonuscard_odoo.bonuscard_odoo_group_user",
    )

    @api.depends(
        "product_variant_ids.bonuscard_catalog_status",
        "product_variant_ids.bonuscard_catalog_updated_at",
    )
    def _compute_bonuscard_catalog_fields(self):
        for template in self:
            # This addon is intended for setups where product variants are not used.
            # If a template has multiple variants, the "catalog status" is ambiguous,
            # so we keep it unset on the template and manage variants directly.
            variants = template.product_variant_ids
            if len(variants) != 1:
                template.bonuscard_catalog_status = "not_set"
                template.bonuscard_catalog_updated_at = False
                continue

            variant = variants[0]
            template.bonuscard_catalog_status = variant.bonuscard_catalog_status
            template.bonuscard_catalog_updated_at = variant.bonuscard_catalog_updated_at

    def action_bonuscard_mark_in_catalog(self):
        self.mapped("product_variant_ids").action_bonuscard_mark_in_catalog()
        return True

    def action_bonuscard_mark_not_in_catalog(self):
        self.mapped("product_variant_ids").action_bonuscard_mark_not_in_catalog()
        return True

    def action_bonuscard_reset_catalog_status(self):
        self.mapped("product_variant_ids").action_bonuscard_reset_catalog_status()
        return True
