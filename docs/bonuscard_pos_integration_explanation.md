# Bonuscard POS Integration

This document explains how the Bonuscard POS integration works in the `bonuscard_odoo` module.

## Diagram file
- `docs/bonuscard_pos_integration_diagram.mmd`

## Integration steps

1. Customer selected in POS
   - `bonuscard_odoo/static/src/app/bonuscard_pos.js` extends `PosStore.setPartnerToCurrentOrder`
   - Calls `res.partner.get_bonuscard_status_for_pos` to resolve Bonuscard status
   - The backend searches Bonuscard using customer phone, mobile, email, or name
   - The partner record is updated with `bonuscard_status` and `bonuscard_recruitment_code`

2. Payment starts in POS
   - `PosStore.pay()` checks if the partner has a `bonuscard_recruitment_code`
   - It builds `orderLines` from products with `barcode` or `default_code`
   - Calls `bonuscard.api.service.validate_purchase_for_pos`
   - Stores `order.bonuscard_transaction_id`, `order.bonuscard_checkout_items`, and `order.bonuscard_partner_id`
   - If discounts are returned, it asks the user to confirm before proceeding

3. Payment confirmation
   - `OrderPaymentValidation.afterOrderValidation()` calls `bonuscard.api.service.finalize_purchase_for_pos`
   - This sends the stored `transactionIdentifier` and `checkoutItems` to Bonuscard
   - On success, the POS clears the captured Bonuscard transaction state

4. Cancel or rollback flows
   - `PosStore.onClickBackButton()`, `deleteCurrentOrder()`, and `closePos()` cancel pending Bonuscard transactions
   - They call `bonuscard.api.service.cancel_purchase_for_pos`
   - This keeps the Bonuscard state consistent when the POS flow is abandoned

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

## Important state tracked in POS

- `order.bonuscard_partner_id`
- `order.bonuscard_transaction_id`
- `order.bonuscard_checkout_items`

These fields ensure the POS finalizes or cancels the exact Bonuscard transaction that was validated before payment.
