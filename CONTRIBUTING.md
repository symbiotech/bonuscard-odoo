# Contributing to bonuscard-odoo

Thank you for contributing! This guide covers the local development setup
required before making changes to this repository.

## Prerequisites

- Python 3.10 or newer
- Git

## Setting up pre-commit

This repository enforces code quality through
[pre-commit](https://pre-commit.com) hooks (ruff, pylint-odoo, OCA hooks, and
general file hygiene checks). You must install and activate the hooks once
before your first commit.

### 1. Install pre-commit

Choose the method that suits your environment:

**Recommended – pipx (isolated, no virtual env required):**

```bash
pipx install pre-commit
```

> Install `pipx` first if needed: `pip install --user pipx` or
> `brew install pipx` on macOS.

**Inside a virtual env:**

```bash
pip install pre-commit
```

**macOS Homebrew:**

```bash
brew install pre-commit
```

### 2. Activate the hooks in this repository

Run this once after cloning (or after updating `.pre-commit-config.yaml`):

```bash
pre-commit install
```

From now on the hooks run automatically on every `git commit`.

### 3. Run all checks manually

```bash
pre-commit run --all-files
```

## Hook overview

| Hook | Purpose |
|---|---|
| [ruff](https://docs.astral.sh/ruff/) | Python linting and auto-formatting |
| [pylint-odoo](https://github.com/OCA/pylint-odoo) | Odoo-specific pylint checks |
| [oca-odoo-pre-commit-hooks](https://github.com/OCA/odoo-pre-commit-hooks) | XML and PO file validation |
| [pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) | Trailing whitespace, EOF, merge-conflict markers, … |

## Configuration files

| File | Purpose |
|---|---|
| `.pre-commit-config.yaml` | Hook definitions and pinned revisions |
| `ruff.toml` | Ruff linter and formatter settings |
| `.pylintrc` | Full pylint config (optional checks; loaded by IDEs) |
| `.pylintrc-mandatory` | Blocking subset used in the pre-commit pipeline |
| `.oca_hooks.cfg` | OCA hook overrides for this non-OCA repository |

## Updating hook revisions

```bash
pre-commit autoupdate
```

Review the diff and commit the updated `.pre-commit-config.yaml`.

## Running Odoo tests

Unit tests are run with Odoo's test runner. Keep all HTTP calls to the
Bonuscard API mocked. Integration tests (tagged `bonuscard_integration`) are
excluded from CI and require local `.env` configuration – see
[README.md](README.md#integration-tests-manual) for details.
