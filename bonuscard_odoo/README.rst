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
* Bonuscard audit fields stored on POS orders (validated/finalized/skipped/failed), even when discount is 0
* Product catalog status on ``product.product`` to control which lines are sent to Bonuscard
* Bulk list actions to mark products as in or not in the Bonuscard catalog
* Scheduled + manual bulk prefetch of Bonuscard customer links (phone → email → optional name fallback) to reduce POS lookup requests

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
4. Click **Test Connection** (calls ``SearchCustomers`` with a probe query to verify URL and credentials).
5. In **Point of Sale > Configuration > Settings**, configure a **Discount Product**.
   Bonuscard discounts that cannot be applied as line percentages are added as
   separate discount lines using this product.
6. (Optional) Configure the bulk prefetch on the connection record:

   - **Bonuscard > Connections** → open a connection → **Bulk Prefetch**
   - Enable/disable the job
   - TTL (hours) to avoid re-querying recently synced partners
   - Batch size per run
   - Optional name fallback (only used when phone and email are missing)
7. Mark Bonuscard catalog products:

   **When Product Variants are disabled** (default for many POS setups), use
   **Inventory > Products**:

   - Select products in the list and run **Mark as Bonuscard Catalog** /
     **Mark as Not in Bonuscard Catalog**
   - Optional columns: enable **Bonuscard Catalog** and **Bonuscard Catalog
     Updated** from the list column picker

   **When Product Variants are enabled**, use **Inventory > Products > Product
   Variants**:

   - Open a variant form and set **Bonuscard Catalog** to ``In Bonuscard Catalog``
   - Or use the same list actions on the Product Variants list

   **From product forms** (backend or POS **Edit Product** modal), Bonuscard
   users can set **Bonuscard Catalog** directly on the form when the product has
   exactly one variant (including on the main product form even when Product
   Variants are enabled).

   In both cases you can also import from CSV with columns ``barcode`` (or
   ``default_code``) and ``bonuscard_catalog_status``

8. Configure catalog probe (optional, managers only):

   **Bonuscard > Connections** → open the current connection:

   - Set **Catalog Probe Customer** to your dedicated Bonuscard test customer
     identifier (recruitment code, phone, email, etc.)
   - Adjust **Catalog Probe Price** (default ``100``) and **Catalog Probe Batch Size**
   - Enable/disable the daily catalog probe cron

   Probe never-scanned products manually:

   - **Inventory > Products** or **Product Variants**: select products and run
     **Check Bonuscard Catalog**
   - Or use **Check Bonuscard Catalog** on a product form

   The scheduled job probes products with catalog status **Not Set** that have a
   barcode or article number. Each product is checked individually via
   ``ValidatePurchase``. A product is **in catalog** only when Bonuscard returns
   the probed EAN on an enriched ``checkoutItems`` line (catalog metadata such as
   ``identifier`` or ``description``). Unknown products are detected when that
   enrichment is missing, when only an unlock/anchor EAN is recognized, or when
   Bonuscard returns no ``transactionIdentifier``. Recognized products trigger
   ``CancelPurchase`` so the probe customer is not left locked.

Usage
=====

Product Catalog in POS
----------------------

Only product variants marked **In Bonuscard Catalog** are included in
``ValidatePurchase``. Other lines are sold normally and ignored by Bonuscard.
Products without a barcode or article number (internal reference /
``default_code``) cannot be marked as in the catalog. The POS product info
popup (long-press a product tile) shows the current Bonuscard catalog status
for single-variant products.

Customer Lookup in POS
----------------------

When a cashier selects a customer in Point of Sale, the addon calls
``SearchCustomers`` using phone, email, and name — unless the partner already
has status ``linked`` or ``not_found`` (cached from a previous lookup). Exact
matches prefer phone and email; name is used only when neither side has phone
or email details. The result is written back to the partner and shown as a
badge in the partner list.
Use **Check Bonuscard** on the partner form to force a fresh lookup.

Bulk Prefetch (Reduce POS Lookups)
---------------------------------

Bonuscard customer linking can be prefetched in the background so that most POS
partner selections already have a cached ``bonuscard_status`` of ``linked`` or
``not_found``.

- Scheduled job: runs daily by default and only processes partners **never scanned before** (see the module cron entry).
- Manual run: **Bonuscard > Connections** → open a connection → **Run Bulk Prefetch** (same scope as the cron).
- Manual refresh: **Bonuscard > Connections** → open a connection → **Refresh Bulk Prefetch** (re-checks already-scanned partners older than TTL).

Term order is phone → email → (optional) name. Name fallback is constrained to
cases where both the partner and the Bonuscard customer have no phone/email.

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
* ``FinalizePurchase`` after successful payment (retried once on failure)
* ``CancelPurchase`` when the order is aborted, the customer is changed, the
  order is deleted, or the POS session is closed

``FinalizePurchase`` is retried once after payment. Local transaction fields are
cleared only after Bonuscard confirms finalization. If finalization still fails,
payment remains complete but a sticky warning is shown and the transaction
fields are kept so the loyalty lock can be recovered manually.

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

POS Order Reporting
-------------------

After payment, Bonuscard audit fields are stored on the synced ``pos.order``
record (state, transaction identifier, validated/finalized timestamps, and last
error message). Open **Point of Sale > Orders** to review them; use the Bonuscard
search filters to list finalized, validated, skipped, failed, or not-applicable
orders.

Manual Integration Tests
========================

Manual integration tests exist in ``tests/test_bonuscard_integration.py`` and
are designed for local testing only.

Configure ``BONUSCARD_TEST_*`` values in a local ``.env`` file (see
``.env.example``). The non-Bonuscard customer-lock test requires
``BONUSCARD_TEST_CONSUMER`` and ``BONUSCARD_TEST_BONUSCARD_EAN`` (a product on
the Bonuscard API). Optionally set ``BONUSCARD_TEST_NON_BONUSCARD_EAN`` to also
exercise a barcoded product that the Bonuscard API rejects. Catalog probe tests
use the same ``BONUSCARD_TEST_CONSUMER`` as the POS lock test; tests run in a
fixed order and release the customer lock in ``tearDown`` so they do not
interfere with each other. ``test_92_catalog_probe_classifies_known_and_unknown_eans``
asserts that a known Bonuscard EAN is marked **in_catalog** and an unknown EAN
is marked **not_in_catalog** against the live API.

Run only the manual integration suite with::

  --test-tags bonuscard_integration

Use runtime or local secret configuration. Never commit real credentials.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/symbiotech/bonuscard-odoo/issues>`_.

Credits
=======

Authors
-------

* symbiotech
