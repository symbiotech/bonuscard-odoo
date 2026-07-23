========================================
Bonuscard POS Order To Sale Order Bridge
========================================

Companion module for ``bonuscard_odoo`` and ``pos_order_to_sale_order``.

``pos_order_to_sale_order`` can create a ``sale.order`` without syncing a
``pos.order``. Bonuscard normally finalizes in ``PosStore.preSyncAllOrders``,
which never runs on those paths.

This module reuses Bonuscard's ``_applyBonuscardAuditAfterPayment``
(FinalizePurchase, or release/Cancel when there is nothing to finalize) after:

* **Customer Account on validate** — patches
  ``OrderPaymentValidation.finalizeSaleOrderFromPos`` after a *new* successful
  conversion.
* **Actions → Create Sale Order** — wraps the shared create helper so Finalize
  runs *before* ``removeOrder`` (one-shot button and popup). Otherwise a pending
  ValidatePurchase would be Cancelled on cart delete.

Neither path starts ValidatePurchase by itself; they only Finalize/release when
a pending transaction already exists on the cart.

Installation
============

* Depends on ``bonuscard_odoo`` and ``pos_order_to_sale_order``.
* ``auto_install`` is enabled: installs automatically when both parents are
  present.

When it activates
=================

* POS config has sale-order creation enabled (Customer Account on validate
  and/or Actions → Create Sale Order).
* Order has a Bonuscard partner / pending ValidatePurchase state as usual.

Cash, card, and mixed payments that sync a ``pos.order`` are unchanged (still
finalized via ``preSyncAllOrders``).

Out of scope
============

* Bonuscard audit fields on ``sale.order`` (v1 relies on the Bonuscard API
  finalize outcome; there is no synced ``pos.order`` for audit storage).
* Starting ValidatePurchase solely because Create Sale Order was pressed.
