/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import { CreateOrderButton } from "@pos_order_to_sale_order/components/create_order_button/create_order_button.esm";
import { CreateOrderPopup } from "@pos_order_to_sale_order/components/create_order_popup/create_order_popup.esm";
import { applyBonuscardCreateSaleOrderUiPatches } from "@bonuscard_pos_order_to_sale_order/js/create_sale_order_ui_patch";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";

describe("bonuscard_pos_order_to_sale_order Create Sale Order UI patches", () => {
    test("one-shot CreateOrderButton routes through Bonuscard audit wrapper", async () => {
        const createCalls = [];
        let stopped = false;
        let closed = false;

        applyBonuscardCreateSaleOrderUiPatches(patchWithCleanup, {
            getDefaultCreateSaleOrderState: () => "confirmed",
            createSaleOrderFromPosWithBonuscardAudit: async (pos, orm, ui, orderState) => {
                createCalls.push({ pos, orm, ui, orderState });
            },
        });

        const button = Object.assign(Object.create(CreateOrderButton.prototype), {
            pos: { config: {} },
            orm: {},
            ui: {},
            props: {
                close: () => {
                    closed = true;
                },
            },
        });

        await button.onClick({
            stopPropagation: () => {
                stopped = true;
            },
        });

        expect(stopped).toBe(true);
        expect(createCalls.length).toBe(1);
        expect(createCalls[0].orderState).toBe("confirmed");
        expect(closed).toBe(true);
    });

    test("CreateOrderPopup routes through Bonuscard audit wrapper", async () => {
        const createCalls = [];
        let closed = false;

        applyBonuscardCreateSaleOrderUiPatches(patchWithCleanup, {
            createSaleOrderFromPosWithBonuscardAudit: async (pos, orm, ui, orderState) => {
                createCalls.push({ pos, orm, ui, orderState });
            },
        });

        const popup = Object.assign(Object.create(CreateOrderPopup.prototype), {
            pos: {},
            orm: {},
            ui: {},
            props: {
                close: () => {
                    closed = true;
                },
            },
        });

        await popup._actionCreateSaleOrder("draft");

        expect(createCalls.length).toBe(1);
        expect(createCalls[0].orderState).toBe("draft");
        expect(closed).toBe(true);
    });
});
