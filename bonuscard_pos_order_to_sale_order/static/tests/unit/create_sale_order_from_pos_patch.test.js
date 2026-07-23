/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import { createSaleOrderFromPosWithBonuscardAudit } from "@bonuscard_pos_order_to_sale_order/js/create_sale_order_from_pos_patch";

function makePos({ order, applyAudit }) {
    const calls = {
        create: [],
        audit: [],
        remove: [],
        addNew: 0,
    };
    const pos = {
        getOrder: () => order,
        _applyBonuscardAuditAfterPayment: async (o) => {
            calls.audit.push(o);
            if (applyAudit) {
                await applyAudit(o);
            }
        },
        removeOrder: (o) => {
            calls.remove.push(o);
        },
        addNewOrder: () => {
            calls.addNew += 1;
        },
    };
    return { pos, calls };
}

describe("bonuscard_pos_order_to_sale_order createSaleOrderFromPosWithBonuscardAudit", () => {
    test("audits then removes the order after a successful create", async () => {
        const order = { id: "order-1" };
        const { pos, calls } = makePos({ order });
        const createFn = async (_pos, _orm, _ui, orderState, options) => {
            calls.create.push({ orderState, options });
        };

        await createSaleOrderFromPosWithBonuscardAudit(
            pos,
            {},
            {},
            "confirmed",
            { createSaleOrderFromPosFn: createFn }
        );

        expect(calls.create.length).toBe(1);
        expect(calls.create[0].orderState).toBe("confirmed");
        expect(calls.create[0].options.removeOrder).toBe(false);
        expect(calls.audit.length).toBe(1);
        expect(calls.audit[0]).toBe(order);
        expect(calls.remove.length).toBe(1);
        expect(calls.remove[0]).toBe(order);
        expect(calls.addNew).toBe(1);
    });

    test("does not audit or remove when create fails", async () => {
        const order = { id: "order-2" };
        const { pos, calls } = makePos({ order });
        const createFn = async () => {
            throw new Error("create failed");
        };

        let thrown = false;
        try {
            await createSaleOrderFromPosWithBonuscardAudit(
                pos,
                {},
                {},
                "draft",
                { createSaleOrderFromPosFn: createFn }
            );
        } catch (error) {
            thrown = error.message === "create failed";
        }

        expect(thrown).toBe(true);
        expect(calls.audit.length).toBe(0);
        expect(calls.remove.length).toBe(0);
        expect(calls.addNew).toBe(0);
    });

    test("skips removeOrder when options.removeOrder is false", async () => {
        const order = { id: "order-3" };
        const { pos, calls } = makePos({ order });
        const createFn = async () => {};

        await createSaleOrderFromPosWithBonuscardAudit(
            pos,
            {},
            {},
            "invoiced",
            { removeOrder: false, createSaleOrderFromPosFn: createFn }
        );

        expect(calls.audit.length).toBe(1);
        expect(calls.remove.length).toBe(0);
        expect(calls.addNew).toBe(0);
    });
});
