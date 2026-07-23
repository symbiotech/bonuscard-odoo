/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { patch } from "@web/core/utils/patch";
import { applyBonuscardSaleOrderBridgePatch } from "@bonuscard_pos_order_to_sale_order/js/order_payment_validation_patch";

/**
 * Inner mock of OCA finalizeSaleOrderFromPos so the bridge's ``super`` is
 * deterministic without loading the full POS / OCA stack.
 */
function applyMockFinalizeSaleOrderFromPos(behavior) {
    patch(OrderPaymentValidation.prototype, {
        async finalizeSaleOrderFromPos() {
            return behavior(this);
        },
    });
}

function makeValidation({ order, applyAudit }) {
    // OrderPaymentValidation.order is a getter over pos.models — do not assign it.
    const validation = Object.create(OrderPaymentValidation.prototype);
    validation.orderUuid = "test-order-uuid";
    validation.pos = {
        models: {
            "pos.order": {
                getBy: (_field, uuid) =>
                    uuid === validation.orderUuid ? order : undefined,
            },
        },
        _applyBonuscardAuditAfterPayment: applyAudit,
    };
    return validation;
}

describe("bonuscard_pos_order_to_sale_order OrderPaymentValidation", () => {
    test("calls Bonuscard audit after a new sale-order conversion", async () => {
        applyMockFinalizeSaleOrderFromPos((validation) => {
            validation.order.uiState.saleOrderConverted = true;
            return true;
        });
        applyBonuscardSaleOrderBridgePatch();

        const order = { uiState: {} };
        const audited = [];
        const validation = makeValidation({
            order,
            applyAudit: async (o) => {
                audited.push(o);
            },
        });

        const result = await validation.finalizeSaleOrderFromPos();
        expect(result).toBe(true);
        expect(audited.length).toBe(1);
        expect(audited[0]).toBe(order);
    });

    test("does not call Bonuscard audit when already converted", async () => {
        applyMockFinalizeSaleOrderFromPos(() => true);
        applyBonuscardSaleOrderBridgePatch();

        const order = { uiState: { saleOrderConverted: true } };
        let auditCalls = 0;
        const validation = makeValidation({
            order,
            applyAudit: async () => {
                auditCalls += 1;
            },
        });

        const result = await validation.finalizeSaleOrderFromPos();
        expect(result).toBe(true);
        expect(auditCalls).toBe(0);
    });

    test("does not call Bonuscard audit when sale-order conversion fails", async () => {
        applyMockFinalizeSaleOrderFromPos(() => false);
        applyBonuscardSaleOrderBridgePatch();

        const order = { uiState: {} };
        let auditCalls = 0;
        const validation = makeValidation({
            order,
            applyAudit: async () => {
                auditCalls += 1;
            },
        });

        const result = await validation.finalizeSaleOrderFromPos();
        expect(result).toBe(false);
        expect(order.uiState.saleOrderConverted).toBe(undefined);
        expect(auditCalls).toBe(0);
    });
});
