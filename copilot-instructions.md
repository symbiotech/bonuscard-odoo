# Copilot Instructions for bonuscard_odoo

## Product Context

- This repository is an Odoo 19 addon for integrating Odoo with the Bonuscard platform.
- Bonuscard is used for loyalty and discount handling in e-commerce and point-of-sale flows.
- The API is designed around purchase validation before payment, purchase finalization after payment, and cancellation when a purchase is aborted.

## Confirmed Initial Scope

- Primary Odoo surface: Point of Sale.
- First release goal: purchase validation flow.
- Authentication: Basic auth.

## Immediate Planning Constraints

- Treat the current bearer-token assumption in the code as outdated unless explicit evidence shows the account uses a different auth mode.
- Before adding more endpoints, align connection settings and request-building with Basic auth credentials.
- Keep the integration isolated inside this addon. Do not spread Bonuscard-specific logic across unrelated modules unless explicitly requested.

## Architecture Expectations

- Keep connection configuration per company.
- Prefer a dedicated API client or service-layer abstraction for Bonuscard requests instead of mixing all HTTP logic into UI actions.
- Keep transport concerns, Bonuscard payload mapping, and Odoo business logic separated.
- Normalize Bonuscard API errors into predictable Odoo exceptions and store useful diagnostics on connector records.
- Support the Bonuscard test environment when configuration allows it.

## POS Flow Rules

- Model the first real integration around these API calls:
  - ValidatePurchase
  - FinalizePurchase
  - CancelPurchase
- Preserve the same transaction identifier across the full purchase lifecycle.
- FinalizePurchase must use the same products and pricing context as ValidatePurchase unless the API documentation explicitly permits a difference.
- If payment is aborted or the sale is rolled back, ensure the flow can call CancelPurchase.
- Design for idempotency and retry safety where possible.

## API Details to Respect

- Bonuscard responses can report errors in the payload even when an HTTP response is returned successfully.
- Handle both HTTP-level failures and API-level business errors.
- Use JSON for request and response handling.
- When language-sensitive responses matter, support the `BC-Culture` header.

## Odoo Coding Guidance

- Follow Odoo model and view conventions already used in this repository.
- Keep changes minimal and production-oriented.
- Add fields, views, security rules, and tests together when introducing a new capability.
- Avoid hardcoding credentials, stores, or customer data.
- Do not call the live Bonuscard API from automated tests.
- Mock HTTP interactions in tests and cover both success and failure paths.

## Suggested Delivery Order

1. Correct authentication and connection settings for Basic auth.
2. Introduce a reusable Bonuscard API client/service layer.
3. Implement POS-oriented ValidatePurchase support.
4. Implement FinalizePurchase and CancelPurchase lifecycle handling.
5. Add logging, diagnostics, and retry-safe error handling.
6. Add follow-up features only after the purchase flow is stable:
   - SearchCustomers
   - RegisterCustomer
   - ActivateDiscountCode
   - Sales report import

## When Generating Code

- Prefer root-cause fixes over view-only or field-only patches.
- If the API documentation and the current code disagree, flag the mismatch and fix the design before adding more functionality.
- Keep README and tests aligned with any meaningful behavior change.
