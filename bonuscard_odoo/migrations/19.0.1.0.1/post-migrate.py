def migrate(cr, version):
    """Backfill stored template catalog mirrors from variant data."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    ProductTemplate = env["product.template"].with_context(active_test=False)

    last_id = 0
    batch_size = 1000
    while True:
        templates = ProductTemplate.search(
            [("id", ">", last_id)], order="id", limit=batch_size
        )
        if not templates:
            break
        templates._compute_bonuscard_catalog_fields()
        last_id = templates[-1].id
