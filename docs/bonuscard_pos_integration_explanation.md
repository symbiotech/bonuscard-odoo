# Bonuscard POS Integration

This document explains how the Bonuscard POS integration works in the `bonuscard_odoo` module.

## Diagram file
- `docs/bonuscard_pos_integration_diagram.mmd`

## Integration steps

1. Customer selected in POS
   - `bonuscard_odoo/static/src/app/bonuscard_pos.js` extends `PosStore.setPartnerToCurrentOrder`
   - Calls `res.partner.get_bonuscard_status_for_pos` to resolve Bonuscard status **unless** the partner already has status `linked` or `not_found` (cached from a prior lookup or the bulk prefetch job)
   - The backend searches Bonuscard using customer phone, email, or name
   - The partner record is updated with `bonuscard_status` and `bonuscard_recruitment_code`
   - Status badges are rendered by `bonuscard_partner_line.xml`; status changes trigger POS notifications (success for `linked`, warnings for `not_found`/`ambiguous`, danger for `error`)

2. Manual partner registration
   - If the lookup returns `not_found`, registration is available from two entry points:
     - Partner form: **Register to Bonuscard** button (`res.partner.action_register_to_bonuscard`)
     - POS partner list: **Register with Bonuscard** dropdown item (`bonuscard_partner_line_extension.xml` via `BonuscardRegistrationService`)
   - `action_register_to_bonuscard` re-checks the partner against Bonuscard before registering
   - If still not found, it calls `RegisterCustomer`, writes the returned `recruitmentCode`, and links the partner
   - After POS registration, `BonuscardRegistrationService` refreshes partner status in the POS session
   - Error handling: `BonuscardRegistrationService._extractErrorMessage` extracts detailed error messages from backend exceptions to show meaningful notifications to the cashier (e.g., "Partner must have a phone number to register with Bonuscard." instead of a generic "Odoo Server Error")

3. Continuous purchase validation
   - `_validateBonuscardPurchaseForOrder` is called in multiple situations:
     - Immediately after partner selection, if `bonuscard_status` resolves to `linked`
     - When a product line is added via `addLineToOrder` and the partner has a `bonuscard_recruitment_code`
     - When a line quantity or price is edited via `OrderSummary._setValue` / `updateQuantityNumber`
     - As a final guard in `PosStore.pay()` whenever the partner has a `bonuscard_recruitment_code`
   - Each call builds `orderLines` from products marked `in_catalog` on `product.product`, with `qty > 0`, `price_unit > 0`, and a barcode or article number
   - Calls `bonuscard.api.service.validate_purchase_for_pos`
   - Stores `order.bonuscard_transaction_id`, `order.bonuscard_checkout_items`, and `order.bonuscard_partner_id`
   - Clears `bonuscard_needs_validation` on successful validation
   - If discounts are returned (`totalDiscount > 0`), they are applied automatically to the order via `_applyBonuscardDiscountsToOrder` — as percentage discounts on matched order lines, or as separate discount lines using the POS discount product when partial coverage remains; when no POS discount product is configured, partial coverage is applied as a proportional line discount instead
   - If the POS discount product is not configured, the cashier sees a warning; proportional discounts can still apply to matched lines, but discounts that cannot be matched to a line may not apply
   - The POS generates the `transactionIdentifier` client-side (GUID without dashes) before the first validation, so concurrent validations (e.g. add product, then immediately edit quantity) all send the same identifier — this prevents Bonuscard error 2 (customer locked) caused by a racing request arriving without an identifier
   - Concurrent calls are guarded by a version counter; stale results are discarded, but their `transactionIdentifier` is still stored so the lock can always be cancelled
   - Previous discounts are cleared (`_clearAppliedBonuscardDiscounts`) before each new validation
   - On Bonuscard error code 2 (customer locked), the POS cancels the current or any other order's pending transaction for the same partner (including already paid orders) and retries validation once
   - When the cart has no Bonuscard catalog lines, no `ValidatePurchase` call is made; if a pending transaction already exists from earlier catalog lines, it is cancelled

4. Payment confirmation
   - `OrderPaymentValidation.afterOrderValidation()` finalizes or cancels the pending Bonuscard transaction
   - When checkout items exist (including zero-discount validations for accumulation programs), it calls `bonuscard.api.service.finalize_purchase_for_pos` to register the purchase with Bonuscard
   - This sends the stored `transactionIdentifier` and `checkoutItems` to Bonuscard
   - Finalization is retried once on failure; on success the POS clears `order.bonuscard_transaction_id` and `order.bonuscard_checkout_items`
   - If there is a pending transaction but no checkout items to finalize (e.g. the cart ended up with no `in_catalog` products), the POS cancels the pending transaction after payment instead of leaving the customer locked; cancel failure is logged and shown as a sticky warning
   - If finalization fails after payment, the POS attempts cancel as a fallback before showing a sticky warning
   - If the cancel fallback succeeds, the transaction fields are cleared and the backend audit state is stored as `failed`
   - If finalization and the cancel fallback both fail, the transaction fields are kept and a sticky warning is shown so the loyalty lock can be recovered manually

