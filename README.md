# Bonuscard Connector

[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Odoo 19](https://img.shields.io/badge/Odoo-19.0-purple)](https://www.odoo.com)

## Description

Bonuscard Connector adds a configurable connection layer between Odoo and the
Bonuscard API for POS-oriented loyalty and discount workflows.

## Purpose

This module is designed as an independent, production-ready Odoo 19 addon.

- Keep Bonuscard integration logic self-contained inside a dedicated addon repository
- Provide secure, explicit Basic-auth credential and endpoint configuration per company
- Offer a stable base for Bonuscard purchase validation, finalization, and cancellation

## Features

- Connection model with API base URL, Basic-auth credentials, culture, timeout, and diagnostics
- Reusable service layer for Bonuscard HTTP requests and response error handling
- Test Connection server action from the form view
- Security groups and ACLs for user and manager roles
- **Customer lookup**: automatically search Bonuscard by phone, email, and name when a customer is selected in POS
- **Partner integration**: Bonuscard status fields and sync controls on the `res.partner` form (`linked`, `not_found`, `ambiguous`, `error`)
- **POS badge**: status indicators on the partner-selection screen in Point of Sale
- **Smart button**: one-click Bonuscard status check directly from the partner form

## Installation

1. Clone this repository into your Odoo addons path:

   ```bash
   git clone https://github.com/symbiotech/bonuscard-odoo.git
   ```

2. Restart your Odoo server and update the module list.
3. Install **Bonuscard Connector** from the Apps menu.

## Configuration

1. Go to `Bonuscard > Connections`.
2. Create a connection record and set API URL, username, password, and culture.
3. Set the test-site base URL manually if you want to work against `https://test.bonuscard.com/`.
4. Click `Test Connection`.

Once a connection is active, the POS will automatically attempt to look up the Bonuscard
status of any customer selected at checkout. The lookup searches by phone, email, and name
and writes the result back to the partner record.

## Test Environment Setup

Use the Bonuscard test account details you received by email and configure them only in your local or test Odoo database.

- Login URL: `https://test.bonuscard.com/Account/Login`
- API base URL: `https://test.bonuscard.com/api/`
- Company context: IdeelSkog AB (same EAN as production, per Bonuscard guidance)

Security rules for this repository:

- Never commit real usernames or passwords to git.
- Keep credentials in Odoo records on non-production databases or inject them through deployment secrets.
- Keep automated tests mocked. Do not call Bonuscard live or test APIs from CI.

If Bonuscard has provided a dedicated test consumer for purchase registration, store that identifier in local configuration and use it in manual end-to-end verification of the purchase flow.

## Integration Tests (Manual)

This repository now includes a manual integration test in `tests/test_bonuscard_integration.py`.

1. Fill local credentials in `.env` (already gitignored).
2. Run tests with the integration tag only.

Example Odoo test tag:

```bash
--test-tags bonuscard_integration
```

Notes:

- Integration tests are skipped automatically if required environment values are missing.
- Unit tests remain mocked and should stay safe for CI.

## Usage

### Customer Lookup in POS

When a cashier selects a customer in Point of Sale, the module automatically calls
`SearchCustomers` on the Bonuscard API using the partner's phone, email, and name.
The result is stored on the partner record and displayed as a status badge in the
partner list:

| Status | Meaning |
|---|---|
| Not Checked | Lookup has not been run yet |
| Linked | A single Bonuscard customer was matched |
| Not Found | No Bonuscard customer matched the partner details |
| Multiple Matches | More than one customer matched — manual review required |
| Error | No active Bonuscard connection is configured |

You can also check or reset the status directly from the partner form view using the
**Bonuscard** smart button or the **Check Bonuscard** / **Reset Bonuscard Status** buttons
in the Bonuscard section.

### Purchase Lifecycle (Foundation)

Use this module as the integration foundation for the POS purchase lifecycle:

- ValidatePurchase before payment
- FinalizePurchase after successful payment
- CancelPurchase if checkout is aborted

## Known Issues / Roadmap

- Add endpoint-specific POS service wrappers for purchase validation and finalization
- Add transaction identifier persistence and retry-safe lifecycle handling
- Add follow-up features for customers, discount codes, and sales reports
- Add customer registration (RegisterCustomer) from POS when no match is found
- Add discount code activation (ActivateDiscountCode)
- Persist `recruitment_code` alongside each sale for purchase reporting

## Credits

**Author:** Idealskog
**Website:** [https://github.com/symbiotech/bonuscard-odoo](https://github.com/symbiotech/bonuscard-odoo)

## Development Setup

This addon is an Odoo 19 module that runs against your main Odoo installation.

### Prerequisites

- Odoo 19.0 source code with a configured Python environment
- Pre-commit installed globally: `pip install pre-commit`

### One-Time Setup

Install pre-commit hooks in this repository:

```bash
pre-commit install
```

After installation, hooks run automatically on every `git commit`.

### Running Tests

Activate your Odoo virtual environment and run tests:

```bash
# From your Odoo source directory
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows

# Run addon tests
python -m odoo -c odoo.conf -d your_db --test-tags bonuscard_odoo --stop-after-init
```

Or for a fresh installation test:

```bash
python -m odoo \
  -c odoo.conf \
  -d your_db \
  -i bonuscard_odoo \
  --without-demo=all \
  --stop-after-init
```

Ensure `odoo.conf` includes this addon's **parent directory** (the repo root, not the addon folder itself) in `addons_path`. Example:

```
addons_path = e:\lucru\odoo\19.0\odoo\addons,e:\lucru\idealskog\odoo_dev\bonuscard_odoo
```

### Code Quality

This repository follows Odoo 19 and OCA coding standards enforced by pre-commit hooks.

**Tools:**

| Tool | Purpose |
|---|---|
| [ruff](https://docs.astral.sh/ruff/) | Python linting and formatting (replaces flake8, black, isort) |
| [pylint-odoo](https://github.com/OCA/pylint-odoo) | Odoo-specific pylint checks |
| [oca-odoo-pre-commit-hooks](https://github.com/OCA/odoo-pre-commit-hooks) | XML and PO file validation |
| [pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) | General file hygiene |

**Configuration files:**

| File | Purpose |
|---|---|
| `.pre-commit-config.yaml` | Hook definitions and pinned revisions |
| `ruff.toml` | Ruff linter and formatter settings |
| `.pylintrc` | All Odoo pylint checks (optional + mandatory; for IDEs) |
| `.pylintrc-mandatory` | Blocking subset used in the pre-commit pipeline |
| `.oca_hooks.cfg` | OCA hook overrides for this non-OCA repository |

**Manual checks:**

Run all checks without committing:

```bash
pre-commit run --all-files
```

### CI

The **Lint** GitHub Actions workflow runs `pre-commit run --all-files` on every
push and pull request to the `19.0` branch.

The **Tests** workflow runs unit tests in an OCA-provided Docker image with PostgreSQL.

## License

[LGPL-3](https://www.gnu.org/licenses/lgpl-3.0) © Idealskog
