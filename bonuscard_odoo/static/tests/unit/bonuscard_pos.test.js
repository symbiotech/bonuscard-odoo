/** @odoo-module */

import { test, expect } from "@odoo/hoot";
import { setupPosEnv, getFilledOrder } from "@point_of_sale/../tests/unit/utils";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { patchTranslations, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import * as makeAwaitableDialog from "@point_of_sale/app/utils/make_awaitable_dialog";
import { BonuscardRegistrationService } from "../../src/app/bonuscard_registration_service";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { runAllTimers } from "@odoo/hoot-mock";

// Ensure the Bonuscard POS patches are loaded for this test suite.
import "../../src/app/bonuscard_pos";
definePosModels();

// Mock translations for tests
patchTranslations({
    bonuscard_odoo: {
        "Bonuscard registration failed.": "Bonuscard registration failed.",
        "A phone number is required to register a customer with Bonuscard.": "A phone number is required to register a customer with Bonuscard.",
        "Bonuscard registration completed.": "Bonuscard registration completed.",
        "Could not cancel the pending Bonuscard transaction. The order has been kept so you can retry cancellation.":
            "Could not cancel the pending Bonuscard transaction. The order has been kept so you can retry cancellation.",
        "Could not cancel the pending Bonuscard transaction before closing. It may remain locked until it expires.":
            "Could not cancel the pending Bonuscard transaction before closing. It may remain locked until it expires.",
        "Payment succeeded but Bonuscard could not commit the discount. The loyalty transaction is still pending.":
            "Payment succeeded but Bonuscard could not commit the discount. The loyalty transaction is still pending.",
        "Payment succeeded but Bonuscard could not release the pending transaction. The customer may remain locked.":
            "Payment succeeded but Bonuscard could not release the pending transaction. The customer may remain locked.",
        "Could not release the pending Bonuscard transaction. The customer may remain locked until it expires.":
            "Could not release the pending Bonuscard transaction. The customer may remain locked until it expires.",
        "Bonuscard discount has been applied to the order.":
            "Bonuscard discount has been applied to the order.",
    }
});

function mockValidatePurchaseWithDiscount(store, product) {
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });
}

function stubSuperClosePosSideEffects(store) {
    // Unit-test demo session is in opening_control; super.closePos() then calls ORM
    // methods (e.g. delete_opening_control_session) that the mock server lacks.
    store.session.state = "opened";
    patchWithCleanup(store, {
        pushOrdersWithClosingPopup: async () => true,
        redirectToBackend: () => {},
    });
}

function patchBonuscardCancelCall(store, handler) {
    patchWithCleanup(store.data, {
        call: async (model, method, args, kwargs) => {
            const result = await handler(model, method, args, kwargs);
            if (result !== undefined) {
                return result;
            }
            return {};
        },
    });
}

function stubAfterOrderValidationSideEffects(store) {
    patchWithCleanup(store, {
        checkPreparationStateAndSentOrderInPreparation: () => {},
        printReceipt: async () => {},
    });
}

function createPaymentValidation(store, order) {
    return new OrderPaymentValidation({
        pos: store,
        orderUuid: order.uuid,
    });
}

test("BonuscardRegistrationService.registerPartnerToBonuscard calls the backend, executes the returned action, and refreshes partner status", async () => {
    const partner = { id: 42, name: "New Customer", phone: "+1234567890" };
    const calls = [];
    const actions = [];
    const notifications = [];
    const fakeNotification = { add: (message, options) => notifications.push({ message, options }) };
    const fakeAction = { doAction: (action) => actions.push(action) };
    const fakeEnv = {};
    const fakePos = {
        data: {
            call: async (model, method, args) => {
                calls.push({ model, method, args });
                if (method === "action_register_to_bonuscard") {
                    return {
                        type: "ir.actions.client",
                        tag: "display_notification",
                        params: { message: "Customer registered successfully.", type: "success", sticky: false },
                    };
                }
                if (method === "get_bonuscard_status_for_pos") {
                    return { status: "linked", recruitment_code: "REG123", note: "" };
                }
                throw new Error(`Unexpected RPC: ${model}.${method}`);
            },
        },
    };

    const service = new BonuscardRegistrationService(fakeEnv, { notification: fakeNotification, action: fakeAction });
    await service.registerPartnerToBonuscard(partner, fakePos);

    expect(calls).toEqual([
        {
            model: "res.partner",
            method: "action_register_to_bonuscard",
            args: [[partner.id]],
        },
        {
            model: "res.partner",
            method: "get_bonuscard_status_for_pos",
            args: [partner.id],
        },
    ]);
    expect(actions.length).toBe(1);
    expect(actions[0].tag).toBe("display_notification");
    expect(notifications.length).toBe(0);
    expect(partner.bonuscard_status).toBe("linked");
    expect(partner.bonuscard_recruitment_code).toBe("REG123");
});

