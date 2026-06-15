/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    async setPartnerToCurrentOrder(partner) {
        await super.setPartnerToCurrentOrder(...arguments);
        const order = this.getOrder();
        if (order && order.bonuscard_partner_id !== (partner?.id || false)) {
            order.bonuscard_transaction_id = null;
            order.bonuscard_checkout_items = null;
            order.bonuscard_partner_id = partner?.id || false;
            order.bonuscard_needs_validation = true;
            order.clearBonuscardDiscounts?.();
        }
        if (!partner) {
            order?.clearBonuscardDiscounts?.();
            return;
        }

        if (partner.bonuscard_status !== "linked" && partner.bonuscard_status !== "not_found") {
            try {
                const result = await this.data.call("res.partner", "get_bonuscard_status_for_pos", [
                    partner.id,
                ]);
                partner.bonuscard_status = result.status;
                partner.bonuscard_recruitment_code = result.recruitment_code;
                partner.bonuscard_last_lookup_note = result.note;
                if (result.status === "linked") {
                    this.notification.add(
                        sprintf(_t("Bonuscard member detected: %s"), result.recruitment_code),
                        { type: "success" }
                    );
                } else if (result.status === "not_found") {
                    this.notification.add(_t("Customer is not linked to Bonuscard."), {
                        type: "warning",
                    });
                } else if (result.status === "ambiguous") {
                    this.notification.add(_t("Bonuscard returned multiple customer matches."), {
                        type: "warning",
                    });
                } else if (result.status === "error") {
                    this.notification.add(result.note || _t("Bonuscard lookup failed."), {
                        type: "danger",
                    });
                }
            } catch {
                this.notification.add(_t("Bonuscard lookup failed."), { type: "danger" });
            }
        }

        if (partner.bonuscard_status === "linked") {
            await this._validateBonuscardPurchaseForOrder(order);
        }
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const line = await super.addLineToOrder(vals, order, opts, configure);
        if (opts._bonuscardLine) {
            return line;
        }

        const partner = order?.getPartner();
        if (partner?.bonuscard_recruitment_code) {
            await this._validateBonuscardPurchaseForOrder(order);
        }
        return line;
    },

    _clearAppliedBonuscardDiscounts(order) {
        if (!order) {
            return;
        }

        for (const line of [...order.lines]) {
            if (line.uiState?._bonuscardLine) {
                line.delete();
            } else if (line.uiState?._bonuscardDiscount) {
                line.setDiscount(0);
                delete line.uiState._bonuscardDiscount;
            }
        }
        order.bonuscard_needs_validation = true;
    },

    async _validateBonuscardPurchaseForOrder(order) {
        if (!order) {
            return false;
        }
        const partner = order.getPartner();
        if (!partner?.bonuscard_recruitment_code) {
            return false;
        }

        this._clearAppliedBonuscardDiscounts(order);

        const orderLines = order.lines
            .filter((l) => l.qty > 0 && (l.product_id?.barcode || l.product_id?.default_code))
            .map((l) => ({
                product_id: l.product_id.id,
                qty: l.qty,
                price_unit: l.price_unit,
            }));

        order.bonuscard_checkout_items = null;

        if (orderLines.length === 0) {
            return false;
        }

        try {
            const result = await this.data.call(
                "bonuscard.api.service",
                "validate_purchase_for_pos",
                [partner.id, orderLines, order.bonuscard_transaction_id || null]
            );

            if (!result.error) {
                order.bonuscard_transaction_id = result.transactionIdentifier;
                order.bonuscard_checkout_items =
                    Array.isArray(result.checkoutItems) && result.checkoutItems.length
                        ? result.checkoutItems
                        : orderLines;
                order.bonuscard_partner_id = partner.id;
                order.bonuscard_needs_validation = false;

                if (result.totalDiscount > 0) {
                    const applied = await this._applyBonuscardDiscountsToOrder(order, result);
                    if (!applied) {
                        this.notification.add(
                            _t(
                                "Bonuscard returned a discount, but it could not be applied to the order. Please configure a discount product in POS settings."
                            ),
                            { type: "warning" }
                        );
                    } else {
                        this.notification.add(
                            _t("Bonuscard discount has been applied to the order."),
                            { type: "success" }
                        );
                    }
                }
                return true;
            }
            const msg = result.messages?.[0] || _t("Bonuscard validation failed.");
            this.notification.add(msg, { type: "warning" });
        } catch {
            this.notification.add(_t("Bonuscard validation failed."), { type: "warning" });
        }
        return false;
    },

    async _applyBonuscardDiscountsToOrder(order, result) {
        const discountProduct = this.config?.discount_product_id;
        const discountProductRecord =
            discountProduct?.id && this.models["product.product"].get(discountProduct.id)
                ? this.models["product.product"].get(discountProduct.id)
                : null;

        const orderLineMap = new Map();
        for (const line of order.lines) {
            if (Number(line.qty || 0) <= 0) {
                continue;
            }
            const product = line.product_id;
            if (!product) {
                continue;
            }
            const keys = [String(product.id)];
            if (product.barcode) {
                keys.push(product.barcode);
            }
            if (product.default_code) {
                keys.push(product.default_code);
            }
            for (const key of keys) {
                if (!orderLineMap.has(key)) {
                    orderLineMap.set(key, []);
                }
                orderLineMap.get(key).push(line);
            }
        }

        const checkoutItemsByIdentifier = new Map(
            (result.checkoutItems || [])
                .filter(
                    (checkoutItem) =>
                        checkoutItem &&
                        checkoutItem.identifier !== undefined &&
                        checkoutItem.identifier !== null
                )
                .map((checkoutItem) => [String(checkoutItem.identifier), checkoutItem])
        );

        let applied = false;
        for (const item of result.resultItems || []) {
            const itemQuantity = Number(item.quantity ?? 1);
            const itemPricePerItem = Number(item.pricePerItem ?? 0);
            if (itemQuantity <= 0 || itemPricePerItem >= 0) {
                continue;
            }
            const identifiers = new Set();
            for (const relatedIdentifier of item.relatedIdentifiers || []) {
                const checkoutItem = checkoutItemsByIdentifier.get(String(relatedIdentifier));
                if (checkoutItem?.ean) {
                    identifiers.add(String(checkoutItem.ean));
                }
                if (checkoutItem?.articleNumber) {
                    identifiers.add(String(checkoutItem.articleNumber));
                }
                if (!checkoutItem) {
                    identifiers.add(String(relatedIdentifier));
                }
            }
            if (!identifiers.size && item.ean !== undefined && item.ean !== null) {
                identifiers.add(String(item.ean));
            }
            const matchedLines = new Set();
            for (const identifier of identifiers) {
                const lines = orderLineMap.get(identifier);
                if (lines) {
                    for (const line of lines) {
                        matchedLines.add(line);
                    }
                }
            }

            if (matchedLines.size) {
                let remainingQuantity = Math.abs(itemQuantity);
                let appliedForItem = false;
                const matchedLinesArray = [...matchedLines].sort(
                    (a, b) => Math.abs(Number(a.qty || 0)) - Math.abs(Number(b.qty || 0))
                );
                for (const line of matchedLinesArray) {
                    if (remainingQuantity <= 0) {
                        break;
                    }
                    const lineQuantity = Math.abs(Number(line.qty || 0));
                    if (
                        lineQuantity <= 0 ||
                        typeof line.setDiscount !== "function" ||
                        !line.price_unit
                    ) {
                        continue;
                    }
                    if (lineQuantity <= remainingQuantity) {
                        const unitPrice = Math.abs(line.price_unit);
                        const discountPercent = Math.min(
                            100,
                            (Math.abs(itemPricePerItem) / unitPrice) * 100
                        );
                        if (discountPercent > 0) {
                            line.setDiscount(discountPercent);
                            line.uiState = line.uiState || {};
                            line.uiState._bonuscardDiscount = true;
                            appliedForItem = true;
                            remainingQuantity -= lineQuantity;
                        }
                    } else {
                        break;
                    }
                }
                if (remainingQuantity > 0 && discountProductRecord) {
                    await this.addLineToOrder(
                        {
                            product_id: discountProductRecord,
                            product_tmpl_id: discountProductRecord.product_tmpl_id,
                            qty: remainingQuantity,
                            price_unit: itemPricePerItem,
                        },
                        order,
                        { _bonuscardLine: true },
                        false
                    );
                    appliedForItem = true;
                    remainingQuantity = 0;
                }
                applied = applied || appliedForItem;
            } else if (discountProductRecord) {
                await this.addLineToOrder(
                    {
                        product_id: discountProductRecord,
                        product_tmpl_id: discountProductRecord.product_tmpl_id,
                        qty: itemQuantity,
                        price_unit: itemPricePerItem,
                    },
                    order,
                    { _bonuscardLine: true },
                    false
                );
                applied = true;
            }
        }

        return applied;
    },

    async pay() {
        const order = this.getOrder();
        const partner = order?.getPartner();

        if (
            partner?.bonuscard_recruitment_code &&
            (!order?.bonuscard_transaction_id || order?.bonuscard_needs_validation)
        ) {
            await this._validateBonuscardPurchaseForOrder(order);
        }

        return super.pay(...arguments);
    },

    async closePos() {
        const orders = this.models["pos.order"]?.getAll?.() ?? [];
        for (const order of orders) {
            if (!order?.bonuscard_transaction_id) {
                continue;
            }

            await this.data
                .call("bonuscard.api.service", "cancel_purchase_for_pos", [
                    order.bonuscard_transaction_id,
                    order.bonuscard_partner_id || null,
                ])
                .catch(() => { });
            order.bonuscard_transaction_id = null;
            order.bonuscard_checkout_items = null;
            order.bonuscard_partner_id = false;
        }
        return super.closePos(...arguments);
    },

    async deleteCurrentOrder() {
        const order = this.getOrder();
        if (order?.bonuscard_transaction_id) {
            await this.data
                .call("bonuscard.api.service", "cancel_purchase_for_pos", [
                    order.bonuscard_transaction_id,
                    order.bonuscard_partner_id || null,
                ])
                .catch(() => { });
        }
        return super.deleteCurrentOrder(...arguments);
    },

    async onClickBackButton() {
        if (this.router.state.current === "PaymentScreen") {
            const order = this.getOrder();
            if (order?.bonuscard_transaction_id) {
                try {
                    const result = await this.data.call(
                        "bonuscard.api.service",
                        "cancel_purchase_for_pos",
                        [order.bonuscard_transaction_id, order.bonuscard_partner_id || null]
                    );
                    if (!result?.error) {
                        order.bonuscard_transaction_id = null;
                        order.bonuscard_checkout_items = null;
                        order.bonuscard_partner_id = false;
                    } else {
                        this.notification.add(
                            result.messages?.[0] || _t("Bonuscard cancel failed."),
                            { type: "warning" }
                        );
                    }
                } catch {
                    this.notification.add(_t("Bonuscard cancel failed."), { type: "warning" });
                }
            }
        }
        return super.onClickBackButton(...arguments);
    },
});

