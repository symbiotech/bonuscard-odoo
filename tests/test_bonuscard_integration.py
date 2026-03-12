import os
from pathlib import Path
from unittest import SkipTest

from odoo.tests import TransactionCase, tagged


def _load_dotenv_if_present():
    """Load simple KEY=VALUE pairs from .env if env vars are not already set."""
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.exists():
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@tagged("bonuscard_integration", "post_install", "-at_install")
class TestBonuscardIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _load_dotenv_if_present()

        cls.api_base_url = os.getenv("BONUSCARD_TEST_API_BASE_URL", "").strip()
        cls.api_username = os.getenv("BONUSCARD_TEST_USERNAME", "").strip()
        cls.api_password = os.getenv("BONUSCARD_TEST_PASSWORD", "").strip()
        cls.api_culture = (
            os.getenv("BONUSCARD_TEST_CULTURE", "en-GB").strip() or "en-GB"
        )

        missing_vars = [
            name
            for name, value in [
                ("BONUSCARD_TEST_API_BASE_URL", cls.api_base_url),
                ("BONUSCARD_TEST_USERNAME", cls.api_username),
                ("BONUSCARD_TEST_PASSWORD", cls.api_password),
            ]
            if not value
        ]
        if missing_vars:
            raise SkipTest(
                f"Integration test skipped. Missing variables: {', '.join(missing_vars)}"
            )

    def test_live_test_connection_with_env_credentials(self):
        instance = self.env["bonuscard.connector.instance"].create(
            {
                "name": "Bonuscard Integration Test",
                "api_base_url": self.api_base_url,
                "api_username": self.api_username,
                "api_password": self.api_password,
                "api_culture": self.api_culture,
            }
        )

        instance.action_test_connection()
        self.assertEqual(instance.connection_status, "ok")
