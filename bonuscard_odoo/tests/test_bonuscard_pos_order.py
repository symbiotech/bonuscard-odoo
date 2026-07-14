from datetime import datetime, timedelta, timezone

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardPosOrder(TransactionCase):
    def test_bonuscard_state_defaults_to_not_applicable(self):
        order = self.env["pos.order"].new({})
        self.assertEqual(order.bonuscard_state, "not_applicable")

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
        self.assertFalse(vals["bonuscard_last_error_message"])

    def test_bonuscard_audit_fields_from_ui_clears_with_false(self):
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_last_error_message": False,
                "bonuscard_validated_at": False,
            }
        )
        self.assertFalse(vals["bonuscard_last_error_message"])
        self.assertFalse(vals["bonuscard_validated_at"])

    def test_bonuscard_audit_fields_from_ui_maps_false_state_to_not_applicable(self):
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_state": False,
                "bonuscard_transaction_identifier": False,
            }
        )
        self.assertEqual(vals["bonuscard_state"], "not_applicable")
        self.assertFalse(vals["bonuscard_transaction_identifier"])

    def test_bonuscard_audit_fields_from_ui_ignores_empty_values(self):
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_state": "",
                "bonuscard_transaction_identifier": None,
            }
        )
        self.assertEqual(vals, {})

    def test_bonuscard_audit_fields_from_ui_accepts_iso_datetime(self):
        iso_validated_at = "2026-07-14T14:12:47.000+02:00"
        vals = self.env["pos.order"]._bonuscard_audit_fields_from_ui(
            {
                "bonuscard_validated_at": iso_validated_at,
                "bonuscard_finalized_at": iso_validated_at,
            }
        )
        self.assertEqual(
            vals["bonuscard_validated_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "2026-07-14 12:12:47",
        )
        self.assertEqual(
            vals["bonuscard_finalized_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "2026-07-14 12:12:47",
        )

    def test_bonuscard_parse_ui_datetime_normalizes_timezone_aware_datetime(self):
        aware_validated_at = datetime(
            2026,
            7,
            14,
            14,
            12,
            47,
            tzinfo=timezone(timedelta(hours=2)),
        )
        parsed = self.env["pos.order"]._bonuscard_parse_ui_datetime(aware_validated_at)
        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-14 12:12:47")
