from odoo.addons.bonuscard_odoo.models.bonuscard_docs import GITHUB_DOCS_BASE
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBonuscardDocs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Needed so with_context(lang="sv_SE") can load translated action names.
        lang = cls.env["res.lang"]._activate_lang("sv_SE")
        if not lang:
            cls.env["res.lang"]._create_lang("sv_SE")

    def test_docs_lang_key(self):
        docs = self.env["bonuscard.docs"]
        self.assertEqual(docs.with_context(lang="sv_SE")._docs_lang_key(), "sv")
        self.assertEqual(docs.with_context(lang="sv_FI")._docs_lang_key(), "sv")
        self.assertEqual(docs.with_context(lang="en_US")._docs_lang_key(), "en")
        self.assertEqual(docs.with_context(lang="en_GB")._docs_lang_key(), "en")
        self.assertEqual(docs.with_context(lang="fi_FI")._docs_lang_key(), "en")

    def test_docs_url_swedish_guides(self):
        docs = self.env["bonuscard.docs"].with_context(lang="sv_SE")
        self.assertEqual(
            docs._docs_url("cashier"),
            f"{GITHUB_DOCS_BASE}/docs/tutorials/sv/pos-kassor.md",
        )
        self.assertEqual(
            docs._docs_url("manager"),
            f"{GITHUB_DOCS_BASE}/docs/tutorials/sv/pos-admin.md",
        )

    def test_docs_url_english_guides(self):
        docs = self.env["bonuscard.docs"].with_context(lang="en_US")
        self.assertEqual(
            docs._docs_url("cashier"),
            f"{GITHUB_DOCS_BASE}/docs/tutorials/en/pos-cashier.md",
        )
        self.assertEqual(
            docs._docs_url("manager"),
            f"{GITHUB_DOCS_BASE}/docs/tutorials/en/pos-manager.md",
        )

    def test_act_url_rewritten_for_swedish(self):
        action = self.env.ref("bonuscard_odoo.action_bonuscard_docs_cashier")
        payload = action.with_context(lang="sv_SE")._get_action_dict()
        self.assertEqual(
            payload["url"],
            f"{GITHUB_DOCS_BASE}/docs/tutorials/sv/pos-kassor.md",
        )
        self.assertEqual(payload["type"], "ir.actions.act_url")
        self.assertEqual(payload["target"], "new")

    def test_act_url_english_default(self):
        action = self.env.ref("bonuscard_odoo.action_bonuscard_docs_manager")
        payload = action.with_context(lang="en_US")._get_action_dict()
        self.assertEqual(
            payload["url"],
            f"{GITHUB_DOCS_BASE}/docs/tutorials/en/pos-manager.md",
        )

    def test_docs_lang_key_from_user_lang_without_context_lang(self):
        """Reproduce web-client path: no context lang, Swedish user preference."""
        user = self.env.ref("base.user_admin")
        user.lang = "sv_SE"
        docs = self.env["bonuscard.docs"].with_user(user).with_context(lang=None)
        self.assertIsNone(docs.env.context.get("lang"))
        self.assertEqual(docs._docs_lang_key(), "sv")
        self.assertEqual(
            docs._docs_url("cashier"),
            f"{GITHUB_DOCS_BASE}/docs/tutorials/sv/pos-kassor.md",
        )

    def test_act_url_read_rewritten_for_swedish_user_without_context_lang(self):
        """Web client loads ir.actions.act_url via read(), not _get_action_dict()."""
        user = self.env.ref("base.user_admin")
        user.lang = "sv_SE"
        action = self.env.ref("bonuscard_odoo.action_bonuscard_docs_cashier")
        payload = (
            action.with_user(user)
            .with_context(lang=None)
            .read(["url", "type", "target"])[0]
        )
        self.assertEqual(
            payload["url"],
            f"{GITHUB_DOCS_BASE}/docs/tutorials/sv/pos-kassor.md",
        )
        self.assertEqual(payload["type"], "ir.actions.act_url")
        self.assertEqual(payload["target"], "new")
