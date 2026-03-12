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

Use this module as the integration foundation for the POS purchase lifecycle:

- ValidatePurchase before payment
- FinalizePurchase after successful payment
- CancelPurchase if checkout is aborted

## Known Issues / Roadmap

- Add endpoint-specific POS service wrappers for purchase validation and finalization
- Add transaction identifier persistence and retry-safe lifecycle handling
- Add follow-up features for customers, discount codes, and sales reports

## Credits

**Author:** Idealskog  
**Website:** [https://github.com/symbiotech/bonuscard-odoo](https://github.com/symbiotech/bonuscard-odoo)

## License

[LGPL-3](https://www.gnu.org/licenses/lgpl-3.0) © Idealskog
