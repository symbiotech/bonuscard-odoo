{
    "name": "Bonuscard POS Order To Sale Order",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Finalize Bonuscard when POS creates a sale order.",
    "author": "symbiotech",
    "website": "https://github.com/symbiotech/bonuscard-odoo",
    "license": "LGPL-3",
    "depends": ["bonuscard_odoo", "pos_order_to_sale_order"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "bonuscard_pos_order_to_sale_order/static/src/js/order_payment_validation_patch.js",
            "bonuscard_pos_order_to_sale_order/static/src/js/create_sale_order_from_pos_patch.js",
            "bonuscard_pos_order_to_sale_order/static/src/js/create_sale_order_ui_patch.js",
        ],
        "web.assets_unit_tests": [
            "bonuscard_pos_order_to_sale_order/static/src/js/order_payment_validation_patch.js",
            "bonuscard_pos_order_to_sale_order/static/src/js/create_sale_order_from_pos_patch.js",
            "bonuscard_pos_order_to_sale_order/static/src/js/create_sale_order_ui_patch.js",
            "bonuscard_pos_order_to_sale_order/static/tests/unit/order_payment_validation_patch.test.js",
            "bonuscard_pos_order_to_sale_order/static/tests/unit/create_sale_order_from_pos_patch.test.js",
            "bonuscard_pos_order_to_sale_order/static/tests/unit/create_sale_order_ui_patch.test.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
