# Bonuscard POS Integration

This document explains how the Bonuscard POS integration works in the `bonuscard_odoo` module.

## Diagram file
- `docs/bonuscard_pos_integration_diagram.mmd`

## Integration steps

1. Customer selected in POS
   - `bonuscard_odoo/static/src/app/bonuscard_pos.js` extends `PosStore.setPartnerToCurrentOrder`
   - Calls `res.partner.get_bonuscard_status_for_pos` to resolve Bonuscard status **unless** the partner already has status `linked` or `not_found` (cached from a prior lookup)
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
   - Each call builds `orderLines` from products that have `barcode` or `default_code`, with `qty > 0` and `price_unit > 0`
   - Calls `bonuscard.api.service.validate_purchase_for_pos`
   - Stores `order.bonuscard_transaction_id`, `order.bonuscard_checkout_items`, and `order.bonuscard_partner_id`
   - Clears `bonuscard_needs_validation` on successful validation
  - If discounts are returned (`totalDiscount > 0`), they are applied automatically to the order via `_applyBonuscardDiscountsToOrder` — as percentage discounts on matched order lines, or as separate discount lines using the POS discount product when partial coverage remains; when no POS discount product is configured, partial coverage is applied as a proportional line discount instead
  - If the POS discount product is not configured, the cashier sees a warning; proportional discounts can still apply to matched lines, but discounts that cannot be matched to a line may not apply
   - The POS generates the `transactionIdentifier` client-side (GUID without dashes) before the first validation, so concurrent validations (e.g. add product, then immediately edit quantity) all send the same identifier — this prevents Bonuscard error 2 (customer locked) caused by a racing request arriving without an identifier
   - Concurrent calls are guarded by a version counter; stale results are discarded, but their `transactionIdentifier` is still stored so the lock can always be cancelled
   - Previous discounts are cleared (`_clearAppliedBonuscardDiscounts`) before each new validation
   - On Bonuscard error code 2 (customer locked), the POS cancels the current or any other order's pending transaction for the same partner (including already paid orders) and retries validation once
   - When the cart has no Bonuscard-eligible lines (no barcode/article number), any pending transaction is cancelled instead of being left open

4. Payment confirmation
   - `OrderPaymentValidation.afterOrderValidation()` finalizes or cancels the pending Bonuscard transaction
   - When checkout items exist (including zero-discount validations for accumulation programs), it calls `bonuscard.api.service.finalize_purchase_for_pos` to register the purchase with Bonuscard
   - This sends the stored `transactionIdentifier` and `checkoutItems` to Bonuscard
   - Finalization is retried once on failure; on success the POS clears `order.bonuscard_transaction_id` and `order.bonuscard_checkout_items`
   - If there is a pending transaction but no checkout items to finalize (e.g. only products without barcode/article number), the POS cancels the pending transaction after payment instead of leaving the customer locked; cancel failure is logged and shown as a sticky warning
   - If finalization fails after payment, the POS attempts cancel as a fallback before showing a sticky warning
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

## Important state tracked in POS

- `order.bonuscard_partner_id`
- `order.bonuscard_transaction_id`
- `order.bonuscard_checkout_items`
- `order.bonuscard_needs_validation` — set when lines change; cleared after a successful validation

- `order._bonuscardCandidateTxId` — client-generated transaction identifier not yet confirmed by a successful validation; included in cancel paths so a sent-but-unconfirmed ID is not lost before Bonuscard confirms it

These fields ensure the POS finalizes or cancels the exact Bonuscard transaction that was validated before payment, and re-validates when the order content changes.
