# Bonuscard Odoo Translations

This module uses Odoo's standard i18n mechanism. Translations are stored in the `i18n/` folder as `.po` files.

## Swedish translation

- File: `bonuscard_odoo/i18n/sv_SE.po`
- Contains Swedish translations for Python, XML, and JavaScript user-facing strings.

## Add another language

1. Copy `sv_SE.po` to the new language code, e.g. `fr_FR.po` for French or `de_DE.po` for German.
2. Translate the `msgstr` values for each `msgid`.
3. Install or update the module in Odoo.
4. In Odoo, go to `Settings > Translations > Load a Translation` or `Settings > Translations > Import/Export > Import Translation` to import the new `.po` file.

## Updating translations

When module user-facing strings change, sync `sv_SE.po` in the same change:

1. Update the module in a local Odoo DB (`-u bonuscard_odoo`; paths from `LOCAL_SETUP.md`).
2. Export a template: `python -m odoo --addons-path=... i18n export bonuscard_odoo -c odoo.conf -d <db> -l pot`
   (writes `bonuscard_odoo.pot` under this folder).
3. Merge into `sv_SE.po`, keep existing Swedish `msgstr`, and restore
   `code:bonuscard_odoo/...` references if the export used `code:addons/bonuscard_odoo/...`.
4. Translate new msgids. This repo normally commits `sv_SE.po` only (drop the pot after merge unless asked to keep it).

Small feature deltas may add entries to `sv_SE.po` directly when a full export is impractical.

## Notes

- Strings in Python use `self.env._(...)` for translation.
- JavaScript strings use `_t(...)`.
- XML view labels and QWeb template text are extracted automatically by Odoo.
- Keep `msgid` values unchanged when translating.
- README / markdown docs are not translated via `.po` files.
