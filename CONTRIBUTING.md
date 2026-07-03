# Contributing to Bonuscard Connector

Thanks for helping improve this Odoo 19 addon.

## Scope and Principles

- Keep Bonuscard-specific logic inside this addon.
- Prefer small, focused pull requests.
- Do not commit secrets, credentials, or real customer data.
- Keep transport logic, payload mapping, and Odoo business logic separated.

## Before You Start

1. Read the project overview in README.md.
2. Copy `LOCAL_SETUP.example.md` to `LOCAL_SETUP.md` and set your machine-specific Odoo paths and commands.
3. Confirm your branch has a single clear goal.

## Local Setup

Use the repository root:

```powershell
uv sync --group dev --no-install-project
pre-commit install
```

Use LOCAL_SETUP.md for canonical Odoo run/test commands in this repository.

## Coding Standards

- Target Odoo 19 conventions.
- Python formatting and linting must pass Ruff.
- Keep imports sorted (stdlib, third-party, Odoo, relative).
- For user-facing model strings, use self.env._("...").
- Avoid broad exception handling unless there is a documented UI-safe reason.
- Do not use noqa/pylint disables unless justified.

## Bonuscard Integration Rules

- Automated tests must not call live or test Bonuscard APIs.
- Mock HTTP calls in automated tests.
- Handle both HTTP failures and API business errors.
- Keep connection configuration per company.
- Preserve transaction identity across validate/finalize/cancel purchase lifecycle.

## Testing and Verification

Run these before opening a PR:

1. Pre-commit checks:

```powershell
pre-commit run --all-files
```

2. Odoo addon tests using the command pattern from LOCAL_SETUP.md.
3. JS POS tests from LOCAL_SETUP.md when your change touches POS code.
4. Manual validation for changed user flows when relevant.

Additional test guidance:

- Keep unit/integration test HTTP interactions mocked by default.
- If you add real-endpoint integration checks, mark them with manual tag
	`bonuscard_integration` and keep them out of CI defaults.
- Include both success and failure-path assertions for API-level and HTTP-level errors.

## Model/View/Security Change Checklist

When adding a capability, update all relevant layers together:

- Models (fields/business methods)
- Views (form/list/smart buttons as needed)
- Security (groups/ACL/rules if access changes)
- Tests (Python and/or POS JS)
- Documentation (README + POS docs when behavior changes)

For security XML data:

- Use `user_ids` for `res.groups` membership relations.
- Use `noupdate="1"` for default memberships that should not be re-applied each upgrade.

## Required Documentation Sync

If behavior changes, update docs in the same PR:

- README.md (features, usage, roadmap)
- docs/bonuscard_pos_integration_explanation.md
- docs/bonuscard_pos_integration_diagram.mmd

Examples:

- New POS hook or renamed method: update explanation and diagram.
- New cancel/validation path: update flow steps in docs.
- Completed roadmap item: mark it done in README.md.

## Pull Request Checklist

- Describe what changed and why.
- Link issue/task if available.
- Include tests updated/added.
- Include docs updated (when behavior changed).
- Confirm no secrets or local-only data were committed.

## Commit Guidance

- Keep commits focused and reviewable.
- Prefer clear, imperative commit messages.
- Separate refactors from behavioral changes where possible.

## Reporting Bugs or Requesting Features

Open an issue with:

- Current behavior
- Expected behavior
- Steps to reproduce
- Logs/errors (sanitized)
- Environment details (Odoo version, module revision)
