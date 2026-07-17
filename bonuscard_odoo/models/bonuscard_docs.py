"""Language-aware GitHub documentation URLs for Bonuscard menus."""

from odoo import models

GITHUB_DOCS_BASE = "https://github.com/symbiotech/bonuscard-odoo/blob/19.0"

# guide key -> {lang prefix: path under the 19.0 branch}
_DOC_PATHS = {
    "tutorials": {
        "en": "docs/tutorials/README.md",
        "sv": "docs/tutorials/README.md",
    },
    "cashier": {
        "en": "docs/tutorials/en/pos-cashier.md",
        "sv": "docs/tutorials/sv/pos-kassor.md",
    },
    "manager": {
        "en": "docs/tutorials/en/pos-manager.md",
        "sv": "docs/tutorials/sv/pos-admin.md",
    },
    "readme": {
        "en": "bonuscard_odoo/README.rst",
        "sv": "bonuscard_odoo/README.rst",
    },
}


class BonuscardDocs(models.AbstractModel):
    _name = "bonuscard.docs"
    _description = "Bonuscard documentation URL helpers"

    def _docs_lang_key(self):
        """Return ``sv`` for Swedish UI languages, otherwise ``en``.

        In the web client, ``context['lang']`` may be absent on some action
        loads; fall back to the signed-in user's language preference.
        """
        lang = self.env.context.get("lang") or self.env.user.lang
        lang = (lang or "en_US").replace("-", "_")
        if lang.lower().startswith("sv"):
            return "sv"
        return "en"

    def _docs_url(self, guide):
        """Build the GitHub blob URL for ``guide`` in the current UI language."""
        paths = _DOC_PATHS[guide]
        lang = self._docs_lang_key()
        path = paths.get(lang) or paths["en"]
        return f"{GITHUB_DOCS_BASE}/{path}"

    def action_open_docs(self, guide):
        """Return an ``ir.actions.act_url`` opening the guide on GitHub."""
        return {
            "type": "ir.actions.act_url",
            "url": self._docs_url(guide),
            "target": "new",
        }

    def action_open_docs_tutorials(self):
        return self.action_open_docs("tutorials")

    def action_open_docs_cashier(self):
        return self.action_open_docs("cashier")

    def action_open_docs_manager(self):
        return self.action_open_docs("manager")

    def action_open_docs_readme(self):
        return self.action_open_docs("readme")
