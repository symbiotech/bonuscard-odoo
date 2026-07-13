from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardPosOrder(TransactionCase):
    def test_bonuscard_audit_fields_from_ui_maps_values(self):
        validated_at = "2026-07-13 10:00:00"
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_state": "finalized",
                "bonuscard_transaction_identifier": "TX-123",
                "bonuscard_validated_at": validated_at,
                "bonuscard_finalized_at": validated_at,
                "bonuscard_last_error_message": False,
            }
        )
        self.assertEqual(vals["bonuscard_state"], "finalized")
        self.assertEqual(vals["bonuscard_transaction_identifier"], "TX-123")
        self.assertEqual(
            vals["bonuscard_validated_at"].strftime("%Y-%m-%d %H:%M:%S"),
            validated_at,
        )
        self.assertEqual(
            vals["bonuscard_finalized_at"].strftime("%Y-%m-%d %H:%M:%S"),
            validated_at,
        )
        self.assertNotIn("bonuscard_last_error_message", vals)

    def test_bonuscard_audit_fields_from_ui_ignores_empty_values(self):
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_state": "",
                "bonuscard_transaction_identifier": None,
            }
        )
        self.assertEqual(vals, {})