5. Cancel or rollback flows
   - `PosStore.onClickBackButton()` (only when on the Payment Screen), `onDeleteOrder()`, `closePos()`, `addNewOrder()`, and `setOrder()` cancel pending Bonuscard transactions on the order being left behind
   - `setPartnerToCurrentOrder` cancels an open transaction **before** changing the partner; if cancel fails, the partner change is blocked to avoid orphaning the Bonuscard lock
   - All cancel paths call `bonuscard.api.service.cancel_purchase_for_pos`
   - `closePos` and `onDeleteOrder` retry cancel once; local transaction state is cleared only after a successful cancel
   - After cancel failure (including after the single retry), cashier-facing sticky warnings are shown:
     - **Partner change** (`setPartnerToCurrentOrder`): blocked; current customer and transaction state are kept
     - **Order deletion** (`onDeleteOrder`): blocked; the order is kept so cancellation can be retried
     - **POS close** (`closePos`): close continues, but transaction state is kept locally and the cashier is warned the Bonuscard lock may remain until it expires
   - `PosOrder.removeOrderline` clears `bonuscard_checkout_items` and sets `bonuscard_needs_validation` so the next action re-validates
   - `PosOrderline.setQuantity` and `PosOrderline.delete` also set `bonuscard_needs_validation` when called outside of the discount-application cycle

## Backend components

- `bonuscard.connector.instance`
  - Stores Bonuscard API URL, credentials, culture, and timeout
  - One connection per company is selected via the **Use for Bonuscard API** (`is_current`) flag
  - Used by all Bonuscard API requests

- `bonuscard.api.service`
  - Abstract model that performs HTTP calls to Bonuscard
  - Implements `validate_purchase_for_pos`, `finalize_purchase_for_pos`, and `cancel_purchase_for_pos`
  - Handles error mapping and non-blocking POS responses

- `res.partner` extension
  - Adds fields:
    - `bonuscard_recruitment_code`
    - `bonuscard_internal_id`
    - `bonuscard_status`
    - `bonuscard_last_synced_at`
    - `bonuscard_last_lookup_note`
  - Implements search/match logic and status synchronization
  - When status is written for a contact, the same status is also written to its commercial partner if both share the same phone number
  - Adds `action_register_to_bonuscard`, `action_refresh_bonuscard_status`, and `action_clear_bonuscard_link`
  - Adds `action_bulk_prefetch_bonuscard_status` to prefetch linking in batches (used by the cron job and the connection form button)

- `product.product` extension
  - Adds `bonuscard_catalog_status` (`not_set`, `in_catalog`, `not_in_catalog`)
  - Products marked `in_catalog` must have a barcode or article number
    (`default_code` / internal reference)
  - Only `in_catalog` products are sent to Bonuscard from POS
  - Bulk list actions and CSV import can maintain catalog membership manually
  - **Check Bonuscard Catalog** (managers only) probes catalog membership via
    `ValidatePurchase` using the dedicated test customer on the connection; unknown
    products are detected when Bonuscard returns no `transactionIdentifier`.
    Bulk probes reuse one `transactionIdentifier` across the batch and cancel once
    at the end so the probe customer is not locked (Bonuscard API error code 2).
  - Adds `bonuscard_catalog_probe_note` with the last probe message
  - Form editing on **Inventory > Products** (single-variant setups), **Product
    Variants**, and the POS **Edit Product** modal for Bonuscard users
  - POS product info popup (long-press on a product tile) displays catalog
    status for single-variant products
  - Used when Odoo **Product Variants** are enabled (variant list/form UI)

- `bonuscard.connector.instance` catalog probe settings (managers only)
  - `catalog_probe_customer_identifier`, `catalog_probe_price` (default 100),
    `catalog_probe_batch_size`, and `catalog_probe_active`
  - Daily cron probes never-scanned products (`not_set` with barcode/article)
  - Manual **Run Catalog Probe** on the connection form uses the same scope as cron

- `product.template` extension
  - Mirrors catalog status from the single underlying variant for list visibility
  - Writable on template forms (inverse writes the single variant) for Bonuscard
    users when the product has exactly one variant
  - List columns, filters, and bulk actions on **Inventory > Products** for
    Bonuscard users who do not have the Product Variants user group (hidden via
    a variant-group view override when variants are enabled)
  - Refuses template-level bulk updates when the user has Product Variants
    enabled or when a template does not have exactly one variant

- `pos.order` extension
  - Adds audit fields: `bonuscard_state`, `bonuscard_transaction_identifier`,
    `bonuscard_validated_at`, `bonuscard_finalized_at`, `bonuscard_last_error_message`
  - `_process_order` maps audit values from the POS UI payload onto the backend
    record when the order is synced
  - List/form/search views on **Point of Sale > Orders** expose the audit fields
    and filters (Finalized, Validated, Skipped, Failed, Not applicable)

## Important state tracked in POS

- `order.bonuscard_partner_id`
- `order.bonuscard_transaction_id`
- `order.bonuscard_checkout_items`
- `order.bonuscard_needs_validation` — set when lines change; cleared after a successful validation

- `order._bonuscardCandidateTxId` — client-generated transaction identifier not yet confirmed by a successful validation; included in cancel paths so a sent-but-unconfirmed ID is not lost before Bonuscard confirms it

These fields ensure the POS finalizes or cancels the exact Bonuscard transaction that was validated before payment, and re-validates when the order content changes.

## Bonuscard audit state stored on POS orders (backend)

For reporting and audit in Odoo, the integration also persists a lightweight
status on the resulting `pos.order`:

- `pos.order.bonuscard_state` — `not_applicable`, `skipped`, `validated`, `finalized`, `failed`
- `pos.order.bonuscard_transaction_identifier`
- `pos.order.bonuscard_validated_at`
- `pos.order.bonuscard_finalized_at`
- `pos.order.bonuscard_last_error_message`

The POS frontend includes these keys in `PosOrder.serializeForORM()`, and
`pos.order._process_order` maps them onto the backend record when the order is
synced. Runtime Bonuscard transaction fields on the POS order are still cleared
after finalize/cancel, but the persisted audit fields remain on `pos.order` for
reporting.
