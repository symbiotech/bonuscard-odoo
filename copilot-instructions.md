# Copilot Instructions for bonuscard_odoo

## Product Context

- This repository is an Odoo 19 addon for integrating Odoo with the Bonuscard platform.
- Bonuscard is used for loyalty and discount handling in e-commerce and point-of-sale flows.
- The API is designed around purchase validation before payment, purchase finalization after payment, and cancellation when a purchase is aborted.

## Confirmed Initial Scope

- Primary Odoo surface: Point of Sale.
- First release goal: purchase validation flow.
- Authentication: Basic auth.
- **Implemented**: SearchCustomers lookup triggered from POS partner selection, Bonuscard status fields on `res.partner`, smart button on partner form, OWL badge in POS partner list.

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
- `BonuscardApiService._get_company_instance(company)` resolves the active connector for a given company, falling back to any active instance.
- `BonuscardApiService.search_customers(instance, query)` wraps the `SearchCustomers` endpoint using URL query params.
- Bonuscard status is written to the **commercial partner** (`partner.commercial_partner_id`) and propagated to child contacts.
- Partner lookup uses phone (normalised digits-only), email, and name as search terms in priority order. Exact deduplication is keyed on Bonuscard customer `id` or `recruitmentCode` to avoid counting the same record twice.

## POS Flow Rules

- Model the first real integration around these API calls:
  - ValidatePurchase
  - FinalizePurchase
  - CancelPurchase
- Preserve the same transaction identifier across the full purchase lifecycle.
- FinalizePurchase must use the same products and pricing context as ValidatePurchase unless the API documentation explicitly permits a difference.
- If payment is aborted or the sale is rolled back, ensure the flow can call CancelPurchase.
- Design for idempotency and retry safety where possible.
- The `setPartnerToCurrentOrder` hook in `PosStore` is already patched by `bonuscard_pos.js`; extend or refine that patch for purchase lifecycle hooks rather than adding a second patch on the same method.
- POS data fields for `res.partner` are extended via `_load_pos_data_fields`; add any new fields needed in POS there.

## API Details to Respect

- Bonuscard responses can report errors in the payload even when an HTTP response is returned successfully.
- Handle both HTTP-level failures and API-level business errors.
- Use JSON for request and response handling.
- When language-sensitive responses matter, support the `BC-Culture` header.

## Test Account Usage

- A Bonuscard test account exists for integration testing against `https://test.bonuscard.com/`.
- Treat all received account credentials and test consumer identifiers as secrets.
- Never write real credentials into repository files, tests, fixtures, commits, or pull request text.
- Use runtime configuration only (local Odoo records, CI/deployment secrets, or secure parameter stores).
- Manual integration tests may read `.env` values locally, but `.env` must keep placeholders by default in git-tracked content.
- For local test execution in this repository, always follow `LOCAL_SETUP.md` rather than ad-hoc test commands in the addon folder. Use the provided Odoo source root command from that file.

## Odoo Coding Guidance

- Follow Odoo model and view conventions already used in this repository.
- Keep changes minimal and production-oriented.
- Add fields, views, security rules, and tests together when introducing a new capability.
- Avoid hardcoding credentials, stores, or customer data.
- Do not call the live Bonuscard API from automated tests.
- Do not call the Bonuscard test API from automated tests.
- Mock HTTP interactions in tests and cover both success and failure paths.
- If integration tests are added, mark them with a dedicated manual tag (for example `bonuscard_integration`) and keep them out of CI defaults.
- `patch.object(model_instance, "method", ...)` does **not** work for Odoo model methods (attributes are read-only). Always patch by full import path string: `patch("odoo.addons.bonuscard_odoo.models.ClassName.method_name", ...)`.
- `res.partner.mobile` may not exist in all Odoo 19 builds. Always guard field access with `self._fields.get("mobile")` before reading `self.mobile`.

## Coding Style and Linting

This repository uses pre-commit hooks that enforce Odoo 19 and OCA coding standards.
The following rules apply when writing or modifying Python code:

- **Formatting**: Use [ruff](https://docs.astral.sh/ruff/) for formatting and linting
  (replaces black, isort, flake8). Line length is 88. Import blocks must be sorted.
- **Imports**: Standard library imports first, then third-party, then Odoo, then relative.
  Combine `from . import X` statements on a single line when possible.
- **Translations**: Use `self.env._("text")` instead of `_("text")` for all user-facing
  strings in model methods (Odoo 18+ practice). Use the lazy form
  `self.env._("text %s", value)` instead of `_("text %s") % value`.
- **Pylint**: All code must pass `.pylintrc-mandatory` without warnings. The `.pylintrc`
  file (loaded by IDEs) also includes optional checks that are non-blocking.
- **OCA hooks**: XML files are validated by `oca-checks-odoo-module`. Avoid deprecated
  XML nodes and ensure all `<record>` tags have an `id` attribute.
- **No `# noqa` unless justified**: Fix the root cause instead of silencing warnings.
  The `# pylint: disable=broad-except` in `action_test_connection` is a documented
  exception for UI-safe error handling.

To run all checks locally:

```bash
pip install pre-commit
pre-commit install      # install hooks once
pre-commit run --all-files   # run everything now
```

## Suggested Delivery Order

1. ~~Correct authentication and connection settings for Basic auth.~~ ✅
2. ~~Introduce a reusable Bonuscard API client/service layer.~~ ✅
3. ~~Implement SearchCustomers with POS partner selection hook and status badges.~~ ✅
4. Implement POS-oriented ValidatePurchase support.
5. Implement FinalizePurchase and CancelPurchase lifecycle handling.
6. Add logging, diagnostics, and retry-safe error handling.
7. Add follow-up features only after the purchase flow is stable:
   - RegisterCustomer
   - ActivateDiscountCode
   - Sales report import

## When Generating Code

- Prefer root-cause fixes over view-only or field-only patches.
- If the API documentation and the current code disagree, flag the mismatch and fix the design before adding more functionality.
- Keep README and tests aligned with any meaningful behavior change.
