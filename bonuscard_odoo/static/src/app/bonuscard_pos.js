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
import { uuidv4 } from "@point_of_sale/utils";
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
    // A transaction is "pending" when the POS either received a transaction ID
    // from Bonuscard (confirmed) or generated one client-side and may already
    // have sent it in a validation request (unconfirmed candidate).
    _bonuscardPendingTransactionId(order) {
        return order?.bonuscard_transaction_id || order?._bonuscardCandidateTxId || null;
    },

    _bonuscardHasCheckoutItems(order) {
        const items = order?.bonuscard_checkout_items;
        return Array.isArray(items) && items.length > 0;
    },

    async _cancelBonuscardPurchaseForOrder(order, { retries = 0, logMethod = "cancel" } = {}) {
        const transactionId = this._bonuscardPendingTransactionId(order);
        if (!transactionId) {
            return { success: true };
        }

        let lastMessage = null;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const result = await this.data.call(
                    "bonuscard.api.service",
                    "cancel_purchase_for_pos",
                    [transactionId, order.bonuscard_partner_id || null]
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
                            transactionId,
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
            break;
        }
        return { success: false, message: lastMessage || _t("Bonuscard cancel failed.") };
    },

    async _releaseBonuscardTransactionIfPending(
        order,
        { logMethod = "releasePending", notifyOnFailure = true, failureMessage = null, sticky = false } = {}
    ) {
        if (!this._bonuscardPendingTransactionId(order)) {
            return { success: true };
        }
        const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
            retries: 1,
            logMethod,
        });
        if (cancelResult.success) {
            this._clearBonuscardPurchaseState(order);
            return cancelResult;
        }
        logPosMessage(
            "Bonuscard",
            logMethod,
            "Bonuscard cancel failed while releasing pending transaction — customer may remain locked",
            false,
            [
                {
                    transactionId: this._bonuscardPendingTransactionId(order),
                    partnerId: order.bonuscard_partner_id || null,
                    message: cancelResult.message,
                },
            ]
        );
        if (notifyOnFailure) {
            this.notification.add(
                failureMessage ||
                    cancelResult.message ||
                    _t("Bonuscard cancel failed."),
                { type: "warning", sticky }
            );
        }
        return cancelResult;
    },

    _clearBonuscardPurchaseState(order) {
        if (!order) {
            return;
        }
        order.bonuscard_transaction_id = null;
        order._bonuscardCandidateTxId = null;
        order.bonuscard_checkout_items = null;
        order.bonuscard_partner_id = false;
        order.bonuscard_needs_validation = true;
        order.clearBonuscardDiscounts?.();
    },

    _isBonuscardCustomerLockError(result) {
        if (!result?.error) {
            return false;
        }
        if (Number(result.errorCode) === 2) {
            return true;
        }
        const message = (result.messages?.[0] || "").toLowerCase();
        return message.includes("locked") && message.includes("transaction");
    },

    async _cancelBonuscardPurchaseWhenLeavingOrder(order, logMethod) {
        if (!this._bonuscardPendingTransactionId(order)) {
            return { success: true };
        }
        const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
            retries: 1,
            logMethod,
        });
        if (cancelResult.success) {
            this._clearBonuscardPurchaseState(order);
            return cancelResult;
        }
        logPosMessage(
            "Bonuscard",
            logMethod,
            "Bonuscard cancel failed while leaving order — customer may remain locked",
            false,
            [
                {
                    transactionId: this._bonuscardPendingTransactionId(order),
                    partnerId: order.bonuscard_partner_id || null,
                    message: cancelResult.message,
                },
            ]
        );
        this.notification.add(
            cancelResult.message ||
                _t(
                    "Could not cancel the pending Bonuscard transaction before switching orders. The customer may remain locked until it expires."
                ),
            { type: "warning", sticky: true }
        );
        return cancelResult;
    },

    async _cancelOrphanedBonuscardTransactionsForPartner(partnerId, excludeOrder) {
        if (!partnerId) {
            return false;
        }
        const orders = this.models["pos.order"]?.getAll?.() ?? [];
        let cancelledAny = false;
        for (const other of orders) {
            if (other === excludeOrder) {
                continue;
            }
            if (
                other.bonuscard_partner_id !== partnerId ||
                !this._bonuscardPendingTransactionId(other)
            ) {
                continue;
            }
            const cancelResult = await this._cancelBonuscardPurchaseForOrder(other, {
                retries: 1,
                logMethod: "recoverOrphanedLock",
            });
            if (cancelResult.success) {
                this._clearBonuscardPurchaseState(other);
                cancelledAny = true;
            }
        }
        return cancelledAny;
    },

    // Note: addNewOrder and setOrder must stay synchronous — core callers
    // (e.g. the openOrder getter) use their return values directly. The
    // cancellation of the order being left runs in the background; failures
    // surface via the sticky warning in _cancelBonuscardPurchaseWhenLeavingOrder.
    addNewOrder(data = {}) {
        const previousOrder = this.getOrder();
        const order = super.addNewOrder(data);
        if (
            previousOrder &&
            previousOrder !== order &&
            this._bonuscardPendingTransactionId(previousOrder)
        ) {
            this._cancelBonuscardPurchaseWhenLeavingOrder(previousOrder, "addNewOrder");
        }
        return order;
    },

    setOrder(order) {
        const previousOrder = this.getOrder();
        const result = super.setOrder(order);
        if (
            previousOrder &&
            previousOrder !== order &&
            this._bonuscardPendingTransactionId(previousOrder)
        ) {
            this._cancelBonuscardPurchaseWhenLeavingOrder(previousOrder, "setOrder");
        }
        return result;
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
                            transactionId: this._bonuscardPendingTransactionId(order),
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
            await this._validateBonuscardPurchaseForOrder(order, { notifyOnDiscount: true });
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

    async _validateBonuscardPurchaseForOrder(
        order,
        { notifyOnDiscount = false, _lockRecoveryAttempt = false } = {}
    ) {
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
            await this._releaseBonuscardTransactionIfPending(order, {
                logMethod: "_validateBonuscardPurchaseForOrder",
                failureMessage: _t(
                    "Could not release the pending Bonuscard transaction. The customer may remain locked until it expires."
                ),
            });
            return false;
        }

        // Generate the transaction identifier client-side (the API prefers a
        // GUID without dashes). This guarantees that concurrent validations —
        // e.g. adding a product then immediately editing its quantity — all
        // send the SAME identifier. Without it, a second request racing the
        // first would arrive without an identifier while the customer is
        // already locked, producing Bonuscard error 2 and orphaning the lock.
        if (!order.bonuscard_transaction_id && !order._bonuscardCandidateTxId) {
            order._bonuscardCandidateTxId = uuidv4().replace(/-/g, "");
        }
        const transactionIdentifier =
            order.bonuscard_transaction_id || order._bonuscardCandidateTxId;

        try {
            const result = await this.data.call(
                "bonuscard.api.service",
                "validate_purchase_for_pos",
                [partner.id, orderLines, transactionIdentifier]
            );

            // A newer validation was triggered while we were waiting; discard this result
            // to prevent stale concurrent calls from stacking up discount lines.
            if (order._bonuscardValidationVersion !== myVersion) {
                // Never lose the transaction ID, otherwise the customer lock
                // becomes orphaned and impossible to cancel.
                if (!result?.error && result?.transactionIdentifier && !order.bonuscard_transaction_id) {
                    order.bonuscard_transaction_id = result.transactionIdentifier;
                    order._bonuscardCandidateTxId = null;
                }
                return false;
            }

            if (!result.error) {
                order.bonuscard_transaction_id =
                    result.transactionIdentifier || transactionIdentifier;
                order._bonuscardCandidateTxId = null;
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
                    } else if (notifyOnDiscount) {
                        this.notification.add(
                            _t("Bonuscard discount has been applied to the order."),
                            { type: "success" }
                        );
                    }
                }
                return true;
            }
            if (!_lockRecoveryAttempt && this._isBonuscardCustomerLockError(result)) {
                // The lock may belong to this order's own (stale) transaction
                // or to an abandoned draft order for the same customer. Cancel
                // both before retrying.
                let recovered = false;
                if (this._bonuscardPendingTransactionId(order)) {
                    const cancelResult = await this._cancelBonuscardPurchaseForOrder(order, {
                        retries: 1,
                        logMethod: "recoverLock",
                    });
                    if (cancelResult.success) {
                        this._clearBonuscardPurchaseState(order);
                        recovered = true;
                    }
                }
                const orphanCancelled =
                    await this._cancelOrphanedBonuscardTransactionsForPartner(
                        partner.id,
                        order
                    );
                recovered = recovered || orphanCancelled;
                if (recovered) {
                    return this._validateBonuscardPurchaseForOrder(order, {
                        notifyOnDiscount,
                        _lockRecoveryAttempt: true,
                    });
                }
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
                [{ partnerId: partner?.id, transactionId: transactionIdentifier, error }]
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

        if (partner?.bonuscard_recruitment_code) {
            await this._validateBonuscardPurchaseForOrder(order, { notifyOnDiscount: true });
        }

        return super.pay(...arguments);
    },

    async closePos() {
        const orders = this.models["pos.order"]?.getAll?.() ?? [];
        for (const order of orders) {
            if (!this._bonuscardPendingTransactionId(order)) {
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
                            transactionId: this._bonuscardPendingTransactionId(order),
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
        if (this._bonuscardPendingTransactionId(order)) {
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
                            transactionId: this._bonuscardPendingTransactionId(order),
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
            if (this._bonuscardPendingTransactionId(order)) {
                try {
                    const result = await this.data.call(
                        "bonuscard.api.service",
                        "cancel_purchase_for_pos",
                        [
                            this._bonuscardPendingTransactionId(order),
                            order.bonuscard_partner_id || null,
                        ]
                    );
                    if (!result?.error) {
                        order.bonuscard_transaction_id = null;
                        order._bonuscardCandidateTxId = null;
                        order.bonuscard_checkout_items = null;
                        order.bonuscard_partner_id = false;
                    } else {
                        logPosMessage(
                            "Bonuscard",
                            "onClickBackButton",
                            "Bonuscard cancel returned error during back navigation",
                            false,
                            [{ transactionId: this._bonuscardPendingTransactionId(order), partnerId: order.bonuscard_partner_id || null, message: result.messages?.[0] }]
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
                        [{ transactionId: this._bonuscardPendingTransactionId(order), partnerId: order.bonuscard_partner_id || null, error }]
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
    _bonuscardReleaseFailedAfterPaymentMessage(apiMessage) {
        const context = _t(
            "Payment succeeded but Bonuscard could not release the pending transaction. The customer may remain locked."
        );
        if (apiMessage) {
            return `${context} (${apiMessage})`;
        }
        return context;
    },

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
                            transactionId: this.pos._bonuscardPendingTransactionId(order),
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

        if (!this.pos._bonuscardPendingTransactionId(order)) {
            return;
        }

        const shouldFinalize = this.pos._bonuscardHasCheckoutItems(order);

        if (!shouldFinalize) {
            const releaseResult = await this.pos._releaseBonuscardTransactionIfPending(order, {
                logMethod: "afterOrderValidation",
                notifyOnFailure: false,
            });
            if (!releaseResult.success) {
                this.pos.notification.add(
                    this._bonuscardReleaseFailedAfterPaymentMessage(releaseResult.message),
                    { type: "warning", sticky: true }
                );
            }
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
                        transactionId: this.pos._bonuscardPendingTransactionId(order),
                        partnerId: order.bonuscard_partner_id || null,
                        message: finalizeResult.message,
                    },
                ]
            );
            const releaseResult = await this.pos._releaseBonuscardTransactionIfPending(order, {
                logMethod: "afterOrderValidation_finalizeFallback",
                notifyOnFailure: false,
            });
            if (releaseResult.success) {
                return;
            }
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
