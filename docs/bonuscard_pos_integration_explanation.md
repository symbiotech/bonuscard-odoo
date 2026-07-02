# Bonuscard POS Integration

This document explains how the Bonuscard POS integration works in the `bonuscard_odoo` module.

## Diagram file
- `docs/bonuscard_pos_integration_diagram.mmd`

## Integration steps

1. Customer selected in POS
   - `bonuscard_odoo/static/src/app/bonuscard_pos.js` extends `PosStore.setPartnerToCurrentOrder`
   - Calls `res.partner.get_bonuscard_status_for_pos` to resolve Bonuscard status
   - The backend searches Bonuscard using customer phone, email, or name
   - The partner record is updated with `bonuscard_status` and `bonuscard_recruitment_code`

2. Manual partner registration
   - If the lookup returns `not_found`, the partner form shows a `Register to Bonuscard` button
   - `res.partner.action_register_to_bonuscard` re-checks the partner against Bonuscard before registering
   - If still not found, it calls `RegisterCustomer`, writes the returned `recruitmentCode`, and links the partner
   - Error handling: Client-side service extracts detailed error messages from backend exceptions to show meaningful notifications to the cashier (e.g., "Partner must have a phone number to register with Bonuscard." instead of a generic "Odoo Server Error")

3. Continuous purchase validation
   - `_validateBonuscardPurchaseForOrder` is called in multiple situations:
     - Immediately after partner selection, if `bonuscard_status` resolves to `linked`
     - When a product line is added via `addLineToOrder` and the partner has a `bonuscard_recruitment_code`
     - When a line quantity or price is edited via `OrderSummary._setValue` / `updateQuantityNumber`
     - As a final guard in `PosStore.pay()` if the order has not been validated yet or needs re-validation
   - Each call builds `orderLines` from products that have `barcode` or `default_code`
   - Calls `bonuscard.api.service.validate_purchase_for_pos`
   - Stores `order.bonuscard_transaction_id`, `order.bonuscard_checkout_items`, and `order.bonuscard_partner_id`
   - If discounts are returned (`totalDiscount > 0`), they are applied automatically to the order via `_applyBonuscardDiscountsToOrder` — as percentage discounts on matched order lines or as separate discount lines using the POS discount product
   - Concurrent calls are guarded by a version counter; stale results are discarded
   - Previous discounts are cleared (`_clearAppliedBonuscardDiscounts`) before each new validation

4. Payment confirmation
   - `OrderPaymentValidation.afterOrderValidation()` calls `bonuscard.api.service.finalize_purchase_for_pos`
   - This sends the stored `transactionIdentifier` and `checkoutItems` to Bonuscard
   - On success, the POS clears `order.bonuscard_transaction_id` and `order.bonuscard_checkout_items`

5. Cancel or rollback flows
   - `PosStore.onClickBackButton()` (only when on the Payment Screen), `onDeleteOrder()`, and `closePos()` cancel pending Bonuscard transactions
   - `setPartnerToCurrentOrder` also cancels an open transaction when the partner is changed mid-order
   - All cancel paths call `bonuscard.api.service.cancel_purchase_for_pos`
   - Cancellation is best-effort: network failures are caught and logged; the POS flow continues regardless
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
    - `bonuscard_status`
    - `bonuscard_last_lookup_note`
  - Implements search/match logic and status synchronization
  - Adds `action_register_to_bonuscard` for manual registration when the customer is not found

## Important state tracked in POS

- `order.bonuscard_partner_id`
- `order.bonuscard_transaction_id`
- `order.bonuscard_checkout_items`

These fields ensure the POS finalizes or cancels the exact Bonuscard transaction that was validated before payment.