test("BonuscardRegistrationService.registerPartnerToBonuscard shows warning when partner has no phone", async () => {
    const partner = { id: 99, name: "No Phone Customer" };
    const notifications = [];
    const calls = [];
    const fakeNotification = { add: (message, options) => notifications.push({ message, options }) };
    const fakeAction = { doAction: () => { } };
    const fakePos = { data: { call: async (...args) => { calls.push(args); return {}; } } };

    const service = new BonuscardRegistrationService({}, { notification: fakeNotification, action: fakeAction });
    await service.registerPartnerToBonuscard(partner, fakePos);

    expect(calls.length).toBe(0);
    expect(notifications.length).toBe(1);
    expect(notifications[0].options.type).toBe("warning");
});

test("_extractErrorMessage extracts meaningful error messages from various error formats", () => {
    const fakeEnv = {};
    const fakeNotification = { add: () => { } };
    const service = new BonuscardRegistrationService(fakeEnv, { notification: fakeNotification, action: {} });

    // Direct error message
    expect(service._extractErrorMessage({ message: "Partner has no phone number" })).toBe("Partner has no phone number");

    // Odoo RPC error data.message
    expect(service._extractErrorMessage({ data: { message: "No active Bonuscard connection" } })).toBe("No active Bonuscard connection");

    // Odoo exception arguments (first argument)
    expect(service._extractErrorMessage({ data: { arguments: ["Bonuscard API error (409)"] } })).toBe("Bonuscard API error (409)");

    // Fallback for "Odoo Server Error"
    expect(service._extractErrorMessage({ message: "Odoo Server Error", data: { message: "Odoo Server Error", arguments: ["Meaningful error text"] } })).toBe("Meaningful error text");

    // Fallback when no error
    expect(service._extractErrorMessage(null)).toBe("Bonuscard registration failed.");
});

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
    product.barcode = "TEST-MULTI-123";

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

    // Initialize discount to 0 to ensure it's a number (not undefined)
    line1.discount = line1.discount ?? 0;
    line2.discount = line2.discount ?? 0;

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

test("_applyBonuscardDiscountsToOrder applies proportional line discount when quantity exceeds discount coverage and no discount product is configured", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    store.config.discount_product_id = false;

    const product = store.models["product.product"].get(5);
    product.barcode = "TEST-PARTIAL-123";

    const line = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 5,
            price_unit: 10,
        },
        order
    );
    line.discount = 0;

    const result = {
        checkoutItems: [
            {
                identifier: "ITEM1",
                ean: product.barcode,
                quantity: 5,
                pricePerItem: 10,
            },
        ],
        resultItems: [
            {
                quantity: 2,
                pricePerItem: -2,
                relatedIdentifiers: ["ITEM1"],
            },
        ],
    };

    const applied = await store._applyBonuscardDiscountsToOrder(order, result);

    expect(applied).toBe(true);
    expect(line.discount).toBe(8);
});

test("_applyBonuscardDiscountsToOrder adds discount product line for partial coverage when discount product is configured", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const product = store.models["product.product"].get(5);
    const discountProduct = store.models["product.product"].get(6);
    product.barcode = "TEST-PARTIAL-DP-123";
    store.config.discount_product_id = discountProduct;

    const line = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 5,
            price_unit: 10,
        },
        order
    );
    line.discount = 0;

    const result = {
        checkoutItems: [
            {
                identifier: "ITEM1",
                ean: product.barcode,
                quantity: 5,
                pricePerItem: 10,
            },
        ],
        resultItems: [
            {
                quantity: 2,
                pricePerItem: -2,
                relatedIdentifiers: ["ITEM1"],
            },
        ],
    };

    const applied = await store._applyBonuscardDiscountsToOrder(order, result);

    expect(applied).toBe(true);
    expect(line.discount).toBe(0);

    const bonuscardDiscountLines = order.lines.filter(
        (orderLine) =>
            orderLine.uiState?._bonuscardLine && orderLine.product_id?.id === discountProduct.id
    );
    expect(bonuscardDiscountLines.length).toBe(1);
    expect(bonuscardDiscountLines[0].qty).toBe(2);
    expect(bonuscardDiscountLines[0].price_unit).toBe(-2);
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner);

    expect(order.lines[0].discount).toBe(20);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
});

test("setPartnerToCurrentOrder skips re-validation when the same customer is re-selected", async () => {
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    let validateCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                validateCallCount++;
                return {
                    transactionIdentifier: "TXN1",
                    checkoutItems: [
                        {
                            identifier: "ITEM1",
                            ean: product.barcode,
                            quantity: 1,
                            pricePerItem: 10,
                        },
                    ],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner);
    expect(validateCallCount).toBe(1);
    expect(order.bonuscard_needs_validation).toBe(false);

    await store.setPartnerToCurrentOrder(partner);

    expect(validateCallCount).toBe(1);
    expect(order.bonuscard_needs_validation).toBe(false);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
});

