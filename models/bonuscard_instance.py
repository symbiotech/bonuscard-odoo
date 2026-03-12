from urllib.parse import urljoin
import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BonuscardConnectorInstance(models.Model):
    _name = "bonuscard.connector.instance"
    _description = "Bonuscard Connection"
    _order = "name asc"

    name = fields.Char(string="Connection Name", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
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
        string="Connection Status",
        default="unknown",
        readonly=True,
        copy=False,
    )
    last_test_at = fields.Datetime(string="Last Test At", readonly=True, copy=False)
    last_error = fields.Text(string="Last Error", readonly=True, copy=False)

    @api.constrains("api_base_url")
    def _check_api_base_url(self):
        for rec in self:
            if rec.api_base_url and not rec.api_base_url.startswith(
                ("http://", "https://")
            ):
                raise ValidationError(
                    _("API Base URL must start with http:// or https://")
                )

    @api.constrains("request_timeout")
    def _check_timeout(self):
        for rec in self:
            if rec.request_timeout < 1:
                raise ValidationError(_("Request timeout must be at least 1 second."))

    def _build_headers(self):
        self.ensure_one()
        credentials = f"{self.api_username}:{self.api_password}".encode("utf-8")
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
        for rec in self:
            rec.ensure_one()
            try:
                service.test_connection(rec)
                rec.write(
                    {
                        "connection_status": "ok",
                        "last_test_at": fields.Datetime.now(),
                        "last_error": False,
                    }
                )
            except Exception as exc:  # pylint: disable=broad-except
                rec.write(
                    {
                        "connection_status": "error",
                        "last_test_at": fields.Datetime.now(),
                        "last_error": str(exc),
                    }
                )

        return True
