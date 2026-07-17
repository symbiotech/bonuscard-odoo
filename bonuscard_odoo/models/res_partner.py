import logging
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _check_bulk_prefetch_access(self):
        """Allow managers (or sudo/cron) to run bulk prefetch."""
        if self.env.is_superuser() or self.env.su:
            return
        if not self.env.user.has_group("bonuscard_odoo.bonuscard_odoo_group_manager"):
            raise UserError(
                self.env._("You do not have permission to run bulk Bonuscard prefetch.")
            )

    @api.model
    def _build_bulk_prefetch_domain(
        self, *, force_refresh=False, enable_name_fallback=False, cutoff=None
    ):
        """Build the partner domain used by bulk Bonuscard prefetch."""
        if force_refresh:
            if cutoff is None:
                # Safe fallback when callers omit cutoff: behave like cron (never synced).
                sync_domain = [("bonuscard_last_synced_at", "=", False)]
            else:
                sync_domain = [
                    "|",
                    ("bonuscard_last_synced_at", "=", False),
                    ("bonuscard_last_synced_at", "<", cutoff),
                ]
        else:
            sync_domain = [("bonuscard_last_synced_at", "=", False)]

        contact_domain = [
            "|",
            ("phone", "not in", [False, ""]),
            ("email", "not in", [False, ""]),
        ]
        if enable_name_fallback:
            contact_domain = [
                "|",
                "|",
                ("phone", "not in", [False, ""]),
                ("email", "not in", [False, ""]),
                "&",
                "&",
                ("phone", "in", [False, ""]),
                ("email", "in", [False, ""]),
                ("name", "!=", False),
            ]

        # A single sync leaf can be ANDed implicitly with a leading '|' contact domain.
        if len(sync_domain) == 1 and not isinstance(sync_domain[0], str):
            return sync_domain + contact_domain
        return ["&"] + sync_domain + contact_domain

    def _get_bonuscard_prefetch_search_terms(
        self, *, enable_name_fallback: bool = False
    ) -> list[str]:
        """Search terms for bulk prefetch (phone → email → name).

        Name fallback is intentionally constrained: it is only used when the partner
        has no phone/email, and relies on `_filter_exact_bonuscard_matches` to avoid
        linking on name when either side has contact details.
        """
        self.ensure_one()
        terms: list[str] = []
        phone = self._normalize_phone(self.phone)
        if phone:
            terms.append(phone)

        email = (self.email or "").strip().lower()
        if email:
            terms.append(email)

        if enable_name_fallback and not phone and not email:
            name = (self.name or "").strip()
            if name:
                terms.append(name)

        return terms

    bonuscard_recruitment_code = fields.Char(copy=False, readonly=True)
    bonuscard_internal_id = fields.Integer(copy=False, readonly=True)
    bonuscard_pos_search = fields.Char(
        string="Bonuscard POS Search",
        compute="_compute_bonuscard_pos_search",
        search="_search_bonuscard_pos_search",
        readonly=True,
    )
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

    @api.depends("bonuscard_recruitment_code", "bonuscard_internal_id")
    def _compute_bonuscard_pos_search(self):
        for partner in self:
            parts = []
            if partner.bonuscard_recruitment_code:
                parts.append(partner.bonuscard_recruitment_code)
            if partner.bonuscard_internal_id:
                parts.append(str(partner.bonuscard_internal_id))
            partner.bonuscard_pos_search = " ".join(parts) or False

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + [
            "bonuscard_recruitment_code",
            "bonuscard_internal_id",
            "bonuscard_status",
            "bonuscard_last_lookup_note",
        ]

    @api.model
    def _search_bonuscard_pos_search(self, operator, value):
        """Search partners by Bonuscard recruitment code, internal id, or app barcode."""
        # Odoo rewrites ``= False`` / ``!= False`` to ``in`` / ``not in`` [False].
        unset_values = False
        if value is False or value is None:
            unset_values = True
        elif not isinstance(value, (str, bytes)) and hasattr(value, "__iter__"):
            values = list(value)
            unset_values = bool(values) and all(
                item is False or item is None for item in values
            )

        if unset_values:
            if operator in ("=", "in"):
                return [
                    ("bonuscard_recruitment_code", "=", False),
                    ("bonuscard_internal_id", "=", False),
                ]
            if operator in ("!=", "not in"):
                return [
                    "|",
                    ("bonuscard_recruitment_code", "!=", False),
                    ("bonuscard_internal_id", "!=", False),
                ]
            return [("id", "=", 0)]

        value = str(value).strip()
        if not value:
            # Empty POS search box should match nothing.
            return [("id", "=", 0)]
        if operator not in ("ilike", "like", "=", "!=", "not ilike"):
            operator = "ilike"

        domains = [("bonuscard_recruitment_code", operator, value)]
        extracted_id = self._extract_bonuscard_id_from_app_barcode(value)
        if extracted_id:
            internal_id = int(extracted_id)
        elif value.isdigit() and value == str(int(value)):
            # Exact digit string only — reject leading-zero variants like "0724" → 724.
            internal_id = int(value)
        else:
            internal_id = None

        if internal_id is not None:
            if operator in ("!=", "not ilike"):
                # Negation of (code match OR id match) => NOT code AND NOT id.
                domains.append(("bonuscard_internal_id", "!=", internal_id))
            else:
                domains.append(("bonuscard_internal_id", "=", internal_id))

        if len(domains) == 1:
            return domains
        if operator in ("!=", "not ilike"):
            return domains  # implicit AND
        return ["|"] * (len(domains) - 1) + domains

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

    # Minimum significant digits for country-code / trunk-aware phone equality.
    # Short fuzzy SearchCustomers hits (e.g. "0724") must not match via suffix.
    _BONUSCARD_PHONE_MATCH_MIN_DIGITS = 7
    # Bonuscard app member barcodes are EAN-13: prefix + zero-padded internal id + check.
    _BONUSCARD_APP_BARCODE_PREFIX = "999000"
    _BONUSCARD_APP_BARCODE_ID_WIDTH = 6

    def _normalize_phone(self, phone_number):
        if phone_number is None or phone_number is False:
            return ""
        if not isinstance(phone_number, str):
            phone_number = str(phone_number)
        return re.sub(r"\D", "", phone_number)

    @api.model
    def _ean13_check_digit(self, first_12_digits):
        """Return the EAN-13 check digit for the first 12 digit characters."""
        if len(first_12_digits) != 12 or not first_12_digits.isdigit():
            return ""
        total = 0
        for index, char in enumerate(first_12_digits):
            digit = int(char)
            total += digit * 3 if index % 2 else digit
        return str((10 - (total % 10)) % 10)

    @api.model
    def _extract_bonuscard_id_from_app_barcode(self, value):
        """Extract Bonuscard internal id from an app member EAN-13 barcode.

        Format: ``999000`` + 6-digit zero-padded internal id + EAN-13 check digit.
        Example: internal id ``976358`` → ``9990009763581``.
        """
        if value is None or value is False:
            return ""
        digits = self._normalize_phone(str(value))
        prefix = self._BONUSCARD_APP_BARCODE_PREFIX
        id_width = self._BONUSCARD_APP_BARCODE_ID_WIDTH
        expected_len = len(prefix) + id_width + 1
        if len(digits) != expected_len or not digits.startswith(prefix):
            return ""
        body, check = digits[:-1], digits[-1]
        if self._ean13_check_digit(body) != check:
            return ""
        raw_id = digits[len(prefix) : len(prefix) + id_width]
        return str(int(raw_id))

    @api.model
    def _phones_equivalent(self, phone_a, phone_b):
        """Return True when two phones identify the same number.

        Compares digit-only forms, then allows national vs E.164 variants:
        trunk leading ``0`` (e.g. ``0703334601``) and missing country prefix
        (e.g. ``703334601`` vs ``+46703334601``). Requires enough significant
        digits so short fuzzy queries cannot match by suffix.
        """
        a = self._normalize_phone(phone_a)
        b = self._normalize_phone(phone_b)
        if not a or not b:
            return False
        if a == b:
            return True
        a_sig = a.lstrip("0") or a
        b_sig = b.lstrip("0") or b
        if a_sig == b_sig:
            return True
        min_digits = self._BONUSCARD_PHONE_MATCH_MIN_DIGITS
        if len(a_sig) < min_digits or len(b_sig) < min_digits:
            return False
        return a_sig.endswith(b_sig) or b_sig.endswith(a_sig)

    @api.model
    def _bonuscard_customer_matches_pos_query(self, customer, query):
        """Return True when a Bonuscard customer matches a POS search query."""
        query = (query or "").strip()
        if not query or not customer:
            return False

        query_lower = query.lower()
        recruitment_code = (customer.get("recruitmentCode") or "").strip()
        if recruitment_code and recruitment_code.lower() == query_lower:
            return True

        customer_id = customer.get("id")
        if customer_id is not None and str(customer_id) == query:
            return True
        extracted_id = self._extract_bonuscard_id_from_app_barcode(query)
        if (
            extracted_id
            and customer_id is not None
            and str(customer_id) == extracted_id
        ):
            return True

        if self._phones_equivalent(query, customer.get("phoneNumber")):
            return True

        customer_email = (customer.get("email") or "").strip().lower()
        if "@" in query_lower and customer_email == query_lower:
            return True
        return False

    def _filter_exact_bonuscard_matches(self, customers):
        self.ensure_one()
        partner_phone = self.phone
        partner_email = (self.email or "").strip().lower()
        partner_name = (self.name or "").strip().lower()
        partner_has_phone = bool(self._normalize_phone(partner_phone))

        exact_matches = {}
        for index, customer in enumerate(customers):
            customer_phone = customer.get("phoneNumber")
            customer_email = (customer.get("email") or "").strip().lower()
            customer_name = (customer.get("name") or "").strip().lower()
            customer_has_phone = bool(self._normalize_phone(customer_phone))
            customer_key = (
                customer.get("id") or customer.get("recruitmentCode") or index
            )
            if self._phones_equivalent(partner_phone, customer_phone):
                exact_matches[customer_key] = customer
                continue
            if partner_email and customer_email and partner_email == customer_email:
                exact_matches[customer_key] = customer
                continue
            if (
                not partner_has_phone
                and not partner_email
                and not customer_has_phone
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
            if self._phones_equivalent(commercial_partner.phone, self.phone):
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

    def _sync_bonuscard_status_for_bulk_prefetch(
        self,
        *,
        company=None,
        instance=None,
        raise_if_missing_instance=False,
        enable_name_fallback=False,
    ):
        """Bulk-prefetch variant of Bonuscard status sync.

        Uses term order: phone → email → (optional) name.
        Stops on the first term that produces an unambiguous decision.
        """
        self.ensure_one()
        service = self.env["bonuscard.api.service"]
        if not company:
            company = (
                self.company_id
                or self.commercial_partner_id.company_id
                or self.env.company
            )
        if not instance:
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

        terms = self._get_bonuscard_prefetch_search_terms(
            enable_name_fallback=enable_name_fallback
        )
        for term in terms:
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

    @api.model
    def action_bulk_prefetch_bonuscard_status(
        self,
        company_id=None,
        instance_id=None,
        partner_ids=None,
        *,
        force_refresh=False,
    ):
        """Manual/cron entry point: prefetch Bonuscard status for customer partners."""
        # Server-side access control. Cron/manual actions run via sudo and are
        # allowed by `_check_bulk_prefetch_access()`.
        self._check_bulk_prefetch_access()
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
        if not instance:
            return {
                "ok": False,
                "company_id": company.id,
                "processed": 0,
                "linked": 0,
                "not_found": 0,
                "ambiguous": 0,
                "error": 0,
                "skipped": 0,
                "message": self.env._(
                    "No active Bonuscard connection is configured for this company."
                ),
            }
        if company_id and instance.company_id and instance.company_id != company:
            raise UserError(
                self.env._(
                    "Selected Bonuscard connection does not belong to the requested company."
                )
            )
        if not instance.bulk_partner_prefetch_active:
            return {
                "ok": False,
                "company_id": company.id,
                "processed": 0,
                "linked": 0,
                "not_found": 0,
                "ambiguous": 0,
                "error": 0,
                "skipped": 0,
                "message": self.env._(
                    "Bulk partner prefetch is disabled for this connection."
                ),
            }

        ttl_hours = int(instance.bulk_partner_prefetch_ttl_hours or 24)
        batch_size = int(instance.bulk_partner_prefetch_batch_size or 200)
        enable_name_fallback = bool(instance.bulk_partner_prefetch_enable_name_fallback)

        cutoff = fields.Datetime.now() - timedelta(hours=ttl_hours)
        domain = self._build_bulk_prefetch_domain(
            force_refresh=force_refresh,
            enable_name_fallback=enable_name_fallback,
            cutoff=cutoff,
        )
        if partner_ids:
            domain = [("id", "in", partner_ids)] + domain
        # Oldest first to avoid starving older never-synced partners.
        partners = self.search(domain, limit=batch_size, order="id asc")

        summary = {
            "ok": True,
            "company_id": company.id,
            "processed": 0,
            "linked": 0,
            "not_found": 0,
            "ambiguous": 0,
            "error": 0,
            "skipped": 0,
        }
        if not partners:
            return summary

        for partner in partners:
            try:
                result = partner._sync_bonuscard_status_for_bulk_prefetch(
                    company=company,
                    instance=instance,
                    enable_name_fallback=enable_name_fallback,
                )
                status = result.get("status") or partner.bonuscard_status
                summary["processed"] += 1
                if status in ("linked", "not_found", "ambiguous"):
                    summary[status] += 1
                else:
                    summary["error"] += 1
            except Exception:  # pylint: disable=broad-except
                _logger.exception(
                    "Bulk Bonuscard prefetch failed for partner %s", partner.id
                )
                summary["processed"] += 1
                summary["error"] += 1

        return summary

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
    def _dedupe_bonuscard_customers(self, customers):
        unique = {}
        for index, customer in enumerate(customers):
            customer_key = (
                customer.get("id") or customer.get("recruitmentCode") or index
            )
            unique[customer_key] = customer
        return list(unique.values())

    @api.model
    def _filter_bonuscard_customers_for_pos_query(self, customers, query):
        """Pick Bonuscard customers that match a POS search/import query.

        Accepts recruitment code, internal id, app member barcode (EAN-13 embedding
        the internal id), email, or phone. Phone matching is digit-based and allows
        national / trunk-``0`` forms of the same E.164 number; short fuzzy API hits
        (e.g. ``0724``) are still rejected.
        """
        query = (query or "").strip()
        if not query or not customers:
            return []

        customers = self._dedupe_bonuscard_customers(customers)
        exact_matches = {}
        for index, customer in enumerate(customers):
            if not self._bonuscard_customer_matches_pos_query(customer, query):
                continue
            customer_key = (
                customer.get("id") or customer.get("recruitmentCode") or index
            )
            exact_matches[customer_key] = customer

        return list(exact_matches.values())

    @api.model
    def _prepare_partner_vals_from_bonuscard_customer(self, customer, *, company=None):
        name = (customer.get("name") or "").strip()
        phone = (customer.get("phoneNumber") or "").strip()
        recruitment_code = (customer.get("recruitmentCode") or "").strip()
        if not name:
            name = recruitment_code or phone or self.env._("Bonuscard Customer")
        vals = {
            "name": name,
            "phone": phone or False,
            "email": (customer.get("email") or "").strip() or False,
            "street": (customer.get("address") or "").strip() or False,
            "city": (customer.get("city") or "").strip() or False,
            "customer_rank": 1,
        }
        if company:
            vals["company_id"] = company.id
        return vals

    def _apply_bonuscard_customer_details(self, customer):
        self.ensure_one()
        vals = {}
        if customer.get("name") and not (self.name or "").strip():
            vals["name"] = customer["name"]
        if customer.get("phoneNumber") and not (self.phone or "").strip():
            vals["phone"] = customer["phoneNumber"]
        if customer.get("email") and not (self.email or "").strip():
            vals["email"] = customer["email"]
        if customer.get("address") and not (self.street or "").strip():
            vals["street"] = customer["address"]
        if customer.get("city") and not (self.city or "").strip():
            vals["city"] = customer["city"]
        if vals:
            self.write(vals)

    @api.model
    def _find_or_create_partner_from_bonuscard_customer(
        self, customer, *, company=None
    ):
        Partner = self.env["res.partner"]
        recruitment_code = (customer.get("recruitmentCode") or "").strip()
        internal_id = customer.get("id")
        phone = (customer.get("phoneNumber") or "").strip()
        email = (customer.get("email") or "").strip()
        normalized_phone = self._normalize_phone(phone)

        partner = Partner.browse()
        if internal_id:
            partner = Partner.search(
                [("bonuscard_internal_id", "=", internal_id)], limit=1
            )
        if not partner and recruitment_code:
            partner = Partner.search(
                [("bonuscard_recruitment_code", "=", recruitment_code)], limit=1
            )
        if not partner and normalized_phone:
            candidates = Partner.search(
                [
                    "|",
                    ("phone", "ilike", phone),
                    ("phone", "ilike", normalized_phone),
                ],
                limit=20,
            )
            partner = candidates.filtered(
                lambda record: self._phones_equivalent(record.phone, phone)
            )[:1]
        if not partner and email:
            partner = Partner.search([("email", "=ilike", email)], limit=1)

        if partner:
            partner._apply_bonuscard_customer_details(customer)
            return partner

        return Partner.create(
            self._prepare_partner_vals_from_bonuscard_customer(
                customer, company=company
            )
        )

    @api.model
    def import_partner_from_bonuscard_for_pos(self, config_id, query):
        """Search Bonuscard and create or link an Odoo partner for POS."""
        query = (query or "").strip()
        if not query:
            raise UserError(
                self.env._("Enter a phone number or Bonuscard ID to search Bonuscard.")
            )

        config = self.env["pos.config"].browse(config_id).exists()
        if not config:
            raise UserError(self.env._("Point of Sale configuration not found."))

        company = config.company_id or self.env.company
        service = self.env["bonuscard.api.service"]
        instance = service._get_company_instance(company)
        if not instance:
            raise UserError(
                self.env._(
                    "No active Bonuscard connection is configured for this company."
                )
            )

        customers = service._search_customers(instance, query)
        if not customers:
            extracted_id = self._extract_bonuscard_id_from_app_barcode(query)
            if extracted_id and extracted_id != query:
                customers = service._search_customers(instance, extracted_id)
        matches = self._filter_bonuscard_customers_for_pos_query(customers, query)
        if len(matches) != 1:
            if len(matches) > 1:
                raise UserError(
                    self.env._(
                        'Bonuscard returned multiple customers for "%s". Refine your search.',
                        query,
                    )
                )
            if customers:
                raise UserError(
                    self.env._(
                        'No Bonuscard customer exactly matched "%s". Refine your search.',
                        query,
                    )
                )
            raise UserError(self.env._('No Bonuscard customer matched "%s".', query))

        customer = matches[0]
        partner = self._find_or_create_partner_from_bonuscard_customer(
            customer, company=company
        )
        partner._write_bonuscard_status(
            "linked",
            customer=customer,
            note=self.env._('Imported from Bonuscard using "%s".', query),
        )

        return self.get_new_partner(config_id, [("id", "=", partner.id)], 0)

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
