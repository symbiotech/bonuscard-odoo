import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    bonuscard_catalog_status = fields.Selection(
        selection=[
            ("not_set", "Not Set"),
            ("in_catalog", "In Bonuscard Catalog"),
            ("not_in_catalog", "Not in Bonuscard Catalog"),
        ],
        string="Bonuscard Catalog",
        default="not_set",
        copy=False,
        tracking=True,
    )
    bonuscard_catalog_updated_at = fields.Datetime(
        string="Bonuscard Catalog Updated",
        copy=False,
        readonly=True,
    )
    bonuscard_catalog_probe_note = fields.Text(
        string="Bonuscard Catalog Probe Note",
        copy=False,
        readonly=True,
        groups="bonuscard_odoo.bonuscard_odoo_group_manager",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["bonuscard_catalog_status"]

    @api.model
    def _check_catalog_probe_access(self):
        """Allow managers (or sudo/cron) to probe Bonuscard catalog status."""
        if self.env.is_superuser() or self.env.su:
            return
        if not self.env.user.has_group("bonuscard_odoo.bonuscard_odoo_group_manager"):
            raise UserError(
                self.env._(
                    "You do not have permission to probe Bonuscard catalog status."
                )
            )

    @api.model
    def _build_catalog_probe_domain(self):
        return [
            ("bonuscard_catalog_status", "=", "not_set"),
            ("active", "=", True),
            "|",
            ("barcode", "!=", False),
            ("default_code", "!=", False),
        ]

    @api.constrains("bonuscard_catalog_status", "barcode", "default_code")
    def _check_bonuscard_catalog_requires_identifier(self):
        for product in self:
            if product.bonuscard_catalog_status != "in_catalog":
                continue
            if not (product.barcode or product.default_code):
                raise ValidationError(
                    self.env._(
                        "A product must have a barcode or article number before it "
                        "can be marked as in the Bonuscard catalog."
                    )
                )

    def _bonuscard_write_catalog_status(self, status):
        self.write(
            {
                "bonuscard_catalog_status": status,
                "bonuscard_catalog_updated_at": fields.Datetime.now(),
            }
        )

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        patched = []
        for vals in vals_list:
            vals = dict(vals or {})
            if (
                "bonuscard_catalog_status" in vals
                and "bonuscard_catalog_updated_at" not in vals
            ):
                vals["bonuscard_catalog_updated_at"] = now
            patched.append(vals)
        return super().create(patched)

    def write(self, vals):
        vals = dict(vals or {})
        if (
            "bonuscard_catalog_status" in vals
            and "bonuscard_catalog_updated_at" not in vals
        ):
            now = fields.Datetime.now()
            # Only set updated_at when status actually changes for at least one record.
            if any(
                product.bonuscard_catalog_status != vals["bonuscard_catalog_status"]
                for product in self
            ):
                vals["bonuscard_catalog_updated_at"] = now
        return super().write(vals)

    def _bonuscard_probe_catalog_status_single(
        self,
        instance,
        transaction_identifier=None,
        *,
        auto_cancel=True,
    ):
        self.ensure_one()
        service = self.env["bonuscard.api.service"]
        result = service.probe_product_catalog_status(
            instance,
            self,
            transaction_identifier=transaction_identifier,
            auto_cancel=auto_cancel,
        )
        status = result.get("status")
        note = result.get("note") or ""

        vals = {"bonuscard_catalog_probe_note": note}
        if status in ("in_catalog", "not_in_catalog"):
            vals["bonuscard_catalog_status"] = status
            vals["bonuscard_catalog_updated_at"] = fields.Datetime.now()
        self.write(vals)
        return result

    @api.model
    def _format_catalog_probe_summary_message(self, summary):
        stats = self.env._(
            "Processed: %(processed)s (in_catalog=%(in_catalog)s, "
            "not_in_catalog=%(not_in_catalog)s, unchanged=%(unchanged)s, "
            "skipped=%(skipped)s, error=%(error)s).",
            **summary,
        )
        cancel_message = summary.get("message")
        if cancel_message:
            return self.env._(
                "%(stats)s %(cancel_message)s",
                stats=stats,
                cancel_message=cancel_message,
            )
        return stats

    @api.model
    def action_bulk_probe_catalog_status(
        self,
        company_id=None,
        instance_id=None,
        product_ids=None,
        *,
        only_unscanned=True,
    ):
        """Manual/cron entry point: probe Bonuscard catalog status for products."""
        self._check_catalog_probe_access()
        company = (
            self.env["res.company"].browse(company_id).exists()
            if company_id
            else self.env.company
        )
        service = self.env["bonuscard.api.service"]
        instance = (
            self.env["bonuscard.connector.instance"].browse(instance_id).exists()
            if instance_id
            else service._get_company_instance(company)
        )
        summary = {
            "ok": True,
            "company_id": company.id,
            "processed": 0,
            "in_catalog": 0,
            "not_in_catalog": 0,
            "unchanged": 0,
            "skipped": 0,
            "error": 0,
        }
        if not instance:
            summary["ok"] = False
            summary["message"] = self.env._(
                "No active Bonuscard connection is configured for this company."
            )
            return summary
        if company_id and instance.company_id and instance.company_id != company:
            raise UserError(
                self.env._(
                    "Selected Bonuscard connection does not belong to the requested company."
                )
            )
        if not instance.catalog_probe_active:
            summary["ok"] = False
            summary["message"] = self.env._(
                "Catalog probe is disabled for this connection."
            )
            return summary
        if not (instance.catalog_probe_customer_identifier or "").strip():
            summary["ok"] = False
            summary["message"] = self.env._(
                "Catalog probe customer identifier is not configured on the Bonuscard connection."
            )
            return summary

        domain = (
            self._build_catalog_probe_domain()
            if only_unscanned
            else [("active", "=", True)]
        )
        if product_ids is not None:
            domain = [("id", "in", product_ids)] + domain

        batch_size = int(instance.catalog_probe_batch_size or 50)
        if product_ids and not only_unscanned:
            products = self.search(domain, order="id asc")
        else:
            products = self.search(domain, limit=batch_size, order="id asc")

        configured_unlock_ean = (
            instance.catalog_probe_unlock_ean or ""
        ).strip() or None
        unlock_ean = configured_unlock_ean
        for product in products:
            try:
                result = product._bonuscard_probe_catalog_status_single(instance)
                status = result.get("status") or "unchanged"
                if status == "in_catalog":
                    unlock_ean = (
                        unlock_ean or product.barcode or product.default_code or None
                    )
                summary["processed"] += 1
                if status in summary:
                    summary[status] += 1
                else:
                    summary["unchanged"] += 1
                if (
                    not configured_unlock_ean
                    and status in ("not_in_catalog", "error")
                    and unlock_ean
                ):
                    service._release_probe_customer_lock(instance, unlock_ean)
            except Exception:  # pylint: disable=broad-except
                _logger.exception(
                    "Bonuscard catalog probe failed for product %s", product.id
                )
                summary["processed"] += 1
                summary["error"] += 1

        return summary

    def action_bonuscard_probe_catalog_status(self):
        self._check_catalog_probe_access()
        company = self.env.company
        service = self.env["bonuscard.api.service"]
        instance = service._get_company_instance(company)
        if not instance:
            raise UserError(
                self.env._(
                    "No active Bonuscard connection is configured for this company."
                )
            )
        if not (instance.catalog_probe_customer_identifier or "").strip():
            raise UserError(
                self.env._(
                    "Catalog probe customer identifier is not configured on the "
                    "Bonuscard connection."
                )
            )

        summary = self.with_company(company).action_bulk_probe_catalog_status(
            company_id=company.id,
            instance_id=instance.id,
            product_ids=self.ids,
            only_unscanned=False,
        )
        if not summary.get("ok"):
            raise UserError(
                summary.get("message")
                or self.env._("Bonuscard catalog probe could not be started.")
            )

        message = self._format_catalog_probe_summary_message(summary)
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

    def action_bonuscard_mark_in_catalog(self):
        invalid = self.filtered(
            lambda product: not (product.barcode or product.default_code)
        )
        if invalid:
            raise ValidationError(
                self.env._(
                    "These products cannot be marked as in the Bonuscard catalog "
                    "because they have no barcode or article number: %s",
                    ", ".join(invalid.mapped("display_name")),
                )
            )
        self._bonuscard_write_catalog_status("in_catalog")
        return True

    def action_bonuscard_mark_not_in_catalog(self):
        self._bonuscard_write_catalog_status("not_in_catalog")
        return True

    def action_bonuscard_reset_catalog_status(self):
        self._bonuscard_write_catalog_status("not_set")
        return True
