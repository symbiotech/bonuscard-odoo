import re

from odoo import api, fields, models
from odoo.exceptions import UserError


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
        mobile_value = self._fields.get("mobile") and self.mobile or False
        values = [self.phone, mobile_value, self.email, self.name]
        terms = []
        for value in values:
            if not value:
                continue
            normalized = value.strip()
            if normalized and normalized not in terms:
                terms.append(normalized)
        return terms

    def _normalize_phone(self, phone_number):
        if not phone_number:
            return ""
        return re.sub(r"\D", "", phone_number)

    def _filter_exact_bonuscard_matches(self, customers):
        self.ensure_one()
        mobile_value = self._fields.get("mobile") and self.mobile or False
        partner_phone = self._normalize_phone(self.phone or mobile_value)
        partner_email = (self.email or "").strip().lower()
        partner_name = (self.name or "").strip().lower()

        exact_matches = {}
        for index, customer in enumerate(customers):
            customer_phone = self._normalize_phone(customer.get("phoneNumber"))
            customer_email = (customer.get("email") or "").strip().lower()
            customer_name = (customer.get("name") or "").strip().lower()
            customer_key = customer.get("id") or customer.get("recruitmentCode") or index
            if partner_phone and customer_phone and partner_phone == customer_phone:
                exact_matches[customer_key] = customer
                continue
            if partner_email and customer_email and partner_email == customer_email:
                exact_matches[customer_key] = customer
                continue
            if partner_name and customer_name and partner_name == customer_name:
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
        return values

    def _sync_bonuscard_status(self, raise_if_missing_instance=False):
        self.ensure_one()
        service = self.env["bonuscard.api.service"]
        partner = self.commercial_partner_id
        company = self.env.company or partner.company_id
        instance = service._get_company_instance(company)
        if not instance:
            if raise_if_missing_instance:
                raise UserError(
                    self.env._(
                        "No active Bonuscard connection is configured for this company."
                    )
                )
            partner._write_bonuscard_status(
                "error",
                note=self.env._("No active Bonuscard connection is configured."),
            )
            return {
                "status": partner.bonuscard_status,
                "note": partner.bonuscard_last_lookup_note,
            }

        for term in partner._get_bonuscard_search_terms():
            customers = service.search_customers(instance, term)
            if not customers:
                continue
            exact_matches = partner._filter_exact_bonuscard_matches(customers)
            if len(exact_matches) == 1:
                customer = exact_matches[0]
                values = partner._write_bonuscard_status(
                    "linked",
                    customer=customer,
                    note=self.env._("Matched Bonuscard customer using %s.", term),
                )
                if self != partner:
                    self.write(values)
                return {
                    "status": "linked",
                    "recruitment_code": customer.get("recruitmentCode"),
                    "name": customer.get("name"),
                    "note": partner.bonuscard_last_lookup_note,
                }
            if len(exact_matches) > 1 or len(customers) > 1:
                values = partner._write_bonuscard_status(
                    "ambiguous",
                    note=self.env._(
                        "Bonuscard returned multiple customer matches for %s.", term
                    ),
                )
                if self != partner:
                    self.write(values)
                return {
                    "status": "ambiguous",
                    "note": partner.bonuscard_last_lookup_note,
                }
            customer = customers[0]
            values = partner._write_bonuscard_status(
                "linked",
                customer=customer,
                note=self.env._("Matched Bonuscard customer using %s.", term),
            )
            if self != partner:
                self.write(values)
            return {
                "status": "linked",
                "recruitment_code": customer.get("recruitmentCode"),
                "name": customer.get("name"),
                "note": partner.bonuscard_last_lookup_note,
            }

        values = partner._write_bonuscard_status(
            "not_found",
            note=self.env._(
                "No Bonuscard customer matched the available partner details."
            ),
        )
        if self != partner:
            self.write(values)
        return {"status": "not_found", "note": partner.bonuscard_last_lookup_note}

    def action_refresh_bonuscard_status(self):
        for partner in self:
            partner._sync_bonuscard_status(raise_if_missing_instance=True)
        return True

    def action_clear_bonuscard_link(self):
        for partner in self:
            partner._write_bonuscard_status(
                "not_checked",
                note=self.env._("Bonuscard status reset manually."),
            )
        return True

    @api.model
    def get_bonuscard_status_for_pos(self, partner_id):
        partner = self.browse(partner_id).exists()
        if not partner:
            return {"status": "not_found", "note": self.env._("Customer not found.")}
        result = partner._sync_bonuscard_status()
        commercial_partner = partner.commercial_partner_id
        return {
            "status": result.get("status"),
            "recruitment_code": commercial_partner.bonuscard_recruitment_code,
            "note": commercial_partner.bonuscard_last_lookup_note,
        }