test("validatePurchaseForOrder retains existing transactionIdentifier when API response omits it", async () => {
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    order.bonuscard_transaction_id = "TXN1";

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

    const result = await store._validateBonuscardPurchaseForOrder(order);

    expect(result).toBe(true);
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner);

    expect(order.bonuscard_transaction_id).toBe("TXN1");
    line.setQuantity(2);
    expect(order.bonuscard_needs_validation).toBe(true);
    expect(order.bonuscard_checkout_items).toBe(null);
});

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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner);

    expect(order.bonuscard_transaction_id).toBe("TXN1");
    order.removeOrderline(line);
    expect(order.bonuscard_needs_validation).toBe(true);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("addLineToOrder re-validation does not show discount success toast", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    mockValidatePurchaseWithDiscount(store, product);

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    const line = await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    expect(line.discount).toBe(20);
    expect(
        notifications.filter(
            (n) =>
                n.message === "Bonuscard discount has been applied to the order." &&
                n.options.type === "success"
        )
    ).toEqual([]);
});

test("setPartnerToCurrentOrder shows discount success toast when discount is applied", async () => {
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    mockValidatePurchaseWithDiscount(store, product);

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    await store.setPartnerToCurrentOrder(partner);

    expect(
        notifications.filter(
            (n) =>
                n.message === "Bonuscard discount has been applied to the order." &&
                n.options.type === "success"
        ).length
    ).toBe(1);
});

test("addLineToOrder validates Bonuscard purchase after customer is selected", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    await store.setPartnerToCurrentOrder(partner);

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
                    transactionIdentifier: "TXN2",
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

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
    });
    partner1.bonuscard_recruitment_code = "ABC123";
    partner1.bonuscard_status = "linked";
    const partner2 = store.models["res.partner"].create({
        name: "Other Customer",
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                            quantity: 1,
                            pricePerItem: -2,
                            relatedIdentifiers: ["ITEM1"],
                        },
                    ],
                };
            }
            if (model === "res.partner" && method === "get_bonuscard_status_for_pos") {
                return {
                    status: "not_found",
                    recruitment_code: false,
                    note: "Customer is not linked",
                };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner1);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    expect(order.lines[0].discount).toBe(20);

    await store.setPartnerToCurrentOrder(partner2);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.lines[0].discount).toBe(0);
});

test("changing partner cancels the open Bonuscard transaction before clearing it", async () => {
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

    const partner1 = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner1.bonuscard_recruitment_code = "ABC123";
    partner1.bonuscard_status = "linked";
    const partner2 = store.models["res.partner"].create({
        name: "Other Customer",
    });

    let cancelledId = null;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
                    transactionIdentifier: "TXN1",
                    checkoutItems: [],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            if (model === "res.partner" && method === "get_bonuscard_status_for_pos") {
                return {
                    status: "not_found",
                    recruitment_code: false,
                    note: "Customer is not linked",
                };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner1);
    expect(order.bonuscard_transaction_id).toBe("TXN1");

    await store.setPartnerToCurrentOrder(partner2);
    expect(cancelledId).toBe("TXN1");
    expect(order.bonuscard_transaction_id).toBe(null);
});

