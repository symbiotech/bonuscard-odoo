import odoo.tests
from odoo.tests import HttpCase, tagged


def _unit_test_error_checker(message):
    # Ignore per-test HOOT log lines; fail only on explicit HOOT errors.
    return "[HOOT]" not in message


@tagged("post_install", "-at_install")
class TestBonuscardJs(HttpCase):
    @odoo.tests.no_retry
    def test_bonuscard_pos_unit(self):
        """Run Bonuscard HOOT unit tests headlessly via the Odoo web test runner."""
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&filter=bonuscard",
            "",
            "",
            login="admin",
            timeout=3600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=_unit_test_error_checker,
        )