patch(PosOrder.prototype, {
    clearBonuscardDiscounts() {
        for (const line of [...this.lines]) {
            if (line.uiState?._bonuscardLine) {
                line.delete();
            } else if (line.uiState?._bonuscardDiscount) {
                line.setDiscount(0);
                delete line.uiState._bonuscardDiscount;
            }
        }
    },

    removeOrderline(line) {
        const result = super.removeOrderline(...arguments);
        if (result) {
            this.clearBonuscardDiscounts();
            this.bonuscard_checkout_items = null;
            this.bonuscard_needs_validation = true;
        }
        return result;
    },
});

patch(PosOrderline.prototype, {
    setQuantity(quantity, keep_price) {
        const result = super.setQuantity(...arguments);
        const order = this.order_id;
        if (result && order) {
            order.bonuscard_checkout_items = null;
            order.bonuscard_needs_validation = true;
        }
        return result;
    },

    delete(...args) {
        const order = this.order_id;
        const result = super.delete(...args);
        if (order) {
            order.bonuscard_checkout_items = null;
            order.bonuscard_needs_validation = true;
        }
        return result;
    },
});

patch(OrderSummary.prototype, {
    async _maybeRevalidateBonuscardOrder() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }
        const partner = order.getPartner();
        if (!partner?.bonuscard_recruitment_code) {
            return;
        }
        await this.pos._validateBonuscardPurchaseForOrder(order);
    },

    async _setValue(val) {
        const { numpadMode } = this.pos;
        let selectedLine = this.currentOrder.getSelectedOrderline();
        if (selectedLine) {
            if (numpadMode === "quantity") {
                if (selectedLine.combo_parent_id) {
                    selectedLine = selectedLine.combo_parent_id;
                }
                if (val === "remove") {
                    this.currentOrder.removeOrderline(selectedLine);
                } else {
                    const result = selectedLine.setQuantity(
                        val,
                        Boolean(selectedLine.combo_line_ids?.length)
                    );
                    if (result !== true) {
                        this.dialog.add(AlertDialog, result);
                        this.numberBuffer.reset();
                    } else {
                        await this._maybeRevalidateBonuscardOrder();
                    }
                }
            } else if (numpadMode === "discount" && val !== "remove") {
                if (selectedLine.combo_parent_id) {
                    selectedLine = selectedLine.combo_parent_id;
                }
                this.pos.setDiscountFromUI(selectedLine, val);
            } else if (numpadMode === "price" && val !== "remove") {
                this.setLinePrice(selectedLine, val);
            }
        }
    },

    async updateQuantityNumber(newQuantity) {
        if (newQuantity !== null) {
            let selectedLine = this.currentOrder.getSelectedOrderline();
            if (selectedLine.combo_parent_id) {
                selectedLine = selectedLine.combo_parent_id;
            }
            const currentQuantity = selectedLine.getQuantity();
            if (newQuantity >= currentQuantity) {
                selectedLine.setQuantity(newQuantity, Boolean(selectedLine.combo_line_ids?.length));
            } else if (newQuantity >= selectedLine.uiState.savedQuantity) {
                await this.handleDecreaseUnsavedLine(newQuantity);
            } else {
                await this.handleDecreaseLine(newQuantity);
            }
            await this._maybeRevalidateBonuscardOrder();
            return true;
        }
        return false;
    },
});

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation() {
        await super.afterOrderValidation(...arguments);
        const order = this.order;

        if (!order?.bonuscard_transaction_id || !order?.bonuscard_checkout_items) {
            return;
        }

        try {
            const result = await this.pos.data.call(
                "bonuscard.api.service",
                "finalize_purchase_for_pos",
                [
                    order.bonuscard_partner_id,
                    order.bonuscard_transaction_id,
                    order.bonuscard_checkout_items,
                ]
            );
            if (result.error) {
                this.pos.notification.add(
                    result.messages?.[0] || _t("Bonuscard finalization failed."),
                    { type: "warning" }
                );
            } else {
                order.bonuscard_transaction_id = null;
                order.bonuscard_checkout_items = null;
            }
        } catch {
            // Do not interrupt the POS payment flow if Bonuscard finalization fails.
            this.pos.notification.add(_t("Bonuscard finalization failed."), { type: "warning" });
        }
    },
});