test("changing partner keeps transaction state when cancel returns an error", async () => {
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

    const partner1 = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner1.bonuscard_recruitment_code = "ABC123";
    partner1.bonuscard_status = "linked";
    const partner2 = store.models["res.partner"].create({
        name: "Other Customer",
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
                    transactionIdentifier: "TXN1",
                    checkoutItems: [],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            if (model === "res.partner" && method === "get_bonuscard_status_for_pos") {
                return {
                    status: "not_found",
                    recruitment_code: false,
                    note: "Customer is not linked",
                };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return {
                    error: true,
                    messages: ["Bonuscard service is temporarily unavailable."],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner1);
    expect(order.bonuscard_transaction_id).toBe("TXN1");

    await store.setPartnerToCurrentOrder(partner2);
    // Cancel failure must block the partner change to avoid orphaning the Bonuscard lock.
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    expect(order.bonuscard_partner_id).toBe(partner1.id);
});

test("removing partner cancels the open Bonuscard transaction before clearing it", async () => {
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    let cancelledId = null;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
                    transactionIdentifier: "TXN1",
                    checkoutItems: [],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    await store.setPartnerToCurrentOrder(partner);
    expect(order.bonuscard_transaction_id).toBe("TXN1");

    await store.setPartnerToCurrentOrder(null);
    expect(cancelledId).toBe("TXN1");
    expect(order.bonuscard_transaction_id).toBe(null);
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
    // uiState._bonuscardLine must be set by addLineToOrder automatically — no manual override.

    order.clearBonuscardDiscounts();

    expect(order.lines.includes(discountLine)).toBe(false);
    expect(line.discount).toBe(0);
    expect(line.uiState?._bonuscardDiscount).toBe(undefined);
});

test("addLineToOrder marks discount lines so subsequent validation can clear them", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "TEST-MARK-123";

    // Add a product line before setting partner so no validation fires during setup.
    await store.addLineToOrder(
        { product_id: product, product_tmpl_id: product.product_tmpl_id, qty: 1, price_unit: 10 },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    // Simulate a discount line that a previous validation had applied.
    // Using _bonuscardLine:true so addLineToOrder returns early without re-triggering validation.
    const discountLine = await store.addLineToOrder(
        { product_id: product, product_tmpl_id: product.product_tmpl_id, qty: 1, price_unit: -5 },
        order,
        { _bonuscardLine: true },
        false
    );
    // The fix: addLineToOrder must set the flag automatically so clearing can find the line.
    expect(discountLine?.uiState?._bonuscardLine).toBe(true);

    // Run a second validation (returns no discounts so no new lines are added).
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return { transactionIdentifier: "TXN1", checkoutItems: [], totalDiscount: 0, resultItems: [] };
            }
            return originalCall(...arguments);
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    // The stale discount line from before must have been cleared by _clearAppliedBonuscardDiscounts.
    expect(order.lines.includes(discountLine)).toBe(false);
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
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

test("pay always revalidates Bonuscard purchase before payment", async () => {
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_needs_validation = false;

    let validationCalled = false;
    store._validateBonuscardPurchaseForOrder = async () => {
        validationCalled = true;
        return true;
    };

    await store.pay();
    expect(validationCalled).toBe(true);
});

test("pay revalidates Bonuscard purchase even after discounts were applied", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = product.barcode || "TEST-123";

    // Configure a discount product so _applyBonuscardDiscountsToOrder can call
    // addLineToOrder (and thus internally setQuantity) when remaining qty > 0.
    store.config.discount_product_id = product;

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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
                    transactionIdentifier: "TXN1",
                    checkoutItems: [
                        { identifier: "ITEM1", ean: product.barcode, quantity: 1, pricePerItem: 10 },
                    ],
                    totalDiscount: 4,
                    resultItems: [
                        // quantity: 2 exceeds the single orderline's qty: 1, so after
                        // setDiscount on the matched line the remaining 1 unit is covered
                        // via addLineToOrder, which internally calls setQuantity.
                        // Without the _bonuscardApplying guard that would re-arm
                        // bonuscard_needs_validation and cause a redundant API call on pay().
                        { quantity: 2, pricePerItem: -2, relatedIdentifiers: ["ITEM1"] },
                    ],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    // After a successful validation with discounts applied, needs_validation must remain false.
    expect(order.bonuscard_needs_validation).toBe(false);
    expect(order.bonuscard_transaction_id).toBe("TXN1");

    // Confirm pay() still revalidates before payment.
    let revalidationCalled = false;
    store._validateBonuscardPurchaseForOrder = async () => {
        revalidationCalled = true;
        return true;
    };

    await store.pay();
    expect(revalidationCalled).toBe(true);
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    await store.setPartnerToCurrentOrder(partner);

    patchWithCleanup(makeAwaitableDialog, {
        ask: async () => true,
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return {
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
                };
            }
            return originalCall(...arguments);
        },
    });

    await store.pay();

    expect(order.lines[0].discount).toBe(20);
    expect(order.payment_ids.length).toBe(0);
});

test("validatePurchaseForOrder excludes zero-price lines from the Bonuscard API payload", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "PRICED-BARCODE";

    // Normal priced line
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    // Zero-price line (e.g. a campaign product with price 0)
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 0,
        },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    let capturedLines = null;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                capturedLines = args[1];
                return { transactionIdentifier: "TXN1", checkoutItems: [], totalDiscount: 0, resultItems: [] };
            }
            return originalCall(...arguments);
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    expect(capturedLines).not.toBe(null);
    expect(capturedLines.length).toBe(1);
    expect(capturedLines[0].price_unit).toBe(10);
});

test("validatePurchaseForOrder returns false and skips the API call when all lines have zero price", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "ZERO-ONLY-BARCODE";

    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 0,
        },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    let apiCalled = false;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                apiCalled = true;
            }
            return originalCall(...arguments);
        },
    });

    const result = await store._validateBonuscardPurchaseForOrder(order);

    expect(result).toBe(false);
    expect(apiCalled).toBe(false);
});

test("_cancelBonuscardPurchaseForOrder makes exactly two cancel API calls when retries is 1 and cancel always fails", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_transaction_id = "TXN-RETRY";
    order.bonuscard_partner_id = false;

    let cancelCallCount = 0;
    patchWithCleanup(store.data, {
        call: async function (model, method) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelCallCount++;
                return { error: true, messages: ["Temporary failure"] };
            }
            return {};
        },
    });

    const result = await store._cancelBonuscardPurchaseForOrder(order, { retries: 1 });

    // retries: 1 means one initial attempt plus one retry = 2 total calls.
    expect(cancelCallCount).toBe(2);
    expect(result.success).toBe(false);
});

test("onDeleteOrder blocks order deletion, keeps transaction state, and adds sticky warning when cancel fails", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = 42;

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: true, messages: ["Bonuscard service unavailable"] };
            }
            return originalCall(...arguments);
        },
    });

    await store.onDeleteOrder(order);

    // Order deletion is blocked: the early return prevents super.onDeleteOrder from running,
    // so transaction state must remain intact.
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    expect(order.bonuscard_checkout_items).not.toBe(null);
    // A sticky warning notification must have been shown.
    expect(notifications.length).toBe(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("onDeleteOrder retries cancel once (two API calls total) before blocking deletion", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_partner_id = false;

    let cancelCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelCallCount++;
                return { error: true, messages: ["fail"] };
            }
            return originalCall(...arguments);
        },
    });

    await store.onDeleteOrder(order);

    // onDeleteOrder passes retries: 1, so the helper must attempt cancellation twice.
    expect(cancelCallCount).toBe(2);
    // Deletion must still be blocked.
    expect(order.bonuscard_transaction_id).toBe("TXN1");
});

