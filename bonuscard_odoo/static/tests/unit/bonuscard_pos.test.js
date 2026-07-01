/** @odoo-module */

import { test, expect } from "@odoo/hoot";
import { setupPosEnv, getFilledOrder } from "@point_of_sale/../tests/unit/utils";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { patchTranslations, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import * as makeAwaitableDialog from "@point_of_sale/app/utils/make_awaitable_dialog";
import { BonuscardRegistrationService } from "../../src/app/bonuscard_registration_service";

// Ensure the Bonuscard POS patches are loaded for this test suite.
import "../../src/app/bonuscard_pos";
definePosModels();

// Mock translations for tests
patchTranslations({
    bonuscard_odoo: {
        "Bonuscard registration failed.": "Bonuscard registration failed.",
        "A phone number is required to register a customer with Bonuscard.": "A phone number is required to register a customer with Bonuscard.",
        "Bonuscard registration completed.": "Bonuscard registration completed.",
    }
});

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

test("changing partner clears transaction state even when cancel returns an error", async () => {
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
    // Partner change must proceed regardless of cancel failure.
    expect(order.bonuscard_transaction_id).toBe(null);
    expect(order.bonuscard_partner_id).toBe(partner2.id);
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
    discountLine.uiState = discountLine.uiState || {};
    discountLine.uiState._bonuscardLine = true;

    order.clearBonuscardDiscounts();

    expect(order.lines.includes(discountLine)).toBe(false);
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
    });
    partner.bonuscard_recruitment_code = "ABC123";
    partner.bonuscard_status = "linked";
    order.setPartner(partner);
    order.bonuscard_transaction_id = "TXN1";
    order.bonuscard_needs_validation = false;

    let validationCalled = false;
    store._validateBonuscardPurchaseForOrder = async () => {
        validationCalled = true;
        throw new Error("Unexpected validation call");
    };

    await store.pay();
    expect(validationCalled).toBe(false);
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
