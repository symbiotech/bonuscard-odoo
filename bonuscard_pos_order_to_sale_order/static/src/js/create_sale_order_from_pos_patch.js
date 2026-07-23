/** @odoo-module **/

import { createSaleOrderFromPos } from "@pos_order_to_sale_order/utils/create_sale_order_from_pos.esm";

/**
 * Actions → Create Sale Order removes the POS order after conversion, which
 * would Cancel a pending Bonuscard ValidatePurchase. Create the sale order
 * without removing first, run the same post-payment Bonuscard audit helper,
 * then remove the cart (default).
 *
 * Does not start ValidatePurchase — only Finalize/release when a pending
 * transaction already exists (same as Customer Account finalize path).
 *
 * @param {Object} pos
 * @param {Object} orm
 * @param {Object} ui
 * @param {string} orderState
 * @param {Object} [options]
 * @param {Boolean} [options.removeOrder=true]
 * @param {Function} [options.createSaleOrderFromPosFn=createSaleOrderFromPos]
 *        Injectable for unit tests.
 */
export async function createSaleOrderFromPosWithBonuscardAudit(
    pos,
    orm,
    ui,
    orderState,
    options = {}
) {
    const {
        removeOrder = true,
        createSaleOrderFromPosFn = createSaleOrderFromPos,
        ...ocaOptions
    } = options;
    const order = pos.getOrder();
    await createSaleOrderFromPosFn(pos, orm, ui, orderState, {
        ...ocaOptions,
        removeOrder: false,
    });
    if (order && typeof pos._applyBonuscardAuditAfterPayment === "function") {
        await pos._applyBonuscardAuditAfterPayment(order);
    }
    if (removeOrder && order) {
        pos.removeOrder(order);
        pos.addNewOrder();
    }
}
