/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    async setPartnerToCurrentOrder(partner) {
        await super.setPartnerToCurrentOrder(...arguments);
        const order = this.getOrder();
        if (order && order.bonuscard_partner_id !== (partner?.id || false)) {
            order.bonuscard_transaction_id = null;
            order.bonuscard_checkout_items = null;
            order.bonuscard_partner_id = partner?.id || false;
        }
        if (!partner) {
            return;
        }
        if (partner.bonuscard_status === "linked" || partner.bonuscard_status === "not_found") {
            return;
        }
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
    },

    async _applyBonuscardDiscountsToOrder(order, result) {
        const discountProduct = this.config?.discount_product_id;
        const discountProductRecord =
            discountProduct?.id && this.models["product.product"].get(discountProduct.id)
                ? this.models["product.product"].get(discountProduct.id)
                : null;

        const orderLineMap = new Map();
        for (const line of order.lines) {
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

        let applied = false;
        for (const item of result.resultItems || []) {
            const itemQuantity = Number(item.quantity ?? 1);
            const itemPricePerItem = Number(item.pricePerItem ?? 0);
            if (itemQuantity <= 0 || itemPricePerItem >= 0) {
                continue;
            }

            const identifiers = new Set(
                [...(item.relatedIdentifiers || []), item.ean]
                    .filter((identifier) => identifier !== undefined && identifier !== null)
                    .map((identifier) => String(identifier))
            );

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
                        {},
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
                    {},
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

        if (order && order.bonuscard_partner_id !== (partner?.id || false)) {
            order.bonuscard_transaction_id = null;
            order.bonuscard_checkout_items = null;
            order.bonuscard_partner_id = partner?.id || false;
        }

        if (partner?.bonuscard_recruitment_code) {
            const orderLines = order.lines
                .filter((l) => l.qty > 0 && (l.product_id?.barcode || l.product_id?.default_code))
                .map((l) => ({
                    product_id: l.product_id.id,
                    qty: l.qty,
                    price_unit: l.price_unit,
                }));

            // Clear any previously stored checkout payload before a new validation
            // attempt. This prevents stale validation state from causing a later
            // FinalizePurchase call if the current validation fails.
            order.bonuscard_checkout_items = null;

            if (orderLines.length > 0) {
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

                        const totalDiscount = result.totalDiscount || 0;
                        if (totalDiscount > 0) {
                            const discountLines = (result.resultItems || [])
                                .map((item) =>
                                    sprintf(
                                        _t("%s: -%s"),
                                        item.description,
                                        Math.abs(
                                            (item.pricePerItem || 0) * (item.quantity || 1)
                                        ).toFixed(2)
                                    )
                                )
                                .join("\n");
                            const confirmed = await ask(this.env.services.dialog, {
                                title: _t("Bonuscard Discounts Applied"),
                                body: sprintf(
                                    _t(
                                        "Total discount: %s\n\n%s\n\nApply the discount to the current order?"
                                    ),
                                    totalDiscount.toFixed(2),
                                    discountLines
                                ),
                            });
                            if (!confirmed) {
                                if (order.bonuscard_transaction_id) {
                                    try {
                                        const result = await this.data.call(
                                            "bonuscard.api.service",
                                            "cancel_purchase_for_pos",
                                            [
                                                order.bonuscard_transaction_id,
                                                order.bonuscard_partner_id || null,
                                            ]
                                        );
                                        if (!result?.error) {
                                            order.bonuscard_transaction_id = null;
                                            order.bonuscard_checkout_items = null;
                                        } else {
                                            this.notification.add(
                                                result.messages?.[0] || _t("Bonuscard cancel failed."),
                                                { type: "warning" }
                                            );
                                        }
                                    } catch {
                                        this.notification.add(_t("Bonuscard cancel failed."), {
                                            type: "warning",
                                        });
                                    }
                                }
                                return;
                            }
                            const applied = await this._applyBonuscardDiscountsToOrder(order, result);
                            if (!applied) {
                                this.notification.add(
                                    _t(
                                        "Bonuscard returned a discount, but it could not be applied to the order. Please configure a discount product in POS settings."
                                    ),
                                    { type: "warning" }
                                );
                                return;
                            }
                            this.notification.add(
                                _t("Bonuscard discount has been applied to the order."),
                                { type: "success" }
                            );
                            return;
                        }
                    } else {
                        const msg = result.messages?.[0] || _t("Bonuscard validation failed.");
                        this.notification.add(msg, { type: "warning" });
                    }
                } catch {
                    this.notification.add(_t("Bonuscard validation failed."), {
                        type: "warning",
                    });
                }
            }
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
