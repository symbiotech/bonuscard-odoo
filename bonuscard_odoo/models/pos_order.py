from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    bonuscard_state = fields.Selection(
        selection=[
            ("not_applicable", "Not applicable"),
            ("skipped", "Skipped (no catalog lines)"),
            ("validated", "Validated"),
            ("finalized", "Finalized"),
            ("failed", "Failed"),
        ],
        string="Bonuscard",
        tracking=True,
        copy=False,
        index=True,
    )
    bonuscard_transaction_identifier = fields.Char(
        tracking=True,
        copy=False,
        index=True,
    )
    bonuscard_validated_at = fields.Datetime(copy=False)
    bonuscard_finalized_at = fields.Datetime(copy=False)
    bonuscard_last_error_message = fields.Text(
        copy=False,
    )
