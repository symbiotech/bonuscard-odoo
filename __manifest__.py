{
    "name": "Bonuscard Connector",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Bonuscard integration foundation for Odoo POS",
    "description": """
Bonuscard Connector
===================

Connect Odoo with the Bonuscard API to configure company-specific credentials and
prepare POS-oriented loyalty and discount workflows.

Configuration
-------------
Set API base URL, Basic-auth credentials, and culture in Bonuscard connection records.

Usage
-----
Use the Test Connection action to validate connector reachability before implementing
ValidatePurchase, FinalizePurchase, and CancelPurchase flows.
    """,
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
