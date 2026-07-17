import base64
import logging
from urllib.parse import urljoin

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
_CTX_SKIP_CURRENT_ENFORCEMENT = "bonuscard_skip_current_enforcement"

# Bonuscard ``BC-Culture`` values keyed by Odoo lang codes / language prefixes.
_ODOO_LANG_TO_BC_CULTURE = {
    "sv_SE": "sv-SE",
    "fi_FI": "fi-FI",
    "nb_NO": "nb-NO",
    "nn_NO": "nb-NO",
    "da_DK": "da-DK",
    "en_GB": "en-GB",
    "en_US": "en-GB",
    "en_AU": "en-GB",
}
_ODOO_LANG_PREFIX_TO_BC_CULTURE = {
    "sv": "sv-SE",
    "fi": "fi-FI",
    "nb": "nb-NO",
    "nn": "nb-NO",
    "da": "da-DK",
    "en": "en-GB",
}


class BonuscardConnectorInstance(models.Model):
    _name = "bonuscard.connector.instance"
    _description = "Bonuscard Connection"
    _order = "name asc"

    name = fields.Char(string="Connection Name", required=True)
    active = fields.Boolean(default=True)
    is_current = fields.Boolean(
        string="Use for Bonuscard API",
        default=False,
        copy=False,
        help="Enable this on exactly one connection per company to control which "
        "Bonuscard environment (production/sandbox) is used by POS and other API calls.",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    api_base_url = fields.Char(
        string="API Base URL",
        required=True,
        default="https://web.bonuscard.com/api/",
    )
    api_username = fields.Char(string="API Username", required=True, copy=False)
    api_password = fields.Char(string="API Password", required=True, copy=False)
    api_culture = fields.Selection(
        selection=[
            ("en-GB", "English"),
            ("sv-SE", "Swedish"),
            ("fi-FI", "Finnish"),
            ("nb-NO", "Norwegian"),
            ("da-DK", "Danish"),
        ],
        string="API Culture",
        required=True,
        default="sv-SE",
        help="Fallback language for Bonuscard API messages (errors and "
        "confirmations) when the current user's language is not supported. "
        "When the user language maps to English, Swedish, Finnish, Norwegian, "
        "or Danish, that language is sent as BC-Culture instead.",
    )
    request_timeout = fields.Integer(string="Request Timeout (s)", default=20)

    bulk_partner_prefetch_active = fields.Boolean(
        string="Enable bulk partner prefetch",
        default=True,
        help="When enabled, the cron job and manual button will prefetch Bonuscard customer links in the background.",
    )
    bulk_partner_prefetch_ttl_hours = fields.Integer(
        string="Bulk prefetch TTL (hours)",
        default=24,
        help="Partners synced within this window are skipped to reduce API calls.",
    )
    bulk_partner_prefetch_batch_size = fields.Integer(
        string="Bulk prefetch batch size",
        default=200,
        help="Maximum number of partners processed per run.",
    )
    bulk_partner_prefetch_enable_name_fallback = fields.Boolean(
        string="Allow name fallback",
        default=False,
        help="If enabled, the prefetch can use partner name as a last resort when phone and email are missing.",
    )

    catalog_probe_active = fields.Boolean(
        string="Enable catalog probe",
        default=True,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
        help="When enabled, the daily cron, manual button, and automatic probes on "
        "manual product create or identifier update check Bonuscard catalog status "
        "for products that have not been scanned yet.",
    )
    catalog_probe_customer_identifier = fields.Char(
        string="Catalog Probe Customer",
        copy=False,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
        help="Dedicated Bonuscard test customer identifier (recruitment code, phone, "
        "email, etc.) used when probing product catalog status via ValidatePurchase.",
    )
    catalog_probe_price = fields.Float(
        string="Catalog Probe Price",
        default=100.0,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
        help="Nominal unit price sent to ValidatePurchase when probing products.",
    )
    catalog_probe_batch_size = fields.Integer(
        string="Catalog Probe Batch Size",
        default=50,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
        help="Maximum number of never-scanned products processed per cron run.",
    )
    catalog_probe_unlock_ean = fields.Char(
        string="Catalog Probe Unlock EAN",
        copy=False,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
        help="Barcode or article number of a product known to exist in the Bonuscard "
        "catalog. When configured, unknown products are probed in the same "
        "ValidatePurchase call as this anchor EAN. Bonuscard may still return a "
        "transactionIdentifier while only recognizing the anchor; membership is "
        "determined from enriched checkoutItems for the probed EAN. CancelPurchase "
        "on that transaction releases the dedicated probe customer.",
    )

    connection_status = fields.Selection(
        selection=[
            ("unknown", "Unknown"),
            ("ok", "OK"),
            ("error", "Error"),
        ],
        default="unknown",
        readonly=True,
        copy=False,
    )
    last_test_at = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    @api.constrains("catalog_probe_price", "catalog_probe_batch_size")
    def _check_catalog_probe_settings(self):
        for rec in self:
            if rec.catalog_probe_price is not None and rec.catalog_probe_price <= 0:
                raise ValidationError(
                    self.env._("Catalog probe price must be greater than zero.")
                )
            if (
                rec.catalog_probe_batch_size is not None
                and rec.catalog_probe_batch_size <= 0
            ):
                raise ValidationError(
                    self.env._("Catalog probe batch size must be greater than zero.")
                )

    @api.constrains("api_base_url")
    def _check_api_base_url(self):
        for rec in self:
            if rec.api_base_url and not rec.api_base_url.startswith(
                ("http://", "https://")
            ):
                raise ValidationError(
                    self.env._("API Base URL must start with http:// or https://")
                )

    @api.constrains("is_current", "company_id", "active")
    def _check_is_current_unique_per_company(self):
        if self.env.context.get(_CTX_SKIP_CURRENT_ENFORCEMENT):
            return
        for rec in self:
            if not rec.is_current:
                continue
            if not rec.active:
                raise ValidationError(
                    self.env._(
                        "Archived Bonuscard connections cannot be selected for API use."
                    )
                )
            other = self.sudo().search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("active", "=", True),
                    ("is_current", "=", True),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    self.env._(
                        "Only one Bonuscard connection can be selected for API use per company."
                    )
                )

    @api.constrains("company_id", "active", "is_current")
    def _check_company_has_current_instance_when_active(self):
        """Require exactly one current connection per company when any are active."""
        if self.env.context.get(_CTX_SKIP_CURRENT_ENFORCEMENT):
            return
        for rec in self:
            company = rec.company_id
            if not company:
                continue
            active_count = self.sudo().search_count(
                [("company_id", "=", company.id), ("active", "=", True)]
            )
            if not active_count:
                continue
            current_count = self.sudo().search_count(
                [
                    ("company_id", "=", company.id),
                    ("active", "=", True),
                    ("is_current", "=", True),
                ]
            )
            if current_count != 1:
                raise ValidationError(
                    self.env._(
                        "Exactly one active Bonuscard connection must be selected for API use per company."
                    )
                )

    @api.constrains("request_timeout")
    def _check_timeout(self):
        for rec in self:
            if rec.request_timeout < 1:
                raise ValidationError(
                    self.env._("Request timeout must be at least 1 second.")
                )

    @api.constrains(
        "bulk_partner_prefetch_ttl_hours", "bulk_partner_prefetch_batch_size"
    )
    def _check_bulk_prefetch_settings(self):
        for rec in self:
            if rec.bulk_partner_prefetch_ttl_hours < 1:
                raise ValidationError(
                    self.env._("Bulk prefetch TTL must be at least 1 hour.")
                )
            if rec.bulk_partner_prefetch_batch_size < 1:
                raise ValidationError(
                    self.env._("Bulk prefetch batch size must be at least 1.")
                )

    @api.model
    def _map_odoo_lang_to_bc_culture(self, lang):
        """Map an Odoo lang code to a Bonuscard ``BC-Culture`` value.

        Returns ``None`` when the language is missing or not supported by
        Bonuscard so callers can fall back to ``api_culture``.
        """
        if not lang:
            return None
        normalized = str(lang).strip().replace("-", "_")
        if "@" in normalized:
            normalized = normalized.split("@", 1)[0]
        if normalized in _ODOO_LANG_TO_BC_CULTURE:
            return _ODOO_LANG_TO_BC_CULTURE[normalized]
        prefix = normalized.split("_", 1)[0].lower()
        return _ODOO_LANG_PREFIX_TO_BC_CULTURE.get(prefix)

    def _resolve_bc_culture(self):
        """Culture sent as ``BC-Culture``: user lang when supported, else config."""
        self.ensure_one()
        return (
            self._map_odoo_lang_to_bc_culture(self.env.lang)
            or self.api_culture
            or "en-GB"
        )

    def _build_headers(self):
        self.ensure_one()
        credentials = f"{self.api_username}:{self.api_password}".encode()
        authorization = base64.b64encode(credentials).decode("ascii")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {authorization}",
            "BC-Culture": self._resolve_bc_culture(),
        }

    def _build_url(self, endpoint):
        self.ensure_one()
        base_url = self.api_base_url.rstrip("/") + "/"
        endpoint = endpoint.lstrip("/")
        return urljoin(base_url, endpoint)

    def _unset_other_current_instances(self):
        self.ensure_one()
        if not self.is_current or not self.company_id:
            return
        others = self.sudo().search(
            [
                ("id", "!=", self.id),
                ("company_id", "=", self.company_id.id),
                ("is_current", "=", True),
            ]
        )
        if others:
            others.write({"is_current": False})

    def _ensure_company_has_current_instance(self):
        """If this company has active instances but none current, pick one."""
        self.ensure_one()
        if not self.company_id:
            return
        active_instances = self.sudo().search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)],
            order="id desc",
        )
        if not active_instances:
            return
        if any(active_instances.mapped("is_current")):
            return
        active_instances[:1].write({"is_current": True})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Make 'current' mandatory without making creation painful:
            # if this is the first active instance for the company, auto-select it.
            if vals.get("active", True) and not vals.get("is_current"):
                company_id = vals.get("company_id") or self.env.company.id
                has_current = self.sudo().search_count(
                    [
                        ("company_id", "=", company_id),
                        ("active", "=", True),
                        ("is_current", "=", True),
                    ]
                )
                if not has_current:
                    vals["is_current"] = True

        # Normalize multi-create input so that per company at most one record
        # is created with is_current=True (pick the last one in vals_list).
        last_current_idx_by_company = {}
        for idx, vals in enumerate(vals_list):
            if not vals.get("is_current"):
                continue
            company_id = vals.get("company_id") or self.env.company.id
            last_current_idx_by_company[company_id] = idx

        for idx, vals in enumerate(vals_list):
            # If multiple records are created with is_current=True for the same
            # company, keep only the last one as current.
            if vals.get("is_current"):
                company_id = vals.get("company_id") or self.env.company.id
                if last_current_idx_by_company.get(company_id) != idx:
                    vals["is_current"] = False

        # Pre-clear existing current instances when creating a new current one.
        # This must happen *before* super().create() so constraints don't see
        # two current connectors for a company during validation.
        for company_id, idx in last_current_idx_by_company.items():
            if not vals_list[idx].get("is_current"):
                continue
            self.with_context(**{_CTX_SKIP_CURRENT_ENFORCEMENT: True}).sudo().search(
                [
                    ("company_id", "=", company_id),
                    ("active", "=", True),
                    ("is_current", "=", True),
                ]
            ).write({"is_current": False})

        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list, strict=True):
            if vals.get("is_current"):
                rec._unset_other_current_instances()
            elif rec.active:
                rec._ensure_company_has_current_instance()
        return records

    def write(self, vals):
        vals = dict(vals or {})

        if self.env.context.get(_CTX_SKIP_CURRENT_ENFORCEMENT):
            return super().write(vals)

        if vals.get("is_current") is True:
            for company in self.mapped("company_id"):
                self.with_context(
                    **{_CTX_SKIP_CURRENT_ENFORCEMENT: True}
                ).sudo().search(
                    [
                        ("company_id", "=", company.id),
                        ("active", "=", True),
                        ("is_current", "=", True),
                        ("id", "not in", self.ids),
                    ]
                ).write({"is_current": False})

        if vals.get("active") is True and vals.get("is_current") is not True:
            # Reactivating instances (single or bulk) must also pick exactly one current
            # per company, otherwise constraints will fail inside super().write().
            # Split the write so one record per company becomes current.
            remaining = self
            results = True
            for company in self.mapped("company_id"):
                company_recs = remaining.filtered(
                    lambda r, company=company: r.company_id == company
                )
                if not company_recs:
                    continue
                has_current = self.sudo().search_count(
                    [
                        ("company_id", "=", company.id),
                        ("active", "=", True),
                        ("is_current", "=", True),
                    ]
                )
                if has_current:
                    continue
                rec_to_current = company_recs.sorted("id")[-1]
                others = company_recs - rec_to_current
                results = results and super(
                    BonuscardConnectorInstance, rec_to_current
                ).write({**vals, "is_current": True})
                if others:
                    results = results and super(
                        BonuscardConnectorInstance, others
                    ).write({**vals, "is_current": False})
                remaining -= company_recs
            if remaining:
                results = results and super(
                    BonuscardConnectorInstance, remaining
                ).write(vals)
            return results

        if (
            "is_current" in vals
            and not vals["is_current"]
            and vals.get("active") is not False
        ):
            # Explicitly unsetting is_current on active current records: pre-assign a
            # replacement so the "exactly one current" constraint is satisfied during
            # super().write(). Uses the skip context so the intermediate state (two
            # current records momentarily) does not trip constraints.
            current_to_unset = self.filtered(lambda r: r.is_current and r.active)
            if current_to_unset:
                for company in current_to_unset.mapped("company_id"):
                    company_recs = current_to_unset.filtered(
                        lambda r, c=company: r.company_id == c
                    )
                    replacement = self.sudo().search(
                        [
                            ("company_id", "=", company.id),
                            ("active", "=", True),
                            ("is_current", "=", False),
                            ("id", "not in", company_recs.ids),
                        ],
                        limit=1,
                        order="id desc",
                    )
                    if replacement:
                        replacement.with_context(
                            **{_CTX_SKIP_CURRENT_ENFORCEMENT: True}
                        ).write({"is_current": True})
                    else:
                        raise ValidationError(
                            self.env._(
                                "Cannot unset the current Bonuscard connection for %s — "
                                "no other active connection is available to take over. "
                                "Archive this connection instead.",
                                company.name,
                            )
                        )

        if vals.get("active") is False:
            # Odoo runs constraints during super().write(). If we archive a current
            # connector without clearing is_current first (or picking a replacement),
            # the constraints will raise. Handle this deterministically up-front.
            current_to_archive = self.filtered("is_current")
            if current_to_archive:
                companies = current_to_archive.mapped("company_id")
                for company in companies:
                    replacement = self.sudo().search(
                        [
                            ("company_id", "=", company.id),
                            ("active", "=", True),
                            ("id", "not in", self.ids),
                        ],
                        limit=1,
                        order="id desc",
                    )
                    if replacement:
                        replacement.with_context(
                            **{_CTX_SKIP_CURRENT_ENFORCEMENT: True}
                        ).write({"is_current": True})
                # Clear current flag on the archived records in the same write
                # so constraints see a consistent state.
                vals.setdefault("is_current", False)

        res = super().write(vals)
        if vals.get("is_current"):
            for rec in self.filtered("is_current"):
                rec._unset_other_current_instances()
        # If current is unset explicitly (or by archiving) and there are still active
        # instances, ensure one is current to satisfy the "exactly one" invariant.
        if vals.get("is_current") is False:
            for rec in self:
                rec._ensure_company_has_current_instance()
        if vals.get("active") is True:
            for rec in self.filtered("active"):
                rec._ensure_company_has_current_instance()
        return res

    def action_test_connection(self):
        service = self.env["bonuscard.api.service"]
        failure_messages = []
        for rec in self:
            try:
                service._test_connection(rec)
                rec.write(
                    {
                        "connection_status": "ok",
                        "last_test_at": fields.Datetime.now(),
                        "last_error": False,
                    }
                )
            except Exception as exc:  # pylint: disable=broad-except
                _logger.exception(
                    "Bonuscard connection test failed for instance %s",
                    rec.id,
                )
                error_message = str(exc)
                failure_messages.append(error_message)
                rec.write(
                    {
                        "connection_status": "error",
                        "last_test_at": fields.Datetime.now(),
                        "last_error": error_message,
                    }
                )

        if failure_messages:
            if len(self) == 1:
                message = failure_messages[0]
            else:
                message = self.env._(
                    "%s of %s connection tests failed. First error: %s",
                    len(failure_messages),
                    len(self),
                    failure_messages[0],
                )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Connection Failed"),
                    "message": message,
                    "type": "danger",
                    "sticky": True,
                },
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Success"),
                "message": self.env._(
                    "Bonuscard API credentials verified successfully."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_run_bulk_partner_prefetch(self):
        """Manual UI entry point to run the bulk partner prefetch for this company."""
        self.ensure_one()
        if not self.bulk_partner_prefetch_active:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Bonuscard Bulk Prefetch"),
                    "message": self.env._(
                        "Bulk partner prefetch is disabled for this connection."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        summary = (
            self.env["res.partner"]
            .with_company(self.company_id)
            .action_bulk_prefetch_bonuscard_status(
                company_id=self.company_id.id, instance_id=self.id
            )
        )
        message = self.env._(
            "Processed: %(processed)s (linked=%(linked)s, not_found=%(not_found)s, ambiguous=%(ambiguous)s, error=%(error)s).",
            **summary,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Bonuscard Bulk Prefetch"),
                "message": message,
                "type": "info" if summary.get("error") == 0 else "warning",
                "sticky": False,
            },
        }

    def action_run_bulk_partner_prefetch_force_refresh(self):
        """Manual UI entry point to refresh already-scanned partners (TTL applies)."""
        self.ensure_one()
        if not self.bulk_partner_prefetch_active:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Bonuscard Bulk Prefetch"),
                    "message": self.env._(
                        "Bulk partner prefetch is disabled for this connection."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        summary = (
            self.env["res.partner"]
            .with_company(self.company_id)
            .action_bulk_prefetch_bonuscard_status(
                company_id=self.company_id.id,
                instance_id=self.id,
                force_refresh=True,
            )
        )
        message = self.env._(
            "Processed: %(processed)s (linked=%(linked)s, not_found=%(not_found)s, ambiguous=%(ambiguous)s, error=%(error)s).",
            **summary,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Bonuscard Bulk Prefetch (Refresh)"),
                "message": message,
                "type": "info" if summary.get("error") == 0 else "warning",
                "sticky": False,
            },
        }

    def action_run_catalog_probe(self):
        """Manual UI entry point to probe never-scanned products for this company."""
        self.ensure_one()
        if not self.catalog_probe_active:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Bonuscard Catalog Probe"),
                    "message": self.env._(
                        "Catalog probe is disabled for this connection."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        summary = (
            self.env["product.product"]
            .with_company(self.company_id)
            .action_bulk_probe_catalog_status(
                company_id=self.company_id.id,
                instance_id=self.id,
                only_unscanned=True,
            )
        )
        if not summary.get("ok"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Bonuscard Catalog Probe"),
                    "message": summary.get("message")
                    or self.env._("Catalog probe could not be started."),
                    "type": "warning",
                    "sticky": True,
                },
            }
        message = (
            self.env["product.product"]
            .with_company(self.company_id)
            ._format_catalog_probe_summary_message(summary)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Bonuscard Catalog Probe"),
                "message": message,
                "type": "info" if summary.get("error") == 0 else "warning",
                "sticky": bool(summary.get("message")),
            },
        }

    @api.model
    def _cron_run_catalog_probe(self):
        """Scheduled entry point: probe never-scanned products per active instance."""
        instances = self.sudo().search(
            [("active", "=", True), ("is_current", "=", True)]
        )
        for instance in instances:
            if not instance.catalog_probe_active:
                continue
            if not (instance.catalog_probe_customer_identifier or "").strip():
                continue
            try:
                summary = (
                    self.env["product.product"]
                    .with_company(instance.company_id)
                    .sudo()
                    .action_bulk_probe_catalog_status(
                        company_id=instance.company_id.id,
                        instance_id=instance.id,
                        only_unscanned=True,
                    )
                )
                _logger.info(
                    "Bonuscard catalog probe complete for company=%s processed=%s "
                    "in_catalog=%s not_in_catalog=%s unchanged=%s skipped=%s error=%s",
                    instance.company_id.id,
                    summary.get("processed"),
                    summary.get("in_catalog"),
                    summary.get("not_in_catalog"),
                    summary.get("unchanged"),
                    summary.get("skipped"),
                    summary.get("error"),
                )
                if summary.get("message"):
                    _logger.warning(
                        "Bonuscard catalog probe cancel failed for company=%s: %s",
                        instance.company_id.id,
                        summary.get("message"),
                    )
            except Exception:  # pylint: disable=broad-except
                _logger.exception(
                    "Bonuscard catalog probe cron failed for company %s",
                    instance.company_id.id,
                )

    @api.model
    def _cron_run_bulk_partner_prefetch(self):
        """Scheduled entry point: run prefetch for each active instance/company.

        Uses ``force_refresh=False`` on purpose: the cron only scans partners that
        have never been checked against Bonuscard. Use **Refresh Bulk Prefetch** on
        the connection form to re-check stale partners while respecting TTL.
        """
        instances = self.sudo().search(
            [("active", "=", True), ("is_current", "=", True)]
        )
        for instance in instances:
            if not instance.bulk_partner_prefetch_active:
                continue
            try:
                summary = (
                    self.env["res.partner"]
                    .with_company(instance.company_id)
                    .sudo()
                    .action_bulk_prefetch_bonuscard_status(
                        company_id=instance.company_id.id,
                        instance_id=instance.id,
                        force_refresh=False,
                    )
                )
                _logger.info(
                    "Bonuscard bulk prefetch complete for company=%s processed=%s linked=%s not_found=%s ambiguous=%s error=%s",
                    instance.company_id.id,
                    summary.get("processed"),
                    summary.get("linked"),
                    summary.get("not_found"),
                    summary.get("ambiguous"),
                    summary.get("error"),
                )
            except Exception:  # pylint: disable=broad-except
                _logger.exception(
                    "Bonuscard bulk prefetch cron failed for company %s",
                    instance.company_id.id,
                )
