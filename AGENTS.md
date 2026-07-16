# AI Agent Instructions

This repository is an **Odoo 19 addon** integrating Point of Sale with the
Bonuscard loyalty/discount API.

## Canonical Instructions

**Read and follow [`.github/copilot-instructions.md`](.github/copilot-instructions.md).**
It is the single source of truth for product context, architecture, POS flows,
coding standards, workflow protocols, and documentation maintenance.

Cursor loads condensed rules from [`.cursor/rules/`](.cursor/rules/). If anything
conflicts, prefer the copilot instructions file.

## Documentation Map

| Doc | Purpose |
|---|---|
| [`bonuscard_odoo/README.rst`](bonuscard_odoo/README.rst) | Addon features, configuration, usage (canonical) |
| [`docs/bonuscard_pos_integration_explanation.md`](docs/bonuscard_pos_integration_explanation.md) | POS hooks, backend methods, tracked state |
| [`docs/bonuscard_pos_integration_diagram.mmd`](docs/bonuscard_pos_integration_diagram.mmd) | Architecture flowchart |
| [`docs/bonuscard-api.md`](docs/bonuscard-api.md) | API reference notes |
| [`LOCAL_SETUP.example.md`](LOCAL_SETUP.example.md) | Template for local Odoo paths and test commands |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | PR checklist, testing, security data rules |

Copy `LOCAL_SETUP.example.md` → `LOCAL_SETUP.md` locally (gitignored). Use
`LOCAL_SETUP.md` for all Odoo run/test commands — do not guess paths.

## Quick Constraints

- Keep Bonuscard logic inside this addon unless explicitly asked otherwise.
- Never commit credentials, test consumer IDs, or real customer data.
- Do not call live or test Bonuscard APIs from automated tests — mock HTTP.
- Run verification via `pre-commit run --all-files` and commands from `LOCAL_SETUP.md`.
- Update docs in the same change when observable behavior changes (see copilot file).
- When adding/changing/removing translatable strings (`self.env._`, `_t`, XML labels),
  update `bonuscard_odoo/i18n/sv_SE.po` in the same change (see Translation Maintenance
  Rule in the copilot file).

## Workflow (summary)

When starting implementation work, confirm: branch goal, done criteria, files to
change, and non-goals. Stay in analysis mode until domain behavior is explicit.
After edits, report what was verified and what was not.

Full protocols: Session Kickoff, Design vs Implementation, Test-Fix, Batch-Fix,
and Verification — see `.github/copilot-instructions.md`.
