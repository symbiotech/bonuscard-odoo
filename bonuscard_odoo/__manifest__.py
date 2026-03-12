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
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/bonuscard_instance_views.xml",
        "views/menus.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
}
