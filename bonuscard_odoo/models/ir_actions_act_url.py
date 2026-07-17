from odoo import models

# xmlid -> guide key for bonuscard.docs._docs_url
_BONUSCARD_DOC_ACTIONS = {
    "bonuscard_odoo.action_bonuscard_docs_tutorials": "tutorials",
    "bonuscard_odoo.action_bonuscard_docs_cashier": "cashier",
    "bonuscard_odoo.action_bonuscard_docs_manager": "manager",
    "bonuscard_odoo.action_bonuscard_docs_readme": "readme",
}


class IrActionsActUrl(models.Model):
    _inherit = "ir.actions.act_url"

    def _get_action_dict(self):
        """Rewrite Bonuscard doc URLs to match the current UI language."""
        result = super()._get_action_dict()
        xmlid = self.get_external_id().get(self.id)
        guide = _BONUSCARD_DOC_ACTIONS.get(xmlid)
        if guide:
            result["url"] = self.env["bonuscard.docs"]._docs_url(guide)
        return result
