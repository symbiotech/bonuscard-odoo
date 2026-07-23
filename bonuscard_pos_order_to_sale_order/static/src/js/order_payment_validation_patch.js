/** @odoo-module **/

import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { patch } from "@web/core/utils/patch";

/**
 * OCA pos_order_to_sale_order converts fully Customer Account payments into a
 * sale.order and never syncs a pos.order — so Bonuscard's preSyncAllOrders
 * Finalize never runs. After a *new* conversion, reuse the same post-payment
 * helper Bonuscard uses for normal paid POS orders.
 *
 * Always builds a fresh patch object so tests can re-apply outermost without
 * breaking the ``super`` prototype chain.
 */
export function applyBonuscardSaleOrderBridgePatch() {
    if (!OrderPaymentValidation?.prototype) {
        return;
    }
    patch(OrderPaymentValidation.prototype, {
        async finalizeSaleOrderFromPos() {
            const order = this.order;
            const wasConverted = Boolean(order?.uiState?.saleOrderConverted);
            const result = await super.finalizeSaleOrderFromPos(...arguments);
            if (order?.uiState?.saleOrderConverted && !wasConverted) {
                await this.pos._applyBonuscardAuditAfterPayment(order);
            }
            return result;
        },
    });
}

try {
    applyBonuscardSaleOrderBridgePatch();
} catch (error) {
    console.error(
        "bonuscard_pos_order_to_sale_order: OrderPaymentValidation patch failed",
        error
    );
}
