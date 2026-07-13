from odoo import api, fields, models
from odoo.exceptions import UserError

# Template-level catalog UI is intended for setups where Odoo's Product Variants
# feature is disabled (users lack product.group_product_variant). Catalog status
# is still stored on product.product; templates mirror the single variant.


class ProductTemplate(models.Model):
    _inherit = "product.template"

    bonuscard_catalog_status = fields.Selection(
        selection=[
            ("not_set", "Not Set"),
            ("in_catalog", "In Bonuscard Catalog"),
            ("not_in_catalog", "Not in Bonuscard Catalog"),
        ],
        string="Bonuscard Catalog",
        compute="_compute_bonuscard_catalog_fields",
        inverse="_inverse_bonuscard_catalog_status",
        store=True,
    )
    bonuscard_catalog_updated_at = fields.Datetime(
        string="Bonuscard Catalog Updated",
        compute="_compute_bonuscard_catalog_fields",
        store=True,
        readonly=True,
    )
    bonuscard_catalog_probe_note = fields.Text(
        string="Bonuscard Catalog Probe Note",
        compute="_compute_bonuscard_catalog_fields",
        readonly=True,
    )

    @api.depends(
        "product_variant_ids.bonuscard_catalog_status",
        "product_variant_ids.bonuscard_catalog_updated_at",
        "product_variant_ids.bonuscard_catalog_probe_note",
    )
    def _compute_bonuscard_catalog_fields(self):
        is_probe_manager = self.env.user.has_group(
            "bonuscard_odoo.bonuscard_odoo_group_manager"
        )
        for template in self:
            variant = template._bonuscard_catalog_variant()
            if not variant:
                template.bonuscard_catalog_status = False
                template.bonuscard_catalog_updated_at = False
                template.bonuscard_catalog_probe_note = False
                continue

            template.bonuscard_catalog_status = variant.bonuscard_catalog_status
            template.bonuscard_catalog_updated_at = variant.bonuscard_catalog_updated_at
            template.bonuscard_catalog_probe_note = (
                variant.bonuscard_catalog_probe_note if is_probe_manager else False
            )

    def _inverse_bonuscard_catalog_status(self):
        for template in self:
            variant = template._bonuscard_catalog_variant()
            if not variant:
                raise UserError(
                    self.env._(
                        "Bonuscard catalog status can only be edited on products "
                        "with exactly one variant."
                    )
                )
            variant.bonuscard_catalog_status = template.bonuscard_catalog_status
        self._compute_bonuscard_catalog_fields()

    def _bonuscard_catalog_variant(self):
        """Return the single variant for template-level catalog management."""
        self.ensure_one()
        variants = self.product_variant_ids
        if len(variants) == 1:
            return variants[0]
        return self.env["product.product"]

    def _bonuscard_action_on_single_variant(self, method_name):
        if self.env.user.has_group("product.group_product_variant"):
            raise UserError(
                self.env._(
                    "Bonuscard catalog actions on the Products list are only "
                    "available when Product Variants are disabled. Open "
                    "Inventory > Products > Product Variants instead."
                )
            )

        invalid = self.filtered(lambda t: not t._bonuscard_catalog_variant())
        if invalid:
            raise UserError(
                self.env._(
                    "These products cannot be updated from the Products list "
                    "because they do not have exactly one variant: %s",
                    ", ".join(invalid.mapped("display_name")),
                )
            )

        variants = self.mapped("product_variant_ids")
        return getattr(variants, method_name)()

    def action_bonuscard_mark_in_catalog(self):
        return self._bonuscard_action_on_single_variant(
            "action_bonuscard_mark_in_catalog"
        )

    def action_bonuscard_mark_not_in_catalog(self):
        return self._bonuscard_action_on_single_variant(
            "action_bonuscard_mark_not_in_catalog"
        )

    def action_bonuscard_reset_catalog_status(self):
        return self._bonuscard_action_on_single_variant(
            "action_bonuscard_reset_catalog_status"
        )

    def action_bonuscard_probe_catalog_status(self):
        return self._bonuscard_action_on_single_variant(
            "action_bonuscard_probe_catalog_status"
        )
