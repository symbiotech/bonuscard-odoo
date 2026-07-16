/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";

patch(ProductCard.prototype, {
    get bonuscardCatalogStatus() {
        const product = this.props.product;
        if (!product) {
            return null;
        }
        if (product.bonuscard_catalog_status) {
            return product.bonuscard_catalog_status;
        }
        const variants = product.product_variant_ids || [];
        return variants.length === 1
            ? variants[0].bonuscard_catalog_status || null
            : null;
    },
    get showBonuscardCatalogMark() {
        return this.bonuscardCatalogStatus === "in_catalog";
    },
    get bonuscardCatalogMarkTitle() {
        return _t("In Bonuscard Catalog");
    },
});
