/** @odoo-module **/

import { CreateOrderButton } from "@pos_order_to_sale_order/components/create_order_button/create_order_button.esm";
import { CreateOrderPopup } from "@pos_order_to_sale_order/components/create_order_popup/create_order_popup.esm";
import { createSaleOrderFromPosWithBonuscardAudit } from "@bonuscard_pos_order_to_sale_order/js/create_sale_order_from_pos_patch";
import { getDefaultCreateSaleOrderState } from "@pos_order_to_sale_order/utils/create_sale_order_from_pos.esm";
import { patch } from "@web/core/utils/patch";

/**
 * Wire Actions → Create Sale Order (one-shot button + popup) through the
 * Bonuscard audit wrapper so Finalize/release runs before removeOrder.
 *
 * @param {typeof patch} [patchFn=patch]
 */
export function applyBonuscardCreateSaleOrderUiPatches(patchFn = patch) {
    if (CreateOrderButton?.prototype) {
        patchFn(CreateOrderButton.prototype, {
            async onClick(ev) {
                const orderState = getDefaultCreateSaleOrderState(this.pos.config);
                if (orderState) {
                    ev.stopPropagation();
                    await createSaleOrderFromPosWithBonuscardAudit(
                        this.pos,
                        this.orm,
                        this.ui,
                        orderState
                    );
                    this.props.close?.();
                    return;
                }
                return super.onClick(...arguments);
            },
        });
    }

    if (CreateOrderPopup?.prototype) {
        patchFn(CreateOrderPopup.prototype, {
            async _actionCreateSaleOrder(orderState) {
                await createSaleOrderFromPosWithBonuscardAudit(
                    this.pos,
                    this.orm,
                    this.ui,
                    orderState
                );
                return this.props.close();
            },
        });
    }
}

try {
    applyBonuscardCreateSaleOrderUiPatches();
} catch (error) {
    console.error(
        "bonuscard_pos_order_to_sale_order: Create Sale Order UI patches failed",
        error
    );
}
