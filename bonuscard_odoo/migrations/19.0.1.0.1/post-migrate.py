def migrate(cr, version):
    """Backfill stored template catalog mirrors from variant data."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.template"].with_context(active_test=False).search([])._compute_bonuscard_catalog_fields()
