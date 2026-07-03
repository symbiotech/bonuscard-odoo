# Local Development Setup Example

This file is a **template** for local machine-specific paths and commands.

1. Copy this file to `LOCAL_SETUP.md`.
2. Replace all placeholders with your real local paths and database name.
3. Keep `LOCAL_SETUP.md` uncommitted (it is gitignored).

## Your Environment Paths

```
Odoo source:     <ODOO_SOURCE_PATH>
Odoo venv:       <ODOO_VENV_PATH>
Addon repo:      <ADDON_REPO_PATH>
Odoo database:   bonuscard_dev
Default user:    admin / admin
```

Suggested placeholders:
- Windows: `C:\dev\odoo\19.0`, `C:\dev\bonuscard_odoo`
- Linux/macOS: `/home/you/dev/odoo/19.0`, `/home/you/dev/bonuscard_odoo`

## Quick Commands

### Install & Test Addon (Windows PowerShell)
```powershell
cd <ODOO_SOURCE_PATH>
& .\.venv\Scripts\activate.ps1
python -m odoo -c odoo.conf -d bonuscard_dev -i bonuscard_odoo --without-demo=all --stop-after-init --addons-path "<ODOO_SOURCE_PATH>\odoo\addons,<ADDON_REPO_PATH>"
```

### Install & Test Addon (Linux/macOS Bash)
```bash
cd <ODOO_SOURCE_PATH>
source .venv/bin/activate
python -m odoo -c odoo.conf -d bonuscard_dev -i bonuscard_odoo --without-demo=all --stop-after-init --addons-path "<ODOO_SOURCE_PATH>/odoo/addons,<ADDON_REPO_PATH>"
```

### Run Python Tests (Windows PowerShell)
```powershell
cd <ODOO_SOURCE_PATH>
& .\.venv\Scripts\activate.ps1
python -m odoo -c odoo.conf -d bonuscard_dev --addons-path "<ODOO_SOURCE_PATH>\odoo\addons,<ADDON_REPO_PATH>" --test-tags bonuscard_odoo --stop-after-init
```

### Run Python Tests (Linux/macOS Bash)
```bash
cd <ODOO_SOURCE_PATH>
source .venv/bin/activate
python -m odoo -c odoo.conf -d bonuscard_dev --addons-path "<ODOO_SOURCE_PATH>/odoo/addons,<ADDON_REPO_PATH>" --test-tags bonuscard_odoo --stop-after-init
```

### Run JS Unit Tests

1. Start Odoo server (if not already running).

Windows PowerShell:
```powershell
cd <ODOO_SOURCE_PATH>
& .\.venv\Scripts\activate.ps1
python -m odoo -c odoo.conf -d bonuscard_dev
# Access at http://localhost:8069
```

Linux/macOS Bash:
```bash
cd <ODOO_SOURCE_PATH>
source .venv/bin/activate
python -m odoo -c odoo.conf -d bonuscard_dev
# Access at http://localhost:8069
```

2. Open test runner:
   - All hoot tests: `http://localhost:8069/web/tests`
   - Bonuscard tests only: `http://localhost:8069/web/tests?filter=bonuscard`
   - Headless mode: `http://localhost:8069/web/tests?headless`

### Run Pre-commit Checks
```powershell
cd <ADDON_REPO_PATH>
uv sync --group dev --no-install-project
pre-commit install
pre-commit run --all-files
```

```bash
cd <ADDON_REPO_PATH>
uv sync --group dev --no-install-project
pre-commit install
pre-commit run --all-files
```

### Start Odoo Server (for manual testing, Windows PowerShell)
```powershell
cd <ODOO_SOURCE_PATH>
& .\.venv\Scripts\activate.ps1
python -m odoo -c odoo.conf -d bonuscard_dev
# Access at http://localhost:8069
```

### Start Odoo Server (for manual testing, Linux/macOS Bash)
```bash
cd <ODOO_SOURCE_PATH>
source .venv/bin/activate
python -m odoo -c odoo.conf -d bonuscard_dev
# Access at http://localhost:8069
```

## Database Reset

Windows PowerShell:
```powershell
# From Odoo venv
python -m odoo -c odoo.conf -d bonuscard_dev --uninstall=bonuscard_odoo --stop-after-init
# Then reinstall with the install command above
```

Linux/macOS Bash:
```bash
# From Odoo venv
python -m odoo -c odoo.conf -d bonuscard_dev --uninstall=bonuscard_odoo --stop-after-init
# Then reinstall with the install command above
```
