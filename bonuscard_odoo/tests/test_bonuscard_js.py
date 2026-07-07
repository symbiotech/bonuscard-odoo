import odoo.tests
from odoo.addons.web.tests.test_js import unit_test_error_checker
from odoo.tests import HttpCase, tagged


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
            error_checker=unit_test_error_checker,
        )
