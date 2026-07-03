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
* Security groups and ACLs for user and manager roles
* Customer lookup by phone, email, and name when a customer is selected in POS
* Partner status fields and sync controls on ``res.partner``
* POS badge for Bonuscard status on the partner-selection screen
* Smart button for one-click Bonuscard status checks from the partner form
* Manual customer registration when lookup returns ``not_found``
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
3. Optionally set the test URL to ``https://test.bonuscard.com/``.
4. Click **Test Connection**.

Usage
=====

Customer Lookup in POS
----------------------

When a cashier selects a customer in Point of Sale, the addon calls
``SearchCustomers`` using phone, email, and name. The result is written back to
the partner and shown as a badge in the partner list.

Customer Registration
---------------------

When lookup returns ``not_found``, the partner form exposes
**Register to Bonuscard**. The action re-checks first, registers by phone if
still missing, then stores the returned recruitment code.

Purchase Lifecycle
------------------

The POS integration supports:

* ``ValidatePurchase`` before payment and after order changes
* ``FinalizePurchase`` after successful payment
* ``CancelPurchase`` when the order is aborted

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
