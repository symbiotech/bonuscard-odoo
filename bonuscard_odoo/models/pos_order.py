from odoo import api, fields, models

_BONUSCARD_AUDIT_FIELDS = (
    "bonuscard_state",
    "bonuscard_transaction_identifier",
    "bonuscard_validated_at",
    "bonuscard_finalized_at",
    "bonuscard_last_error_message",
)


class PosOrder(models.Model):
    _inherit = "pos.order"

    bonuscard_state = fields.Selection(
        selection=[
            ("not_applicable", "Not applicable"),
            ("skipped", "Skipped"),
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

    @api.model
    def _bonuscard_audit_fields_from_ui(self, ui_order):
        vals = {}
        for field_name in _BONUSCARD_AUDIT_FIELDS:
            if field_name not in ui_order:
                continue
            value = ui_order[field_name]
            if value in (None, False, ""):
                continue
            if field_name in ("bonuscard_validated_at", "bonuscard_finalized_at"):
                value = fields.Datetime.to_datetime(value)
            vals[field_name] = value
        return vals

    @api.model
    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        bonuscard_vals = self._bonuscard_audit_fields_from_ui(order)
        if bonuscard_vals:
            self.browse(order_id).write(bonuscard_vals)
        return order_id
