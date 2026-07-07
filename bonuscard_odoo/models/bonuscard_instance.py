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
                    "%s of %s connection tests failed.",
                    len(failure_messages),
                    len(self),
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
