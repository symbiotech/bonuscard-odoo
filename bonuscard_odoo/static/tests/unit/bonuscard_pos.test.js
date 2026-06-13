/** @odoo-module */

import { test, expect } from "@odoo/hoot";
import { setupPosEnv, getFilledOrder } from "@point_of_sale/../tests/unit/utils";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import * as makeAwaitableDialog from "@point_of_sale/app/utils/make_awaitable_dialog";

definePosModels();

test("_applyBonuscardDiscountsToOrder applies line discounts for matching identifiers", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);

    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    const line = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const result = {
        checkoutItems: [
            {
                identifier: "ITEM1",
                ean: product.barcode,
                quantity: 1,
                pricePerItem: 10,
            },
        ],
        resultItems: [
            {
                quantity: 1,
                pricePerItem: -2,
                relatedIdentifiers: ["ITEM1"],
            },
        ],
    };

    const applied = await store._applyBonuscardDiscountsToOrder(order, result);

    expect(applied).toBe(true);
    expect(line.discount).toBe(20);
});

test("_applyBonuscardDiscountsToOrder only consumes the configured quantity across matched lines", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);

    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    const line1 = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );
    const line2 = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const result = {
        resultItems: [
            {
                quantity: 1,
                pricePerItem: -2,
                relatedIdentifiers: [String(product.id)],
            },
        ],
    };

    const applied = await store._applyBonuscardDiscountsToOrder(order, result);

    expect(applied).toBe(true);
    expect(line1.discount + line2.discount).toBe(20);
    expect([line1.discount, line2.discount].filter((discount) => discount > 0).length).toBe(1);
});

test("pay applies Bonuscard discount and does not create a payment line when approved", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
        bonuscard_recruitment_code: "ABC123",
        bonuscard_status: "linked",
    });
    await store.setPartnerToCurrentOrder(partner);

    patchWithCleanup(makeAwaitableDialog, {
        ask: async () => true,
    });

    onRpc("bonuscard.api.service", "validate_purchase_for_pos", () => ({
        transactionIdentifier: "TXN1",
        checkoutItems: [],
        totalDiscount: 2,
        resultItems: [
            {
                quantity: 1,
                pricePerItem: -2,
                relatedIdentifiers: [String(product.id)],
            },
        ],
    }));

    await store.pay();

    expect(order.lines[0].discount).toBe(20);
    expect(order.payment_ids.length).toBe(0);
});