test("closePos keeps transaction state and adds sticky warning when cancel fails", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = 42;

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    // Stub the cancel helper to return failure; this isolates the closePos
    // failure-handling logic from the _cancelBonuscardPurchaseForOrder internals.
    store._cancelBonuscardPurchaseForOrder = async () => ({
        success: false,
        message: "Bonuscard service unavailable",
    });

    stubSuperClosePosSideEffects(store);
    patchWithCleanup(store.data, {
        call: async () => ({}),
    });

    await store.closePos();

    // State must NOT have been cleared — the transaction lock must remain intact.
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    // A sticky warning notification must have been shown.
    expect(notifications.length).toBe(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("closePos retries cancel once (two API calls total) before continuing with POS close", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_partner_id = false;

    let cancelCallCount = 0;
    stubSuperClosePosSideEffects(store);
    patchBonuscardCancelCall(store, (model, method) => {
        if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
            cancelCallCount++;
            return { error: true, messages: ["fail"] };
        }
    });

    await store.closePos();

    // closePos passes retries: 1, so the helper must attempt cancellation twice.
    expect(cancelCallCount).toBe(2);
});

test("onDeleteOrder clears bonuscard transaction state after cancelling", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = partner.id;

    let cancelledId = null;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false, messages: [] };
            }
            if (model === "pos.order" && method === "action_pos_order_cancel") {
                return true;
            }
            return originalCall(...arguments);
        },
    });

    await store.onDeleteOrder(order);

    expect(cancelledId).toBe("TXN1");
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
    expect(order.bonuscard_partner_id).toBe(false);
});

