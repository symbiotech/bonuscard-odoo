import base64
import logging
from urllib.parse import urljoin

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BonuscardConnectorInstance(models.Model):
    _name = "bonuscard.connector.instance"
    _description = "Bonuscard Connection"
    _order = "name asc"

    name = fields.Char(string="Connection Name", required=True)
    active = fields.Boolean(default=True)
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
        default="en-GB",
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

    @api.constrains("api_base_url")
    def _check_api_base_url(self):
        for rec in self:
            if rec.api_base_url and not rec.api_base_url.startswith(
                ("http://", "https://")
            ):
                raise ValidationError(
                    self.env._("API Base URL must start with http:// or https://")
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

    def _build_headers(self):
        self.ensure_one()
        credentials = f"{self.api_username}:{self.api_password}".encode()
        authorization = base64.b64encode(credentials).decode("ascii")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {authorization}",
            "BC-Culture": self.api_culture,
        }

    def _build_url(self, endpoint):
        self.ensure_one()
        base_url = self.api_base_url.rstrip("/") + "/"
        endpoint = endpoint.lstrip("/")
        return urljoin(base_url, endpoint)

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

    @api.model
    def _cron_run_bulk_partner_prefetch(self):
        """Scheduled entry point: run prefetch for each active instance/company.

        Uses ``force_refresh=False`` on purpose: the cron only scans partners that
        have never been checked against Bonuscard. Use **Refresh Bulk Prefetch** on
        the connection form to re-check stale partners while respecting TTL.
        """
        instances = self.sudo().search([("active", "=", True)])
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
