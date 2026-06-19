# Bonuscard Odoo Translations

This module uses Odoo's standard i18n mechanism. Translations are stored in the `i18n/` folder as `.po` files.

## Swedish translation

- File: `bonuscard_odoo/i18n/sv.po`
- Contains Swedish translations for Python, XML, and JavaScript user-facing strings.

## Add another language

1. Copy `sv.po` to the new language code, e.g. `fr.po` for French or `de.po` for German.
2. Translate the `msgstr` values for each `msgid`.
3. Install or update the module in Odoo.
4. In Odoo, go to `Settings > Translations > Load a Translation` or `Settings > Translations > Import/Export > Import Translation` to import the new `.po` file.

## Notes

- Strings in Python use `self.env._(...)` for translation.
- JavaScript strings use `_t(...)`.
- XML view labels and QWeb template text are extracted automatically by Odoo.
- Keep `msgid` values unchanged when translating.
