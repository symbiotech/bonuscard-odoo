from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    bonuscard_catalog_status = fields.Selection(
        selection=[
            ("not_set", "Not Set"),
            ("in_catalog", "In Bonuscard Catalog"),
            ("not_in_catalog", "Not in Bonuscard Catalog"),
        ],
        string="Bonuscard Catalog",
        default="not_set",
        copy=False,
        tracking=True,
    )
    bonuscard_catalog_updated_at = fields.Datetime(
        string="Bonuscard Catalog Updated",
        copy=False,
        readonly=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["bonuscard_catalog_status"]

    @api.constrains("bonuscard_catalog_status", "barcode", "default_code")
    def _check_bonuscard_catalog_requires_identifier(self):
        for product in self:
            if product.bonuscard_catalog_status != "in_catalog":
                continue
            if not (product.barcode or product.default_code):
                raise ValidationError(
                    self.env._(
                        "A product must have a barcode or article number before it "
                        "can be marked as in the Bonuscard catalog."
                    )
                )

    def _bonuscard_write_catalog_status(self, status):
        self.write(
            {
                "bonuscard_catalog_status": status,
                "bonuscard_catalog_updated_at": fields.Datetime.now(),
            }
        )

    def action_bonuscard_mark_in_catalog(self):
        invalid = self.filtered(
            lambda product: not (product.barcode or product.default_code)
        )
        if invalid:
            raise ValidationError(
                self.env._(
                    "These products cannot be marked as in the Bonuscard catalog "
                    "because they have no barcode or article number: %s",
                    ", ".join(invalid.mapped("display_name")),
                )
            )
        self._bonuscard_write_catalog_status("in_catalog")
        return True

    def action_bonuscard_mark_not_in_catalog(self):
        self._bonuscard_write_catalog_status("not_in_catalog")
        return True

    def action_bonuscard_reset_catalog_status(self):
        self._bonuscard_write_catalog_status("not_set")
        return True
