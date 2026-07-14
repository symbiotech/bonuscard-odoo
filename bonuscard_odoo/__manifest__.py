{
    "name": "Bonuscard Connector",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Bonuscard integration foundation for Odoo POS",
    "author": "symbiotech",
    "website": "https://github.com/symbiotech/bonuscard-odoo",
    "license": "LGPL-3",
    "depends": [
        "base",
        "point_of_sale",
        "product",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/bonuscard_bulk_prefetch_cron.xml",
        "data/bonuscard_catalog_probe_cron.xml",
        "data/product_server_actions.xml",
        "views/bonuscard_instance_views.xml",
        "views/product_template_views.xml",
        "views/product_product_views.xml",
        "views/pos_order_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "bonuscard_odoo/static/src/app/**/*",
        ],
        "web.assets_unit_tests": [
            "bonuscard_odoo/static/tests/**/*",
        ],
    },
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
}
