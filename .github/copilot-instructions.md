# AI Agent Instructions for bonuscard_odoo

> **Canonical source** for GitHub Copilot, Cursor, and other AI coding assistants.
> Cursor loads condensed rules from `.cursor/rules/`; see `AGENTS.md` for the doc map.
> When updating agent guidance, edit this file first, then sync `AGENTS.md` and
> `.cursor/rules/` if the condensed rules need the same change.

## Product Context

- This repository is an Odoo 19 addon for integrating Odoo with the Bonuscard platform.
- Bonuscard is used for loyalty and discount handling in e-commerce and point-of-sale flows.
- The API is designed around purchase validation before payment, purchase finalization after payment, and cancellation when a purchase is aborted.

## Confirmed Initial Scope

- Primary Odoo surface: Point of Sale.
- Authentication: Basic auth via `bonuscard.connector.instance._build_headers`.
- **Implemented**: SearchCustomers lookup from POS partner selection; POS customer import on Enter when local search is empty (recruitment code, phone including national/trunk-0 vs E.164, or email; short fuzzy hits rejected); Bonuscard status fields on `res.partner`; smart button and manual check/reset on partner form; OWL badges in POS partner list; ValidatePurchase / FinalizePurchase / CancelPurchase lifecycle with automatic discount application; RegisterCustomer from partner form and POS partner list; product catalog gating and manager catalog probe; bulk partner prefetch (cron + manual); Bonuscard audit fields on `pos.order`.

## Immediate Planning Constraints

- Keep connection settings and request-building aligned with Basic auth credentials.
- Keep the integration isolated inside this addon. Do not spread Bonuscard-specific logic across unrelated modules unless explicitly requested.
- Configure a POS discount product — unmatched Bonuscard discounts are added as separate discount lines.

## Architecture Expectations

