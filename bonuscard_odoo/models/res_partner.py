import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    bonuscard_recruitment_code = fields.Char(copy=False, readonly=True)
    bonuscard_internal_id = fields.Integer(copy=False, readonly=True)
    bonuscard_status = fields.Selection(
        selection=[
            ("not_checked", "Not Checked"),
            ("linked", "Linked"),
            ("not_found", "Not Found"),
            ("ambiguous", "Multiple Matches"),
            ("error", "Error"),
        ],
        default="not_checked",
        copy=False,
        readonly=True,
    )
    bonuscard_last_synced_at = fields.Datetime(copy=False, readonly=True)
    bonuscard_last_lookup_note = fields.Text(copy=False, readonly=True)

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + [
            "bonuscard_recruitment_code",
            "bonuscard_status",
            "bonuscard_last_lookup_note",
        ]

    def _get_bonuscard_search_terms(self):
        self.ensure_one()
        candidates = [
            self._normalize_phone(self.phone),
        ] + [v.strip() for v in [self.email, self.name] if v]
        terms = []
        for value in candidates:
            if value and value not in terms:
                terms.append(value)
        return terms

    def _normalize_phone(self, phone_number):
        if not phone_number:
            return ""
        return re.sub(r"\D", "", phone_number)

    def _filter_exact_bonuscard_matches(self, customers):
        self.ensure_one()
        partner_phone = self._normalize_phone(self.phone)
        partner_email = (self.email or "").strip().lower()
        partner_name = (self.name or "").strip().lower()

        exact_matches = {}
        for index, customer in enumerate(customers):
            customer_phone = self._normalize_phone(customer.get("phoneNumber"))
            customer_email = (customer.get("email") or "").strip().lower()
            customer_name = (customer.get("name") or "").strip().lower()
            customer_key = (
                customer.get("id") or customer.get("recruitmentCode") or index
            )
            if customer_phone and partner_phone and partner_phone == customer_phone:
                exact_matches[customer_key] = customer
                continue
            if partner_email and customer_email and partner_email == customer_email:
                exact_matches[customer_key] = customer
                continue
            if (
                not partner_phone
                and not partner_email
                and not customer_phone
                and not customer_email
                and partner_name
                and customer_name
                and partner_name == customer_name
            ):
                exact_matches[customer_key] = customer
        return list(exact_matches.values())

    def _write_bonuscard_status(self, status, customer=None, note=None):
        self.ensure_one()
        values = {
            "bonuscard_status": status,
            "bonuscard_last_synced_at": fields.Datetime.now(),
            "bonuscard_last_lookup_note": note or False,
        }
        if customer:
            values.update(
                {
                    "bonuscard_recruitment_code": customer.get("recruitmentCode")
                    or False,
                    "bonuscard_internal_id": customer.get("id") or False,
                }
            )
        elif status != "linked":
            values.update(
                {
                    "bonuscard_recruitment_code": False,
                    "bonuscard_internal_id": False,
                }
            )
        self.write(values)
        # Phone is the unique identifier on the Bonuscard side, so a contact and its
        # commercial partner sharing the same phone number represent the same Bonuscard
        # entity.  Keep both records in sync to avoid stale status on either record.
        commercial_partner = self.commercial_partner_id
        if commercial_partner and commercial_partner != self:
            company_phone = self._normalize_phone(commercial_partner.phone)
            self_phone = self._normalize_phone(self.phone)
            if company_phone and self_phone and company_phone == self_phone:
                commercial_partner._write_bonuscard_status(
                    status, customer=customer, note=note
                )
        return values

    def _sync_bonuscard_status(self, raise_if_missing_instance=False):
        self.ensure_one()
        service = self.env["bonuscard.api.service"]
        company = (
            self.company_id or self.commercial_partner_id.company_id or self.env.company
        )
        instance = service._get_company_instance(company)
        if not instance:
            if raise_if_missing_instance:
                raise UserError(
                    self.env._(
                        "No active Bonuscard connection is configured for this company."
                    )
                )
            self._write_bonuscard_status(
                "error",
                note=self.env._("No active Bonuscard connection is configured."),
            )
            return {
                "status": self.bonuscard_status,
                "note": self.bonuscard_last_lookup_note,
            }

        for term in self._get_bonuscard_search_terms():
            customers = service._search_customers(instance, term)
            if not customers:
                continue
            exact_matches = self._filter_exact_bonuscard_matches(customers)
            if len(exact_matches) == 1:
                customer = exact_matches[0]
                self._write_bonuscard_status(
                    "linked",
                    customer=customer,
                    note=self.env._("Matched Bonuscard customer using %s.", term),
                )
                return {
                    "status": "linked",
                    "recruitment_code": customer.get("recruitmentCode"),
                    "name": customer.get("name"),
                    "note": self.bonuscard_last_lookup_note,
                }
            if len(exact_matches) > 1 or len(customers) > 1:
                self._write_bonuscard_status(
                    "ambiguous",
                    note=self.env._(
                        "Bonuscard returned multiple customer matches for %s.", term
                    ),
                )
                return {
                    "status": "ambiguous",
                    "note": self.bonuscard_last_lookup_note,
                }

        self._write_bonuscard_status(
            "not_found",
            note=self.env._(
                "No Bonuscard customer matched the available partner details."
            ),
        )
        return {"status": "not_found", "note": self.bonuscard_last_lookup_note}

    def action_refresh_bonuscard_status(self):
        for partner in self:
            partner._sync_bonuscard_status(raise_if_missing_instance=True)
        return True

    def action_clear_bonuscard_link(self):
        for partner in self:
            partner._write_bonuscard_status(
                "not_checked",
                note=partner.env._("Bonuscard status reset manually."),
            )
        return True

    def action_register_to_bonuscard(self):
        self.ensure_one()
        service = self.env["bonuscard.api.service"]
        company = (
            self.company_id or self.commercial_partner_id.company_id or self.env.company
        )
        instance = service._get_company_instance(company)
        if not instance:
            raise UserError(
                self.env._(
                    "No active Bonuscard connection is configured for this company."
                )
            )

        phone_number = (self.phone or "").strip()
        if not phone_number:
            raise UserError(
                self.env._(
                    "Partner must have a phone number to register with Bonuscard."
                )
            )

        try:
            search_result = self._sync_bonuscard_status(raise_if_missing_instance=True)
            if search_result.get("status") == "linked":
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": self.env._("Success"),
                        "message": self.env._(
                            "Customer is already registered in Bonuscard and has been linked."
                        ),
                        "type": "info",
                        "sticky": False,
                    },
                }
            if search_result.get("status") == "ambiguous":
                raise UserError(
                    self.env._(
                        "Bonuscard returned multiple matches for the customer. "
                        "Please verify the partner details before attempting registration."
                    )
                )
            if search_result.get("status") == "error":
                raise UserError(
                    self.env._(
                        "Could not verify the Bonuscard status before registration: %s",
                        search_result.get("note"),
                    )
                )

            result = service._register_customer(instance, phone_number=phone_number)
            if result.get("error"):
                messages = result.get("messages") or [
                    self.env._("Bonuscard registration failed.")
                ]
                error_note = " | ".join(messages)
                raise UserError(error_note)

            customer = result.get("customer") or {}
            if not customer.get("recruitmentCode"):
                raise UserError(
                    self.env._(
                        "Bonuscard registration succeeded but no recruitment code was returned."
                    )
                )
            note = self.env._(
                "Successfully registered to Bonuscard on %s.",
                fields.Datetime.now(),
            )
            self._write_bonuscard_status("linked", customer=customer, note=note)

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Success"),
                    "message": self.env._(
                        "Customer registered successfully. Recruitment code: %s. The customer will receive an SMS with a link to complete the registration on the Bonuscard website.",
                        customer.get("recruitmentCode"),
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as exc:
            if isinstance(exc, UserError):
                raise
            _logger.exception(
                "Unexpected error during Bonuscard registration for partner %s",
                self.id,
            )
            raise UserError(
                self.env._("Bonuscard registration failed: %s", str(exc))
            ) from exc

    @api.model
    def get_bonuscard_status_for_pos(self, partner_id):
        partner = self.browse(partner_id).exists()
        if not partner:
            return {"status": "not_found", "note": self.env._("Customer not found.")}
        result = partner._sync_bonuscard_status()
        return {
            "status": result.get("status"),
            "recruitment_code": partner.bonuscard_recruitment_code,
            "note": partner.bonuscard_last_lookup_note,
        }
