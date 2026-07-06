# Bonuscard Connector

[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Odoo 19](https://img.shields.io/badge/Odoo-19.0-purple)](https://www.odoo.com)

## Description

Bonuscard Connector is an Odoo 19 addon that integrates Odoo POS with the
Bonuscard API for loyalty and discount workflows.

## Canonical Docs

For addon behavior, configuration, and usage, use
[bonuscard_odoo/README.rst](bonuscard_odoo/README.rst).

## Documentation Structure

To avoid duplicate docs drift, this repository uses a split canonical model:

- **Addon behavior and usage (canonical):** [bonuscard_odoo/README.rst](bonuscard_odoo/README.rst)
- **POS integration flow narrative:** [docs/bonuscard_pos_integration_explanation.md](docs/bonuscard_pos_integration_explanation.md)
- **POS integration architecture diagram:** [docs/bonuscard_pos_integration_diagram.mmd](docs/bonuscard_pos_integration_diagram.mmd)
- **API reference notes:** [docs/bonuscard-api.md](docs/bonuscard-api.md)
- **Development workflow and contribution rules:** this file and [CONTRIBUTING.md](CONTRIBUTING.md)
- **AI agent instructions (canonical):** [.github/copilot-instructions.md](.github/copilot-instructions.md) with Cursor rules in [`.cursor/rules/`](.cursor/rules/) and entry point [AGENTS.md](AGENTS.md)

If content overlaps, update the module README first and link to it from here.

## Installation

1. Clone this repository into your Odoo addons path:

   ```bash
   git clone https://github.com/symbiotech/bonuscard-odoo.git
   ```

2. Restart your Odoo server and update the module list.
3. Install **Bonuscard Connector** from the Apps menu.

## Configuration

Configuration and functional usage are documented in
[bonuscard_odoo/README.rst](bonuscard_odoo/README.rst).

## Functional References

- [bonuscard_odoo/README.rst](bonuscard_odoo/README.rst)
- [docs/bonuscard_pos_integration_explanation.md](docs/bonuscard_pos_integration_explanation.md)
- [docs/bonuscard_pos_integration_diagram.mmd](docs/bonuscard_pos_integration_diagram.mmd)

## Roadmap

| Item | Status |
|------|--------|
| Basic-auth connection and API service layer | Done |
| POS customer lookup and status badges | Done |
| ValidatePurchase / FinalizePurchase / CancelPurchase in POS | Done |
| Automatic discount application in POS | Done |
| RegisterCustomer (partner form and POS) | Done |
| ActivateDiscountCode | Planned |
| Sales report import | Planned |

## Development Setup

This addon is an Odoo 19 module that runs against your main Odoo installation.
Use `LOCAL_SETUP.example.md` as the committed template, then create your local
`LOCAL_SETUP.md` from it with machine-specific paths.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution workflow, coding standards,
testing expectations, and pull request checklist.

### Prerequisites

- Odoo 19.0 source code with a configured Python environment
- `uv` installed on your machine for dependency and tool management

### One-Time Setup

Use `uv` to sync dev tools without installing the current project package:

```bash
uv sync --group dev --no-install-project
pre-commit install
```

> Note: This repository uses a custom Odoo addon build backend, so `uv` may fail if it tries to install the addon package itself.
> Using `--no-install-project` keeps `pre-commit` and other dev tools in the environment without building the current project.

After installation, hooks run automatically on every `git commit`.

### Running Tests

Activate your Odoo virtual environment and run tests:

```bash
# From your Odoo source directory
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows

# Run Python addon tests
python -m odoo -c odoo.conf -d your_db --test-tags bonuscard_odoo --stop-after-init
```

JS unit tests for POS logic are run via the Odoo web test runner. See
`LOCAL_SETUP.example.md` for URLs and filter options (`?filter=bonuscard`).

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
addons_path = C:\XXX\odoo\19.0\odoo\addons,C:\XXX\odoo_dev\bonuscard_odoo
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

The source code is licensed under [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0).
The Bonuscard name and logo are used with permission from Bonuscard Sverige AB.
The Bonuscard name, logo, and related branding are not covered by the LGPL-3 license and remain the property of Bonuscard Sverige AB.