- Keep connection configuration per company.
- Prefer a dedicated API client or service-layer abstraction for Bonuscard requests instead of mixing all HTTP logic into UI actions.
- Keep transport concerns, Bonuscard payload mapping, and Odoo business logic separated.
- Normalize Bonuscard API errors into predictable Odoo exceptions and store useful diagnostics on connector records.
- Support the Bonuscard test environment when configuration allows it.
- `BonuscardApiService._get_company_instance(company)` resolves the active connector for a given company, falling back to any active instance.
- `BonuscardApiService.search_customers(instance, query)` wraps the `SearchCustomers` endpoint using URL query params.
- When Bonuscard status is written on a contact, the same status is mirrored on its **commercial partner** (`partner.commercial_partner_id`) when both records share an equivalent phone number (Bonuscard's unique customer key; national / trunk-0 / E.164 forms count as the same).
- Partner lookup uses phone (digit normalize plus country-code / trunk-aware equivalence), email, and name as search terms in priority order. Exact deduplication is keyed on Bonuscard customer `id` or `recruitmentCode` to avoid counting the same record twice.
- POS customer import (`import_partner_from_bonuscard_for_pos`) accepts a Bonuscard `SearchCustomers` result when the cashier's query matches recruitment code, phone (same equivalence as above), or email. A short fuzzy API hit (for example `0724` matching internal id `724`) is rejected.

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
- When language-sensitive responses matter, send the `BC-Culture` header.
  Prefer the current user's Odoo language when it maps to a supported Bonuscard
  culture; otherwise use the connection `api_culture` fallback.

## Test Account Usage

- A Bonuscard test account exists for manual integration testing against `https://test.bonuscard.com/`.
- Treat all received account credentials and test consumer identifiers as secrets.
- Never write real credentials into repository files, tests, fixtures, commits, or pull request text.
- Use runtime configuration only (local Odoo records, CI/deployment secrets, or secure parameter stores).
- Manual integration tests may read `.env` values locally, but `.env` must keep placeholders by default in git-tracked content.
- For local test execution in this repository, always follow `LOCAL_SETUP.md` rather than ad-hoc test commands in the addon folder. Use the provided Odoo source root command from that file.
- If `LOCAL_SETUP.md` is not present in the conversation context, ask the user to provide the relevant command before proceeding. Do not guess or substitute ad-hoc commands.

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
- `res.partner` in Odoo 19 base has no `mobile` field. Only `phone` is available.

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
	JavaScript uses `_t(...)`. XML visible labels are extracted by Odoo.
- **Pylint**: All code must pass `.pylintrc-mandatory` without warnings. The `.pylintrc`
	file (loaded by IDEs) also includes optional checks that are non-blocking.
- **OCA hooks**: XML files are validated by `oca-checks-odoo-module`. Avoid deprecated
	XML nodes and ensure all `<record>` tags have an `id` attribute.
- **No `# noqa` unless justified**: Fix the root cause instead of silencing warnings.
	The `# pylint: disable=broad-except` in `action_test_connection` is a documented
	exception for UI-safe error handling.

To run all checks locally:

```bash
uv sync --group dev --no-install-project
pre-commit install      # install hooks once
pre-commit run --all-files   # run everything now
```

## Suggested Delivery Order

1. ~~Correct authentication and connection settings for Basic auth.~~ ✅
2. ~~Introduce a reusable Bonuscard API client/service layer.~~ ✅
3. ~~Implement SearchCustomers with POS partner selection hook and status badges.~~ ✅
4. ~~Implement POS-oriented ValidatePurchase support.~~ ✅
5. ~~Implement FinalizePurchase and CancelPurchase lifecycle handling.~~ ✅
6. ~~Add logging, diagnostics, and retry-safe error handling.~~ ✅
7. ~~RegisterCustomer (partner form and POS partner list).~~ ✅
8. ~~Product catalog gating, bulk partner prefetch, and catalog probe.~~ ✅
9. ~~Bonuscard audit fields on `pos.order` (validated/finalized/skipped/failed).~~ ✅
10. Add follow-up features only after the purchase flow is stable:
	 - ActivateDiscountCode
	 - Sales report import

## Workflow Rules for This Repo

When multiple protocols apply, follow them in this order: (1) Session Kickoff, (2) Design vs Implementation, (3) Test-Fix, (4) Batch-Fix, (5) Verification. Apply all that are relevant in sequence.

### Session Kickoff Protocol

Start implementation chats by restating these four items in one short block before editing code:

1. Branch goal
2. Done criteria
3. Files expected to change
4. Explicit non-goals

If any item is missing, ask for all missing items in a single message before making edits.

### Test-Fix Protocol (JS/POS)

When user asks to fix failing tests, require this input first:

1. Exact failing test name(s)
2. Exact error output
3. Repro command used in this repo
4. Expected behavior

Then execute this flow:

1. Find root cause in production code first
2. Patch minimal production code or test seam (no fake-only workaround unless requested)
3. Update all tests with the same root cause in one pass
4. Report list of updated tests

### Batch-Fix Rule

If one failure pattern likely affects multiple tests/files, proactively scan and fix all matching cases in the same change instead of waiting for follow-up prompts.

### Design vs Implementation Rule

- If user is still clarifying domain behavior, stay in analysis mode and produce a short decision summary.
- Start code edits only after behavior is explicit.
- Re-check implementation against that decision summary before finishing.

### Odoo Security Data Rule

- For `res.groups`, use `user_ids` for membership relations.
- For default memberships that should not be re-applied on every upgrade, place assignment in `noupdate="1"` data.

### Verification Rule

After edits:

1. Run or suggest the canonical local command path from LOCAL_SETUP.md
2. Report what was verified and what was not verified
3. If blocked, provide exact blocker and next command to run

## Documentation Maintenance Rule

When any code change affects observable behavior, update the relevant docs in the same change:

| Doc | What it covers | Update when… |
|---|---|---|
| `bonuscard_odoo/README.rst` | Features list, configuration, usage (canonical addon docs) | A feature is added, changed, or completed |
| `README.md` | Repo setup, roadmap, development workflow | Roadmap status changes or dev/CI instructions change |
| `bonuscard_odoo/static/description/index.html` | Odoo Apps listing highlights | User-visible features change |
| `docs/bonuscard_pos_integration_explanation.md` | Step-by-step POS flow, patched methods, backend components, tracked state | Any POS patch is added/renamed/removed; any `bonuscard.api.service` or `res.partner` method changes |
| `docs/bonuscard_pos_integration_diagram.mmd` | Architecture flowchart | The trigger points or data-flow arrows between POS and backend change |

Concrete checks before finishing a code change:

1. If a POS method is patched or renamed, update the method name in explanation.md and the diagram.
2. If a new validation trigger is added (e.g. a new hook that calls `_validateBonuscardPurchaseForOrder`), add it to step 3 of explanation.md and the diagram.
3. If a new cancel path is added, add it to step 5 of explanation.md.
4. If a Roadmap item in README.md is implemented, mark it Done in the same PR.
5. If a new end-to-end feature is added, add a bullet to the **Features** section of `bonuscard_odoo/README.rst` and update `static/description/index.html`.
6. Never describe a flow as "(Foundation)" or "Ready for" once it is fully implemented.

## Translation Maintenance Rule

When adding, changing, or removing translatable user-facing strings, update
`bonuscard_odoo/i18n/` in the **same change**. Do not leave new English-only
strings for a later pass unless explicitly asked.

Covers:

- Python: `self.env._("...")`
- JavaScript: `_t("...")`
- XML: visible labels and QWeb text (e.g. button text `Bonuscard`)

Does **not** cover: README / markdown docs (not shipped via `.po`).

Workflow (match existing repo practice):

1. Prefer Odoo export via `LOCAL_SETUP.md` paths: update the module (`-u bonuscard_odoo`),
   then `python -m odoo --addons-path=... i18n export bonuscard_odoo -c odoo.conf -d <db> -l pot`
   (writes `bonuscard_odoo/i18n/bonuscard_odoo.pot`). This repo normally commits
   `sv_SE.po` only — use the pot as a merge source, then remove it unless asked to keep it.
2. Merge the exported template into `bonuscard_odoo/i18n/sv_SE.po`, preserving existing
   `msgstr` values. Keep `#: code:bonuscard_odoo/...` references (not `code:addons/bonuscard_odoo/...`).
3. Add Swedish `msgstr` for every new/changed msgid. Brand-only strings like `Bonuscard`
   may stay empty (English fallback) when that is already the convention.
4. **Msgid changes / fuzzy merges:** gettext merge tools often clear `msgstr` (or mark
   `#, fuzzy`) when the English `msgid` changes even if a prior Swedish translation
   existed. Agents must **not** leave previously translated entries empty after a sync.
   Re-translate or adapt the old `msgstr` to the new `msgid` meaning (carry forward the
   prior Swedish and update it). Only leave `msgstr ""` when the entry was never
   translated, is brand-only by convention, or emptiness is an intentional product
   choice. Diff `sv_SE.po` against the pre-sync version and restore any accidentally
   cleared `msgstr` before committing.
5. For a small feature delta, manually inserting the new entries into `sv_SE.po` (same
   reference format) is acceptable when a full export/merge is impractical.

## When Generating Code

- Prefer root-cause fixes over view-only or field-only patches.
- If the API documentation and the current code disagree, flag the mismatch and fix the design before adding more functionality.
- Keep `bonuscard_odoo/README.rst`, explanation.md, diagram.mmd, and tests aligned with any meaningful behavior change.
