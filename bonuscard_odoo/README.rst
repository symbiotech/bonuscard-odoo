===================
Bonuscard Connector
===================

Bonuscard Connector adds a configurable connection layer between Odoo and the
Bonuscard API for POS-oriented loyalty and discount workflows.

Overview
========

This addon provides:

* Company-specific Bonuscard connections with Basic-auth credentials
* POS customer lookup and partner status synchronization
* Purchase lifecycle integration (validate, finalize, cancel)
* Reusable backend service methods for Bonuscard API calls

Features
========

* Connection model with API base URL, Basic-auth credentials, culture, timeout, and diagnostics
* Reusable service layer for Bonuscard HTTP requests and response error handling
* Test Connection server action from the form view
* Security groups (Bonuscard User, Bonuscard Manager) and ACLs; admin is assigned Manager by default
* Customer lookup by phone, email, and name when a customer is selected in POS
* Partner status fields and sync controls on ``res.partner``
* POS badge for Bonuscard status on the partner-selection screen
* Smart button for one-click Bonuscard status checks from the partner form
* Manual customer registration from the partner form or POS partner list when lookup returns ``not_found``
* Automatic discount application in POS after validation

Installation
============

1. Add this repository to your Odoo addons path.
2. Restart Odoo and update the module list.
3. Install **Bonuscard Connector** from Apps.

Configuration
=============

1. Go to **Bonuscard > Connections**.
2. Create a connection record with API URL, username, password, and culture.
3. Optionally set the test API base URL to ``https://test.bonuscard.com/api/``.
4. Click **Test Connection**.
5. In **Point of Sale > Configuration > Settings**, configure a **Discount Product**.
   Bonuscard discounts that cannot be applied as line percentages are added as
   separate discount lines using this product.

Usage
=====

Customer Lookup in POS
----------------------

When a cashier selects a customer in Point of Sale, the addon calls
``SearchCustomers`` using phone, email, and name — unless the partner already
has status ``linked`` or ``not_found`` (cached from a previous lookup). The
result is written back to the partner and shown as a badge in the partner list.
Use **Check Bonuscard** on the partner form to force a fresh lookup.

Customer Registration
---------------------

When lookup returns ``not_found``, registration is available from:

* The partner form: **Register to Bonuscard**
* The POS partner list: **Register with Bonuscard** in the partner row menu

Both paths call ``action_register_to_bonuscard``, which re-checks Bonuscard
first, registers by phone if still missing, then stores the returned recruitment
code. A phone number is required.

Partner Form Controls
---------------------

The Bonuscard tab on ``res.partner`` shows status, recruitment code, internal
ID, last sync time, and lookup notes. **Check Bonuscard** refreshes status;
**Reset Bonuscard Status** clears the link; **Register to Bonuscard** appears
when status is ``not_found``.

Purchase Lifecycle
------------------

The POS integration supports:

* ``ValidatePurchase`` before payment and after order changes
* ``FinalizePurchase`` after successful payment
* ``CancelPurchase`` when the order is aborted, the customer is changed, the
  order is deleted, or the POS session is closed

Cancel requests are retried once on ``onDeleteOrder`` and ``closePos``. Local
transaction fields are cleared only after Bonuscard confirms cancellation.
If cancel still fails:

* Changing the customer is blocked while a transaction is pending.
* Deleting the order is blocked so the cashier can retry cancellation.
* Closing the POS shows a warning and may leave the Bonuscard lock active
  until it expires on the Bonuscard side.

Only order lines with a barcode or article number and a positive unit price are
sent to Bonuscard. Returned discounts are applied as line percentages or as
separate discount lines (requires the POS discount product above).

Manual Integration Tests
========================

Manual integration tests exist in ``tests/test_bonuscard_integration.py`` and
are designed for local testing only.

Use runtime or local secret configuration. Never commit real credentials.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/symbiotech/bonuscard-odoo/issues>`_.

Credits
=======

Authors
-------

* symbiotech