test("onDeleteOrder keeps order and transaction state when cancel fails after retry", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = partner.id;

    let cancelCallCount = 0;
    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelCallCount++;
                return {
                    error: true,
                    messages: ["Bonuscard service is temporarily unavailable."],
                };
            }
            return originalCall(...arguments);
        },
    });

    const deleted = await store.onDeleteOrder(order);

    expect(cancelCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe("TXN1");
    expect(order.bonuscard_checkout_items).not.toBe(null);
    expect(order.bonuscard_partner_id).toBe(partner.id);
    expect(deleted).toBe(undefined);
    expect(notifications.length).toBe(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("onDeleteOrder retries cancel once before clearing transaction state", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = partner.id;

    let cancelCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelCallCount++;
                if (cancelCallCount === 1) {
                    return { error: true, messages: ["Temporary Bonuscard outage."] };
                }
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    const deleted = await store.onDeleteOrder(order);

    expect(cancelCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
    expect(order.bonuscard_partner_id).toBe(false);
    expect(deleted).toBe(true);
    expect(order.uiState.displayed).toBe(false);
});

test("closePos keeps transaction state when cancel fails after retry", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    order.bonuscard_transaction_id = "TXN-CLOSE";
    order.bonuscard_checkout_items = [{ ean: "TEST-456", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = partner.id;

    let cancelCallCount = 0;
    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    stubSuperClosePosSideEffects(store);
    patchBonuscardCancelCall(store, (model, method) => {
        if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
            cancelCallCount++;
            return {
                error: true,
                messages: ["Bonuscard service is temporarily unavailable."],
            };
        }
    });

    await store.closePos();

    expect(cancelCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe("TXN-CLOSE");
    expect(order.bonuscard_checkout_items).not.toBe(null);
    expect(order.bonuscard_partner_id).toBe(partner.id);
    expect(notifications.length).toBe(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("closePos retries cancel once before clearing transaction state", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();

    const partner = store.models["res.partner"].create({
        name: "Bonuscard Customer",
    });
    order.bonuscard_transaction_id = "TXN-CLOSE-RETRY";
    order.bonuscard_checkout_items = [{ ean: "TEST-789", quantity: 1, pricePerItem: 10 }];
    order.bonuscard_partner_id = partner.id;

    let cancelCallCount = 0;
    stubSuperClosePosSideEffects(store);
    patchBonuscardCancelCall(store, (model, method) => {
        if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
            cancelCallCount++;
            if (cancelCallCount === 1) {
                return { error: true, messages: ["Temporary Bonuscard outage."] };
            }
            return { error: false, messages: [] };
        }
    });

    await store.closePos();

    expect(cancelCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
    expect(order.bonuscard_partner_id).toBe(false);
});

test("afterOrderValidation clears Bonuscard transaction state on successful finalize", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-FINALIZE";
    order.bonuscard_checkout_items = [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }];

    let finalizedArgs = null;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizedArgs = args;
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    await validation.afterOrderValidation();

    expect(finalizedArgs).toEqual([
        42,
        "TXN-FINALIZE",
        [{ ean: "TEST-123", quantity: 1, pricePerItem: 10 }],
    ]);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("afterOrderValidation retries finalize once before clearing transaction state", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-FINALIZE-RETRY";
    order.bonuscard_checkout_items = [{ ean: "TEST-456", quantity: 1, pricePerItem: 10 }];

    let finalizeCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizeCallCount++;
                if (finalizeCallCount === 1) {
                    return { error: true, messages: ["Temporary Bonuscard outage."] };
                }
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    const finalizePromise = validation.afterOrderValidation();
    await runAllTimers();
    await finalizePromise;

    expect(finalizeCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("afterOrderValidation keeps transaction state when finalize fails after retry", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-FINALIZE-FAIL";
    order.bonuscard_checkout_items = [{ ean: "TEST-789", quantity: 1, pricePerItem: 10 }];

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    let finalizeCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizeCallCount++;
                return {
                    error: true,
                    messages: ["Bonuscard service is temporarily unavailable."],
                };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: true, messages: ["Bonuscard cancel failed."] };
            }
            return originalCall(...arguments);
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    const finalizePromise = validation.afterOrderValidation();
    await runAllTimers();
    await finalizePromise;

    expect(finalizeCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe("TXN-FINALIZE-FAIL");
    expect(order.bonuscard_checkout_items).not.toBe(null);
    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe(
        "Payment succeeded but Bonuscard could not commit the discount. The loyalty transaction is still pending. (Bonuscard service is temporarily unavailable.)"
    );
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("afterOrderValidation shows payment-succeeded warning without API detail when finalize returns no message", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-FINALIZE-NO-MSG";
    order.bonuscard_checkout_items = [{ ean: "TEST-000", quantity: 1, pricePerItem: 10 }];

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });

    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                return { error: true, messages: [] };
            }
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: true, messages: ["Bonuscard cancel failed."] };
            }
            return originalCall(...arguments);
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    const finalizePromise = validation.afterOrderValidation();
    await runAllTimers();
    await finalizePromise;

    expect(order.bonuscard_transaction_id).toBe("TXN-FINALIZE-NO-MSG");
    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe(
        "Payment succeeded but Bonuscard could not commit the discount. The loyalty transaction is still pending."
    );
});

test("afterOrderValidation retries finalize once when the RPC throws", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-FINALIZE-THROW";
    order.bonuscard_checkout_items = [{ ean: "TEST-321", quantity: 1, pricePerItem: 10 }];

    let finalizeCallCount = 0;
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizeCallCount++;
                if (finalizeCallCount === 1) {
                    throw new Error("Network error");
                }
                return { error: false, messages: [] };
            }
            return originalCall(...arguments);
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    const finalizePromise = validation.afterOrderValidation();
    await runAllTimers();
    await finalizePromise;

    expect(finalizeCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("concurrent validations: only the latest call applies its discounts, stale calls are discarded", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "TEST-CONCURRENT-123";

    // Add a line before setting the partner so no validation fires during setup.
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    // Use setPartner directly to avoid triggering validation during setup.
    order.setPartner(partner);

    let apiCallCount = 0;
    const resolvers = [];
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                apiCallCount++;
                // Return a manually-controlled promise so we can interleave resolutions.
                return new Promise((resolve) => resolvers.push(resolve));
            }
            return originalCall(...arguments);
        },
    });

    // Start two concurrent validations without awaiting either.
    const p1 = store._validateBonuscardPurchaseForOrder(order);
    const p2 = store._validateBonuscardPurchaseForOrder(order);

    // Both API calls must have been initiated synchronously before any await settled.
    expect(apiCallCount).toBe(2);
    expect(resolvers.length).toBe(2);

    const makeResult = (txnId) => ({
        transactionIdentifier: txnId,
        checkoutItems: [
            { identifier: "ITEM1", ean: product.barcode, quantity: 1, pricePerItem: 10 },
        ],
        totalDiscount: 2,
        resultItems: [{ quantity: 1, pricePerItem: -2, relatedIdentifiers: ["ITEM1"] }],
    });

    // Resolve the stale call first, then the latest call.
    resolvers[0](makeResult("TXN-STALE"));
    resolvers[1](makeResult("TXN-LATEST"));

    await p1;
    await p2;

    // Only the latest result should have been applied: exactly one discounted line.
    const discountedLines = order.lines.filter(
        (l) => l.discount > 0 || l.uiState?._bonuscardLine
    );
    expect(discountedLines.length).toBe(1);
    // The transaction ID must come from the latest call, not the stale one.
    expect(order.bonuscard_transaction_id).toBe("TXN-LATEST");
});

test("addNewOrder cancels the pending Bonuscard transaction on the order being left", async () => {
    const store = await setupPosEnv();
    const order1 = store.addNewOrder();
    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order1.bonuscard_transaction_id = "TXN-OLD";
    order1.bonuscard_partner_id = partner.id;

    let cancelledId = null;
    let cancelLeavingDone;
    const origLeaving = store._cancelBonuscardPurchaseWhenLeavingOrder.bind(store);
    patchWithCleanup(store, {
        _cancelBonuscardPurchaseWhenLeavingOrder(order, logMethod) {
            cancelLeavingDone = origLeaving(order, logMethod);
            return cancelLeavingDone;
        },
    });
    patchWithCleanup(store.data, {
        call: async (model, method, args) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false };
            }
            return {};
        },
    });

    const order2 = store.addNewOrder();
    await cancelLeavingDone;

    expect(cancelledId).toBe("TXN-OLD");
    expect(order1.bonuscard_transaction_id).toBe(null);
    expect(order2).not.toBe(order1);
});

