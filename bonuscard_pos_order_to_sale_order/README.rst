========================================
Bonuscard POS Order To Sale Order Bridge
========================================

Companion module for ``bonuscard_odoo`` and ``pos_order_to_sale_order``.

When **Create Sale Order when paying with Customer Account** is enabled,
``pos_order_to_sale_order`` creates a ``sale.order`` and does not sync a
``pos.order``. Bonuscard normally finalizes in ``PosStore.preSyncAllOrders``,
which never runs on that path.

This module patches ``OrderPaymentValidation.finalizeSaleOrderFromPos`` so that
after a *new* successful conversion it calls Bonuscard's
``_applyBonuscardAuditAfterPayment`` (FinalizePurchase, or release/Cancel when
there is nothing to finalize).

Installation
============

* Depends on ``bonuscard_odoo`` and ``pos_order_to_sale_order``.
* ``auto_install`` is enabled: installs automatically when both parents are
  present.

When it activates
=================

* POS config has Customer Account → sale order on validate enabled.
* Cashier pays fully with Customer Account (``pay_later``).
* Order has a Bonuscard partner / pending ValidatePurchase state as usual.

Cash, card, and mixed payments are unchanged (still finalized via
``preSyncAllOrders``).

Out of scope
============

* The **Actions → Create Order** button (draft cart → sale order without
  payment). Pending Bonuscard transactions are still cancelled on order
  delete, as in ``bonuscard_odoo``.
* Bonuscard audit fields on ``sale.order`` (v1 relies on the Bonuscard API
  finalize outcome; there is no synced ``pos.order`` for audit storage).
