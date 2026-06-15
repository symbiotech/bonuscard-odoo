/** @odoo-module */

import { test, expect } from "@odoo/hoot";
import { setupPosEnv, getFilledOrder } from "@point_of_sale/../tests/unit/utils";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import * as makeAwaitableDialog from "@point_of_sale/app/utils/make_awaitable_dialog";

// Ensure the Bonuscard POS patches are loaded for this test suite.
import "../../src/app/bonuscard_pos";
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
    expect(line1.discount + line2.discount).toBe(20);
    expect([line1.discount, line2.discount].filter((discount) => discount > 0).length).toBe(1);
});

test("setPartnerToCurrentOrder validates Bonuscard purchase and applies discount before payment", async () => {
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

    await store.setPartnerToCurrentOrder(partner);

    expect(order.lines[0].discount).toBe(20);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
});

test("quantity change clears pending Bonuscard transaction", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
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

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
        bonuscard_recruitment_code: "ABC123",
        bonuscard_status: "linked",
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

    await store.setPartnerToCurrentOrder(partner);

    expect(order.bonuscard_transaction_id).toBe("TXN1");
    line.setQuantity(2);
    expect(order.bonuscard_needs_validation).toBe(true);
    expect(order.bonuscard_checkout_items).toBeNull();

test("removing a line clears pending Bonuscard transaction", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
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

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
        bonuscard_recruitment_code: "ABC123",
        bonuscard_status: "linked",
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

    await store.setPartnerToCurrentOrder(partner);

    expect(order.bonuscard_transaction_id).toBe("TXN1");
    order.removeOrderline(line);
    expect(order.bonuscard_needs_validation).toBe(true);
    expect(order.bonuscard_checkout_items).toBeNull();

test("addLineToOrder validates Bonuscard purchase after customer is selected", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
        bonuscard_recruitment_code: "ABC123",
        bonuscard_status: "linked",
    });

    await store.setPartnerToCurrentOrder(partner);

    onRpc("bonuscard.api.service", "validate_purchase_for_pos", () => ({
        transactionIdentifier: "TXN2",
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

    const line = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    expect(order.bonuscard_transaction_id).toBe("TXN2");
    expect(line.discount).toBe(20);
});

test("changing partner clears pending Bonuscard transaction and discounts", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
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

    const partner1 = store.models["res.partner"].create({
        name: "Bonuscard Customer",
        bonuscard_recruitment_code: "ABC123",
        bonuscard_status: "linked",
    });
    const partner2 = store.models["res.partner"].create({
        name: "Other Customer",
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
    onRpc("res.partner", "get_bonuscard_status_for_pos", () => ({
        status: "not_found",
        recruitment_code: false,
        note: "Customer is not linked",
    }));

    await store.setPartnerToCurrentOrder(partner1);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    expect(order.lines[0].discount).toBe(20);

    await store.setPartnerToCurrentOrder(partner2);
    expect(order.bonuscard_transaction_id).toBeNull();
    expect(order.lines[0].discount).toBe(0);
});

test("clearBonuscardDiscounts removes bonuscard discount lines and resets applied discounts", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
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
    line.setDiscount(20);
    line.uiState = line.uiState || {};
    line.uiState._bonuscardDiscount = true;

    const discountLine = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: -2,
        },
        order,
        { _bonuscardLine: true },
        false
    );
    discountLine.uiState = discountLine.uiState || {};
    discountLine.uiState._bonuscardLine = true;

    order.clearBonuscardDiscounts();

    expect(order.lines).not.toContain(discountLine);
    expect(line.discount).toBe(0);
    expect(line.uiState?._bonuscardDiscount).toBe(undefined);
});

test("pay revalidates Bonuscard purchase when the order needs validation", async () => {
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
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_needs_validation = true;

    let called = false;
    store._validateBonuscardPurchaseForOrder = async (orderArg) => {
        called = true;
        return true;
    };

    await store.pay();
    expect(called).toBe(true);
});

test("pay does not revalidate Bonuscard purchase when no validation is needed", async () => {
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
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_needs_validation = false;

    store._validateBonuscardPurchaseForOrder = async () => {
        throw new Error("Unexpected validation call");
    };

    await store.pay();
});

test("OrderSummary revalidates Bonuscard order when quantity changes", async () => {
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

    let called = false;
    store._validateBonuscardPurchaseForOrder = async (orderArg) => {
        called = true;
        return true;
    };

    const fakeSummary = { currentOrder: order, pos: store };
    await OrderSummary.prototype._maybeRevalidateBonuscardOrder.call(fakeSummary);
    expect(called).toBe(true);
});

test("OrderSummary does not revalidate Bonuscard order when no partner is linked", async () => {
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

    let called = false;
    store._validateBonuscardPurchaseForOrder = async () => {
        called = true;
        return true;
    };

    const fakeSummary = { currentOrder: order, pos: store };
    await OrderSummary.prototype._maybeRevalidateBonuscardOrder.call(fakeSummary);
    expect(called).toBe(false);
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
        checkoutItems: [
            {
                identifier: "ITEM1",
                ean: product.barcode,
                quantity: 1,
                pricePerItem: 10,
            },
        ],
        totalDiscount: 2,
        resultItems: [
            {
                description: "Discount",
                quantity: 1,
                pricePerItem: -2,
                relatedIdentifiers: ["ITEM1"],
            },
        ],
    }));

    await store.pay();

    expect(order.lines[0].discount).toBe(20);
    expect(order.payment_ids.length).toBe(0);
});