test("concurrent validations share the same client-generated transaction identifier", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "TEST-SHARED-TXID";

    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    const sentIdentifiers = [];
    const resolvers = [];
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                sentIdentifiers.push(args[2]);
                return new Promise((resolve) => resolvers.push(resolve));
            }
            return originalCall(...arguments);
        },
    });

    // Simulate "add product then immediately edit quantity": two validations
    // start before the first response arrives.
    const p1 = store._validateBonuscardPurchaseForOrder(order);
    const p2 = store._validateBonuscardPurchaseForOrder(order);

    expect(sentIdentifiers.length).toBe(2);
    // Both requests must carry the SAME non-null identifier, otherwise the
    // second one would hit Bonuscard error 2 (customer locked).
    expect(sentIdentifiers[0]).not.toBe(null);
    expect(sentIdentifiers[1]).toBe(sentIdentifiers[0]);

    const result = {
        transactionIdentifier: sentIdentifiers[0],
        checkoutItems: [],
        totalDiscount: 0,
        resultItems: [],
    };
    resolvers[0](result);
    resolvers[1](result);
    await p1;
    await p2;

    expect(order.bonuscard_transaction_id).toBe(sentIdentifiers[0]);
});

test("stale concurrent validation result still stores the transaction identifier so the lock can be cancelled", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const product = store.models["product.product"].get(5);
    product.barcode = "TEST-STALE-CAPTURE";

    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);

    const resolvers = [];
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method) {
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                return new Promise((resolve) => resolvers.push(resolve));
            }
            return originalCall(...arguments);
        },
    });

    const p1 = store._validateBonuscardPurchaseForOrder(order);
    const p2 = store._validateBonuscardPurchaseForOrder(order);

    // Resolve only the stale (first) call with a transaction ID; leave the
    // latest call to fail so the order would otherwise have no identifier.
    resolvers[0]({
        transactionIdentifier: "TXN-FROM-STALE",
        checkoutItems: [],
        totalDiscount: 0,
        resultItems: [],
    });
    resolvers[1]({ error: true, messages: ["Bonuscard validation failed."] });
    await p1;
    await p2;

    // The stale result's transaction ID must have been captured, not discarded.
    expect(order.bonuscard_transaction_id).toBe("TXN-FROM-STALE");
});

test("validation recovers from customer lock by cancelling orphaned transactions on other orders", async () => {
    const store = await setupPosEnv();
    const product = store.models["product.product"].get(5);
    product.barcode = "LOCK-RECOVERY-123";

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const orphanedOrder = store.addNewOrder();
    const order = store.addNewOrder();
    // Assign the orphaned transaction only after switching orders, so the
    // addNewOrder background-cancel path does not clean it up during setup.
    orphanedOrder.bonuscard_transaction_id = "TXN-ORPHAN";
    orphanedOrder.bonuscard_partner_id = partner.id;
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );
    order.setPartner(partner);

    let validateCallCount = 0;
    let cancelledIds = [];
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledIds.push(args[0]);
                return { error: false };
            }
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                validateCallCount++;
                if (validateCallCount === 1) {
                    return {
                        error: true,
                        errorCode: 2,
                        messages: [
                            "Customer is locked to an open transaction. Please try again or restart.",
                        ],
                    };
                }
                return {
                    transactionIdentifier: "TXN-NEW",
                    checkoutItems: [
                        {
                            identifier: "ITEM1",
                            ean: product.barcode,
                            quantity: 1,
                            pricePerItem: 10,
                        },
                    ],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    // Two cancels: the current order's own candidate identifier and the
    // orphaned transaction held by the other draft order.
    expect(cancelledIds.length).toBe(2);
    expect(cancelledIds[1]).toBe("TXN-ORPHAN");
    expect(orphanedOrder.bonuscard_transaction_id).toBe(null);
    expect(validateCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe("TXN-NEW");
});

