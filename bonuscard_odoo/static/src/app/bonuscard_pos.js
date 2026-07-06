/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { registry } from "@web/core/registry";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { BonuscardRegistrationService } from "./bonuscard_registration_service";
import "./bonuscard_partner_line_patch";

// Register the Bonuscard Registration Service
registry.category("services").add("bonuscard_registration", {
    dependencies: ["notification", "action"],
    start(env, { notification, action }) {
        return new BonuscardRegistrationService(env, { notification, action });
    },
});

patch(PosStore.prototype, {
    async _cancelBonuscardPurchaseForOrder(order, { retries = 0, logMethod = "cancel" } = {}) {
        if (!order?.bonuscard_transaction_id) {
            return { success: true };
        }

        let lastMessage = null;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const result = await this.data.call(
                    "bonuscard.api.service",
                    "cancel_purchase_for_pos",
                    [order.bonuscard_transaction_id, order.bonuscard_partner_id || null]
                );
                if (result?.error === false) {
                    return { success: true };
                }
                lastMessage = result?.messages?.[0] || null;
            } catch (error) {
                logPosMessage(
                    "Bonuscard",
                    logMethod,
                    "Bonuscard cancel request failed",
                    false,
                    [
                        {
                            transactionId: order.bonuscard_transaction_id,
                            partnerId: order.bonuscard_partner_id || null,
                            attempt: attempt + 1,
                            error,
                        },
                    ]
                );
                if (attempt < retries) {
                    continue;
                }
                return { success: false, message: _t("Bonuscard cancel failed.") };
            }
            if (attempt < retries) {
                continue;
            }
            return {
                success: false,
                message: lastMessage || _t("Bonuscard cancel failed."),
            };
        }
        return { success: false, message: lastMessage || _t("Bonuscard cancel failed.") };
    },

    _clearBonuscardPurchaseState(order) {
        if (!order) {
            return;
        }
        order.bonuscard_transaction_id = null;
        order.bonuscard_checkout_items = null;
        order.bonuscard_partner_id = false;
        order.bonuscard_needs_validation = true;
        order.clearBonuscardDiscounts?.();
    },

    async setPartnerToCurrentOrder(partner, ...rest) {
        const order = this.getOrder();
        const newPartnerId = partner?.id || false;
        const bonuscardPartnerChanged = order && order.bonuscard_partner_id !== newPartnerId;

        if (bonuscardPartnerChanged) {
            const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
                logMethod: "setPartnerToCurrentOrder",
            });
            if (!cancelResult.success) {
                logPosMessage(
                    "Bonuscard",
                    "setPartnerToCurrentOrder",
                    "Bonuscard cancel failed during partner change — keeping current customer",
                    false,
                    [
                        {
                            transactionId: order.bonuscard_transaction_id,
                            partnerId: order.bonuscard_partner_id || null,
                            newPartnerId,
                            message: cancelResult.message,
                        },
                    ]
                );
                this.notification.add(
                    cancelResult.message ||
                        _t(
                            "Bonuscard cancel failed. The customer could not be changed while a Bonuscard transaction is pending."
                        ),
                    { type: "warning", sticky: true }
                );
                return;
            }
            this._clearBonuscardPurchaseState(order);
        }

        // Pass false instead of null to parent, as POS setPartner doesn't handle null
        await super.setPartnerToCurrentOrder(partner || false, ...rest);

        if (bonuscardPartnerChanged) {
            order.bonuscard_partner_id = newPartnerId;
            order.bonuscard_needs_validation = true;
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
                    logPosMessage(
                        "Bonuscard",
                        "setPartnerToCurrentOrder",
                        "Customer not found in Bonuscard",
                        false,
                        [{ partnerId: partner?.id }]
                    );
                    this.notification.add(_t("Customer is not linked to Bonuscard."), {
                        type: "warning",
                    });
                } else if (result.status === "ambiguous") {
                    logPosMessage(
                        "Bonuscard",
                        "setPartnerToCurrentOrder",
                        "Bonuscard returned ambiguous customer matches",
                        false,
                        [{ partnerId: partner?.id }]
                    );
                    this.notification.add(_t("Bonuscard returned multiple customer matches."), {
                        type: "warning",
                    });
                } else if (result.status === "error") {
                    logPosMessage(
                        "Bonuscard",
                        "setPartnerToCurrentOrder",
                        "Bonuscard lookup returned error status",
                        false,
                        [{ partnerId: partner?.id, note: result.note }]
                    );
                    this.notification.add(result.note || _t("Bonuscard lookup failed."), {
                        type: "danger",
                    });
                }
            } catch (error) {
                logPosMessage(
                    "Bonuscard",
                    "setPartnerToCurrentOrder",
                    "Bonuscard lookup failed for partner",
                    false,
                    [{ partnerId: partner?.id, error }]
                );
                this.notification.add(_t("Bonuscard lookup failed."), { type: "danger" });
            }
        }

        if (partner.bonuscard_status === "linked" && bonuscardPartnerChanged) {
            await this._validateBonuscardPurchaseForOrder(order);
        }
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const line = await super.addLineToOrder(vals, order, opts, configure);
        if (opts._bonuscardLine) {
            // Mark the line so _clearAppliedBonuscardDiscounts can find and delete it
            // during the next validation cycle.
            if (line) {
                line.uiState = line.uiState || {};
                line.uiState._bonuscardLine = true;
            }
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

        // Guard against concurrent calls (e.g. rapid product additions).
        // Only the latest invocation may apply its result; all earlier in-flight
        // calls are discarded once a newer one has started.
        order._bonuscardValidationVersion = (order._bonuscardValidationVersion || 0) + 1;
        const myVersion = order._bonuscardValidationVersion;

        this._clearAppliedBonuscardDiscounts(order);

        const orderLines = order.lines
            .filter(
                (l) =>
                    l.qty > 0 &&
                    l.price_unit > 0 &&
                    !l.uiState?._bonuscardLine &&
                    (l.product_id?.barcode || l.product_id?.default_code)
            )
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

            // A newer validation was triggered while we were waiting; discard this result
            // to prevent stale concurrent calls from stacking up discount lines.
            if (order._bonuscardValidationVersion !== myVersion) {
                return false;
            }

            if (!result.error) {
                order.bonuscard_transaction_id =
                    result.transactionIdentifier || order.bonuscard_transaction_id;
                order.bonuscard_checkout_items =
                    Array.isArray(result.checkoutItems) && result.checkoutItems.length
                        ? result.checkoutItems
                        : orderLines;
                order.bonuscard_partner_id = partner.id;
                order.bonuscard_needs_validation = false;

                if (result.totalDiscount > 0) {
                    order._bonuscardApplying = true;
                    let applied;
                    try {
                        applied = await this._applyBonuscardDiscountsToOrder(order, result);
                    } finally {
                        order._bonuscardApplying = false;
                    }
                    if (!applied) {
                        logPosMessage(
                            "Bonuscard",
                            "_validateBonuscardPurchaseForOrder",
                            "Bonuscard discount could not be applied - missing discount product",
                            false,
                            [{ partnerId: partner?.id, totalDiscount: result.totalDiscount }]
                        );
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
            logPosMessage(
                "Bonuscard",
                "_validateBonuscardPurchaseForOrder",
                "Bonuscard validation returned error response",
                false,
                [{ partnerId: partner?.id, message: msg }]
            );
            this.notification.add(msg, { type: "warning" });
        } catch (error) {
            logPosMessage(
                "Bonuscard",
                "_validateBonuscardPurchaseForOrder",
                "Bonuscard validation request failed",
                false,
                [{ partnerId: partner?.id, transactionId: order.bonuscard_transaction_id, error }]
            );
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
                        if (!discountProductRecord) {
                            const unitPrice = Math.abs(line.price_unit);
                            const lineTotal = lineQuantity * unitPrice;
                            const discountAmount = remainingQuantity * Math.abs(itemPricePerItem);
                            const discountPercent = Math.min(
                                100,
                                lineTotal > 0 ? (discountAmount / lineTotal) * 100 : 0
                            );
                            if (discountPercent > 0) {
                                line.setDiscount(discountPercent);
                                line.uiState = line.uiState || {};
                                line.uiState._bonuscardDiscount = true;
                                appliedForItem = true;
                                remainingQuantity = 0;
                            }
                        }
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

            const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
                retries: 1,
                logMethod: "closePos",
            });
            if (!cancelResult.success) {
                logPosMessage(
                    "Bonuscard",
                    "closePos",
                    "Bonuscard cancel failed during POS close — transaction lock may remain active",
                    false,
                    [
                        {
                            transactionId: order.bonuscard_transaction_id,
                            partnerId: order.bonuscard_partner_id || null,
                            message: cancelResult.message,
                        },
                    ]
                );
                this.notification.add(
                    cancelResult.message ||
                        _t(
                            "Could not cancel the pending Bonuscard transaction before closing. It may remain locked until it expires."
                        ),
                    { type: "warning", sticky: true }
                );
                continue;
            }
            this._clearBonuscardPurchaseState(order);
        }
        return super.closePos(...arguments);
    },

    async onDeleteOrder(order) {
        if (order?.bonuscard_transaction_id) {
            const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
                retries: 1,
                logMethod: "onDeleteOrder",
            });
            if (!cancelResult.success) {
                logPosMessage(
                    "Bonuscard",
                    "onDeleteOrder",
                    "Bonuscard cancel failed during order deletion — order deletion blocked to allow retry",
                    false,
                    [
                        {
                            transactionId: order.bonuscard_transaction_id,
                            partnerId: order.bonuscard_partner_id || null,
                            message: cancelResult.message,
                        },
                    ]
                );
                this.notification.add(
                    cancelResult.message ||
                        _t(
                            "Could not cancel the pending Bonuscard transaction. The order has been kept so you can retry cancellation."
                        ),
                    { type: "warning", sticky: true }
                );
                return;
            }
            this._clearBonuscardPurchaseState(order);
        }
        return super.onDeleteOrder(order);
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
                        logPosMessage(
                            "Bonuscard",
                            "onClickBackButton",
                            "Bonuscard cancel returned error during back navigation",
                            false,
                            [{ transactionId: order.bonuscard_transaction_id, partnerId: order.bonuscard_partner_id || null, message: result.messages?.[0] }]
                        );
                        this.notification.add(
                            result.messages?.[0] || _t("Bonuscard cancel failed."),
                            { type: "warning" }
                        );
                    }
                } catch (error) {
                    logPosMessage(
                        "Bonuscard",
                        "onClickBackButton",
                        "Bonuscard cancel failed during back navigation",
                        false,
                        [{ transactionId: order.bonuscard_transaction_id, partnerId: order.bonuscard_partner_id || null, error }]
                    );
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
        if (result === true && order && !order._bonuscardApplying) {
            order.bonuscard_checkout_items = null;
            order.bonuscard_needs_validation = true;
        }
        return result;
    },

    delete(...args) {
        const order = this.order_id;
        const result = super.delete(...args);
        if (order && !order._bonuscardApplying) {
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
    _bonuscardFinalizePendingAfterPaymentMessage(apiMessage) {
        const context = _t(
            "Payment succeeded but Bonuscard could not commit the discount. The loyalty transaction is still pending."
        );
        if (apiMessage) {
            return `${context} (${apiMessage})`;
        }
        return context;
    },

    async _finalizeBonuscardPurchaseForOrder(order) {
        const retries = 1;
        let lastMessage = null;

        for (let attempt = 0; attempt <= retries; attempt++) {
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
                if (!result?.error) {
                    return { success: true };
                }
                lastMessage = result.messages?.[0] || null;
            } catch (error) {
                logPosMessage(
                    "Bonuscard",
                    "_finalizeBonuscardPurchaseForOrder",
                    "Bonuscard finalize request failed",
                    false,
                    [
                        {
                            transactionId: order.bonuscard_transaction_id,
                            partnerId: order.bonuscard_partner_id || null,
                            attempt: attempt + 1,
                            error,
                        },
                    ]
                );
                if (attempt < retries) {
                    await new Promise((resolve) => setTimeout(resolve, 500));
                    continue;
                }
                return { success: false, message: lastMessage };
            }
            if (attempt < retries) {
                await new Promise((resolve) => setTimeout(resolve, 500));
                continue;
            }
            break;
        }
        return { success: false, message: lastMessage };
    },

    async afterOrderValidation() {
        await super.afterOrderValidation(...arguments);
        const order = this.order;

        if (!order?.bonuscard_transaction_id || !order?.bonuscard_checkout_items) {
            return;
        }

        const finalizeResult = await this._finalizeBonuscardPurchaseForOrder(order);
        if (!finalizeResult.success) {
            logPosMessage(
                "Bonuscard",
                "afterOrderValidation",
                "Bonuscard finalization failed after payment",
                false,
                [
                    {
                        transactionId: order.bonuscard_transaction_id,
                        partnerId: order.bonuscard_partner_id || null,
                        message: finalizeResult.message,
                    },
                ]
            );
            this.pos.notification.add(
                this._bonuscardFinalizePendingAfterPaymentMessage(finalizeResult.message),
                { type: "warning", sticky: true }
            );
            return;
        }
        order.bonuscard_transaction_id = null;
        order.bonuscard_checkout_items = null;
    },
});
