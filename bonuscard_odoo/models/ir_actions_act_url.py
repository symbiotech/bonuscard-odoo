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

    def _localized_bonuscard_doc_url(self):
        """Return the localized GitHub URL for a Bonuscard doc action, if any."""
        self.ensure_one()
        xmlid = self.get_external_id().get(self.id)
        guide = _BONUSCARD_DOC_ACTIONS.get(xmlid)
        if not guide:
            return None
        return self.env["bonuscard.docs"]._docs_url(guide)

    def _get_action_dict(self):
        """Rewrite Bonuscard doc URLs to match the current UI language."""
        result = super()._get_action_dict()
        url = self._localized_bonuscard_doc_url()
        if url:
            result["url"] = url
        return result

    def read(self, fields=None, load="_classic_read"):
        """Rewrite Bonuscard doc URLs (web client loads act_url via read())."""
        result = super().read(fields, load=load)
        if fields is not None and "url" not in fields:
            return result
        xmlids = self.get_external_id()
        docs = self.env["bonuscard.docs"]
        for action, row in zip(self, result, strict=True):
            guide = _BONUSCARD_DOC_ACTIONS.get(xmlids.get(action.id))
            if guide:
                row["url"] = docs._docs_url(guide)
        return result