test("validation releases pending transaction when cart has no Bonuscard-eligible lines", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const product = store.models["product.product"].get(5);
    product.barcode = null;
    product.default_code = null;
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN-NO-EAN";
    order.bonuscard_partner_id = partner.id;
    order.bonuscard_checkout_items = [{ ean: "OLD", quantity: 1, pricePerItem: 10 }];

    let cancelledId = null;
    patchWithCleanup(store.data, {
        call: async (model, method, args) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false };
            }
            return {};
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    expect(cancelledId).toBe("TXN-NO-EAN");
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("afterOrderValidation releases pending transaction when checkout items are missing", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    order.bonuscard_transaction_id = "TXN-NO-FINALIZE";
    order.bonuscard_partner_id = partner.id;
    order.bonuscard_checkout_items = null;

    let cancelledId = null;
    let finalizeCalled = false;
    patchWithCleanup(store.data, {
        call: async (model, method, args) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false };
            }
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizeCalled = true;
            }
            return {};
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    await validation.afterOrderValidation();

    expect(cancelledId).toBe("TXN-NO-FINALIZE");
    expect(finalizeCalled).toBe(false);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("afterOrderValidation shows sticky warning when release fails after payment", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    order.bonuscard_transaction_id = "TXN-RELEASE-FAIL";
    order.bonuscard_partner_id = partner.id;
    order.bonuscard_checkout_items = null;

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });
    patchWithCleanup(store.data, {
        call: async (model, method) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: true, messages: ["Bonuscard cancel failed."] };
            }
            return {};
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    await validation.afterOrderValidation();

    expect(order.bonuscard_transaction_id).toBe("TXN-RELEASE-FAIL");
    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe(
        "Payment succeeded but Bonuscard could not release the pending transaction. The customer may remain locked. (Bonuscard cancel failed.)"
    );
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].options.sticky).toBe(true);
});

test("validation keeps transaction state when release fails for ineligible cart lines", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const product = store.models["product.product"].get(5);
    product.barcode = null;
    product.default_code = null;
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN-RELEASE-FAIL";
    order.bonuscard_partner_id = partner.id;

    const notifications = [];
    patchWithCleanup(store.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });
    patchWithCleanup(store.data, {
        call: async (model, method) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                return { error: true, messages: ["Bonuscard cancel failed."] };
            }
            return {};
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    expect(order.bonuscard_transaction_id).toBe("TXN-RELEASE-FAIL");
    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe(
        "Could not release the pending Bonuscard transaction. The customer may remain locked until it expires."
    );
    expect(notifications[0].options.sticky).toBe(false);
});

test("afterOrderValidation finalizes zero-discount transaction when checkout items exist", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.bonuscard_partner_id = 42;
    order.bonuscard_transaction_id = "TXN-ZERO";
    order.bonuscard_checkout_items = [{ ean: "TEST-999", quantity: 1, pricePerItem: 10 }];

    let cancelledId = null;
    let finalizeArgs = null;
    patchWithCleanup(store.data, {
        call: async (model, method, args) => {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledId = args[0];
                return { error: false };
            }
            if (model === "bonuscard.api.service" && method === "finalize_purchase_for_pos") {
                finalizeArgs = args;
                return { error: false };
            }
            return {};
        },
    });

    stubAfterOrderValidationSideEffects(store);
    const validation = createPaymentValidation(store, order);
    await validation.afterOrderValidation();

    expect(finalizeArgs).toEqual([
        42,
        "TXN-ZERO",
        [{ ean: "TEST-999", quantity: 1, pricePerItem: 10 }],
    ]);
    expect(cancelledId).toBe(null);
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_checkout_items).toBe(null);
});

test("validation recovers from customer lock by cancelling pending tx on finalized orders", async () => {
    const store = await setupPosEnv();
    const product = store.models["product.product"].get(5);
    product.barcode = "LOCK-PAID-123";

    const partner = store.models["res.partner"].create({ name: "Bonuscard Customer" });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";

    const paidOrder = store.addNewOrder();
    paidOrder.state = "paid";
    paidOrder.bonuscard_transaction_id = "TXN-PAID-ORPHAN";
    paidOrder.bonuscard_partner_id = partner.id;

    const order = store.addNewOrder();
    await store.addLineToOrder(
        {
            product_id: product,
            product_tmpl_id: product.product_tmpl_id,
            qty: 1,
            price_unit: 10,
        },
        order
    );
    order.setPartner(partner);

    let validateCallCount = 0;
    let cancelledIds = [];
    const originalCall = store.data.call.bind(store.data);
    patchWithCleanup(store.data, {
        call: async function (model, method, args) {
            if (model === "bonuscard.api.service" && method === "cancel_purchase_for_pos") {
                cancelledIds.push(args[0]);
                return { error: false };
            }
            if (model === "bonuscard.api.service" && method === "validate_purchase_for_pos") {
                validateCallCount++;
                if (validateCallCount === 1) {
                    return {
                        error: true,
                        errorCode: 2,
                        messages: [
                            "Customer is locked to an open transaction. Please try again or restart.",
                        ],
                    };
                }
                return {
                    transactionIdentifier: "TXN-NEW",
                    checkoutItems: [
                        {
                            identifier: "ITEM1",
                            ean: product.barcode,
                            quantity: 1,
                            pricePerItem: 10,
                        },
                    ],
                    totalDiscount: 0,
                    resultItems: [],
                };
            }
            return originalCall(...arguments);
        },
    });

    await store._validateBonuscardPurchaseForOrder(order);

    expect(cancelledIds.includes("TXN-PAID-ORPHAN")).toBe(true);
    expect(paidOrder.bonuscard_transaction_id).toBe(null);
    expect(validateCallCount).toBe(2);
    expect(order.bonuscard_transaction_id).toBe("TXN-NEW");
});
