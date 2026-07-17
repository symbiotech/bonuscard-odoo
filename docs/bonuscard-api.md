# Bonuscard REST API – Full Documentation

Source: <https://web.bonuscard.com/api/documentation>
Captured: 2026-03-12

## Overview

- REST API with JSON, secured with SSL + Basic Authentication
- Account must be activated by a Bonuscard admin before use
- Header `BC-Culture` controls response language (default `en-GB`)
- In this Odoo addon, `BC-Culture` follows the current user's language when it
  maps to a supported culture; otherwise the connection **API Culture** is used
- Test environment base URL: `https://test.bonuscard.com/`

### Supported languages (`BC-Culture` header)

| Code | Language |
|------|----------|
| `en-GB` | English (Default) |
| `sv-SE` | Swedish |
| `fi-FI` | Finnish |
| `nb-NO` | Norwegian |
| `da-DK` | Danish |

---

## Error Handling

All API errors return HTTP 200 with `"error": true`, an `"errorCode"`, and a `"messages"` array.
Entries are usually strings; some endpoints may return UI-oriented objects with a ``message``
field (and optional styling keys). The Odoo addon always normalizes these to plain strings
before cashier-facing display.

| Code | Meaning |
|------|---------|
| 1 | Invalid request – customer not found or checkout items missing prices |
| 2 | Customer locked to another transaction (wrong or missing `transactionIdentifier`) |
| 3 | Calculation timeout |
| 4 | Customer not eligible – needs to verify account before next purchase |
| 5 | Discount code is not for pre-registering; supply it with the purchase instead |

```json
{
  "error": true,
  "errorCode": 1,
  "messages": ["Hittar ingen kund som matchar sökningen."]
}
```

---

## Requests

### 1. ValidatePurchase

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/ValidatePurchase` |
| **Method** | POST |
| **Content-Type** | application/json |

Can be called any number of times. Returns available discounts based on the `checkoutItems` supplied.
Use the same `transactionIdentifier` across all calls; the server generates it on the first call if omitted.

#### Request Body

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `customerIdentifier` | Barcode from app, recruitment code, email, SSN, or phone |
| required on 2nd+ calls | string | `transactionIdentifier` | GUID without dashes preferred; server generates on first call if omitted |
| required | array of [CheckoutItem](#checkoutitem) | `checkoutItems` | Products being purchased |
| not required | array of string | `codes` | Campaign/coupon codes to apply |

```json
{
  "customerIdentifier": "WLKT6",
  "transactionIdentifier": "ef835fc21aa64b41b1e86f47cdaedd8b",
  "checkoutItems": [
    { "ean": "8710255122465", "quantity": 2, "pricePerItem": 299 }
  ],
  "codes": ["SOMMAR2019"]
}
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| boolean | `error` | `false` on success |
| array of string | `messages` | Transaction messages or error messages |
| string | `customerIdentifier` | Identifier used |
| [Customer](#customer) | `customer` | Customer info |
| string | `transactionIdentifier` | Transaction ID (preserve for Finalize/Cancel) |
| array of [CheckoutItem](#checkoutitem) | `checkoutItems` | Products included in transaction |
| array of [CheckoutItem](#checkoutitem) | `resultItems` | Discounts resulting from transaction |
| decimal | `totalDiscount` | Total discount amount |

```json
{
  "error": false,
  "messages": ["Ett köp har genererat en rabatt av typen \"Eukanuba hundmat uppfödarrabatt\""],
  "customerIdentifier": "WLKT6",
  "customer": {
    "id": 1,
    "name": "Test Testsson",
    "phoneNumber": "+46707654321",
    "email": "test.testsson@example.com",
    "address": "Testgatan 1",
    "city": "Staden",
    "recruitmentCode": "WLKT6"
  },
  "transactionIdentifier": "ef835fc21aa64b41b1e86f47cdaedd8b",
  "checkoutItems": [
    {
      "identifier": "9",
      "ean": "8710255122465",
      "articleNumber": "1213",
      "description": "eukanuba hund puppy large 3 kg",
      "quantity": 2,
      "pricePerItem": 299
    }
  ],
  "resultItems": [
    {
      "identifier": "11",
      "ean": "7350040121764",
      "description": "Eukanuba hundmat uppfödarrabatt",
      "quantity": 1,
      "pricePerItem": -74.75,
      "addedStamps": 1,
      "numberOfStamps": 1,
      "maxNumberOfStamps": 1,
      "relatedIdentifiers": ["9"]
    }
  ],
  "totalDiscount": 149.5
}
```

---

### 2. FinalizePurchase

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/FinalizePurchase` |
| **Method** | POST |
| **Content-Type** | application/json |

Call **after payment is completed** to actually create the discounts.
The body must be identical to the last `ValidatePurchase` call.

#### Request Body

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `customerIdentifier` | Same as ValidatePurchase |
| required | string | `transactionIdentifier` | Same as ValidatePurchase |
| not required | string | `note` | Free-text note (e.g., cashier name) |
| required | array of [CheckoutItem](#checkoutitem) | `checkoutItems` | Same products as ValidatePurchase |
| not required | array of string | `codes` | Same codes as ValidatePurchase |

```json
{
  "customerIdentifier": "WLKT6",
  "transactionIdentifier": "ef835fc21aa64b41b1e86f47cdaedd8b",
  "note": "Cashier: Anna",
  "checkoutItems": [
    { "ean": "8710255122465", "quantity": 2, "pricePerItem": 299 }
  ],
  "codes": ["SOMMAR2019"]
}
```

#### Response Body

Same structure as `ValidatePurchase` response:
`error`, `messages`, `customerIdentifier`, `customer`, `transactionIdentifier`, `checkoutItems`, `resultItems`.

---

### 3. CancelPurchase

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/CancelPurchase` |
| **Method** | POST |
| **Content-Type** | application/json |

Call if the purchase is **aborted**. Unlocks the customer for other transactions.

#### Request Body

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `transactionIdentifier` | Transaction to cancel |

```json
{
  "transactionIdentifier": "ef835fc21aa64b41b1e86f47cdaedd8b"
}
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| boolean | `error` | `false` on success |
| array of string | `messages` | Messages |

```json
{
  "error": false,
  "messages": ["Transaktionen är avbruten och kunden tillgänglig för andra köp."]
}
```

---

### 4. SearchCustomers

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/SearchCustomers` |
| **Method** | GET |
| **Parameters** | Query string |

Find existing customers. Accepts partial matches; multiple tokens separated by spaces.

#### Query Parameters

| Required | Type | Parameter | Description |
|----------|------|-----------|-------------|
| required | string | `query` | Recruitment code, phone, email, or name (partial, space-separated tokens) |

```
GET https://web.bonuscard.com/Api/SearchCustomers?query=0707654321
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| array of [Customer](#customer) | `customers` | Matching customers |
| boolean | `error` | `false` on success |
| array of string | `messages` | Error messages |

```json
{
  "customers": [
    {
      "id": 1,
      "name": "Test Testsson",
      "phoneNumber": "+46707654321",
      "email": "test.testsson@example.com",
      "address": "Testgatan 1",
      "city": "Staden",
      "recruitmentCode": "WLKT6"
    }
  ],
  "error": false
}
```

---

### 5. RegisterCustomer

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/RegisterCustomer` |
| **Method** | POST |
| **Parameters** | Query string |

Registers a new customer by phone number.

#### Query Parameters

| Required | Type | Parameter | Description |
|----------|------|-----------|-------------|
| required | string | `phoneNumber` | Unique cell phone number |

```
POST https://web.bonuscard.com/Api/RegisterCustomer?phoneNumber=0707654321
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| [Customer](#customer) | `customer` | Newly created customer |
| boolean | `error` | `false` on success |
| array of string | `messages` | Messages |

```json
{
  "customer": {
    "id": 1,
    "phoneNumber": "+46707654321",
    "recruitmentCode": "WLKT6"
  },
  "error": false,
  "messages": ["Kunden har skapats"]
}
```

---

### 6. ActivateDiscountCode

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/ActivateDiscountCode` |
| **Method** | POST |
| **Content-Type** | application/json |

Pre-registers a discount code on a customer (before/outside of a purchase).
Note: error code 5 is returned if the code must be supplied as part of a purchase instead.

#### Request Body

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `customerIdentifier` | Barcode, recruitment code, email, SSN, or phone |
| required | string | `code` | Discount code to register |

```json
{
  "customerIdentifier": "WLKT6",
  "code": "SOMMAR2019"
}
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| boolean | `error` | `false` on success |
| array of string | `messages` | Messages |

```json
{
  "error": false,
  "messages": ["Rabattkod aktiverad!"]
}
```

---

### 7. GetAvailableSalesReportsForYear

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/GetAvailableSalesReportsForYear` |
| **Method** | GET |
| **Parameters** | Query string |

Returns a list of available sales reports for the specified year.

#### Query Parameters

| Required | Type | Parameter | Description |
|----------|------|-----------|-------------|
| required | integer | `year` | Year to query |

```
GET https://web.bonuscard.com/Api/GetAvailableSalesReportsForYear?year=2024
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| boolean | `error` | `false` on success |
| array of string | `messages` | Error messages |
| array of [SalesReportHeader](#salesreportheader) | `salesreports` | Available reports (use `id` in GetSalesReport) |

```json
{
  "error": false,
  "salesreports": [
    { "id": 1, "reportedAt": "2024-01-01T12:00:00.000", "createdBy": "Automatic" }
  ]
}
```

---

### 8. GetSalesReport

| | |
|-|-|
| **URL** | `https://web.bonuscard.com/Api/GetSalesReport` |
| **Method** | GET |
| **Parameters** | Query string |

Returns full details for a specific sales report.

#### Query Parameters

| Required | Type | Parameter | Description |
|----------|------|-----------|-------------|
| required | integer | `id` | Sales report ID (from GetAvailableSalesReportsForYear) |

```
GET https://web.bonuscard.com/Api/GetSalesReport?id=1
```

#### Response Body

| Type | Field | Description |
|------|-------|-------------|
| boolean | `error` | `false` on success |
| array of string | `messages` | Error messages |
| [SalesReport](#salesreport) | `salesreport` | Full report |

```json
{
  "error": false,
  "salesreport": {
    "id": 1,
    "reportedAt": "2024-01-01T12:00:00.000",
    "createdBy": "Automatic",
    "stores": [
      {
        "storeId": 1,
        "name": "Teststore",
        "storeCustomerNumber": "128056",
        "storeAddress": "Mainstreet 2, 123 45 Metropolis",
        "storeChain": {
          "storeChainName": "The store chain of awesomeness",
          "storeChainNumber": "356",
          "data": { "name": "Cost center", "value": "2601" }
        },
        "reportRows": [
          {
            "coupontypeName": "Discount for tasty snacks - 10 %",
            "couponExternalIdentifier": "1234",
            "productArticleNumber": "123456",
            "productDescription": "Tasty Snacks with peanuts",
            "productCustomReportText": null,
            "numberOfPurchases": 50,
            "salesPrice": 29.00,
            "costPrice": 8.0,
            "customerCreditAmount": 145.0,
            "storeCreditAmount": 40.0
          }
        ],
        "totalSales": 5033.00,
        "totalCustomerCreditAmount": 727.55,
        "totalStoreCreditAmount": 300.1
      }
    ]
  }
}
```

---

## Data Types

### CheckoutItem

Used for both purchase items in requests and discount results in responses.

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `ean` | EAN barcode – uniquely identifies the product |
| required | integer | `quantity` | Quantity |
| required | decimal | `pricePerItem` | Sales price per unit |
| not required | integer | `category` | Product category (see table below) |
| not required | string | `identifier` | Unique line item ID (mostly response-only) |
| not required | string | `articleNumber` | Article number (mostly response-only) |
| not required | string | `description` | Product description (mostly response-only) |
| not required | integer | `addedStamps` | Stamps added by this discount (discount response only) |
| not required | integer | `numberOfStamps` | Current stamp count after transaction (discount response only) |
| not required | integer | `maxNumberOfStamps` | Max stamps on card (discount response only) |
| not required | array of string | `relatedIdentifiers` | Identifiers of products triggering this discount |
| not required | string | `dataColumn1Value` | Extra coupon data (rarely used) |
| not required | string | `dataColumn2Value` | Extra coupon data (rarely used) |
| not required | string | `dataColumn3Value` | Extra coupon data (rarely used) |

**Product categories:**

| ID | Name | ID | Name |
|----|------|----|------|
| 1 | Cats | 2 | Small Animals |
| 3 | Pet Accessories | 4 | Dogs |
| 5 | Aquaristics | 6 | Reptile |
| 7 | Birds | 8 | Electronics |
| 9 | Pet Trimming | 10 | Clothing |
| 11 | Horse Equestrian | 12 | Pets |
| 13 | Fashion & Clothing | 14 | Fishing |
| 15 | Food | 16 | Skincare |
| 17 | Hunting | 18 | Sports & Leisure |
| 19 | Beauty & Health | 20 | Hunting & Fishing |
| 21 | Fun & Entertainment | 22 | Home & Garden |
| 23 | Conditioner | 24 | Cars & Vehicles |
| 25 | Restaurant & Cafe | 26 | Travelling |
| 27 | Gambling & Betting | 28 | Kids |
| 29 | Schampoo | 30 | Health |
| 31 | Services & Subscriptions | 32 | Finance & Insurance |
| 33 | Sport | 38 | Professional |
| 39 | Youth | 41 | CatSand |
| 42 | Other | | |

---

### Customer

Returned by `SearchCustomers`, `ValidatePurchase`, and `FinalizePurchase`.

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | integer | `id` | Internal numeric ID – do NOT use in API requests |
| not required | string | `name` | Full name |
| not required | string | `phoneNumber` | Phone number |
| not required | string | `email` | Email address |
| not required | string | `address` | Postal address |
| not required | string | `city` | City |
| required | string | `recruitmentCode` | Preferred identifier for use in API requests |

---

### SalesReportHeader

Returned in `GetAvailableSalesReportsForYear`.

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | integer | `id` | Report ID – use in `GetSalesReport` |
| required | datetime | `reportedAt` | When report was created |
| required | string | `createdBy` | Creator name or `"Automatic"` |

---

### SalesReport

Returned in `GetSalesReport`.

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | integer | `id` | Report ID |
| required | datetime | `reportedAt` | Creation time |
| required | string | `createdBy` | Creator |
| required | array of [SalesReportStore](#salesreportstore) | `stores` | Per-store data |

---

### SalesReportStore

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | integer | `storeId` | Store ID |
| required | string | `name` | Store name |
| not required | string | `storeCustomerNumber` | Partner-specific customer number |
| not required | string | `storeAddress` | Store address |
| not required | [SalesReportStoreChain](#salesreportstorechain) | `storeChain` | Chain data |
| required | array of [SalesReportRow](#salesreportrow) | `reportRows` | Report rows |
| implied | decimal | `totalSales` | Total sales |
| implied | decimal | `totalCustomerCreditAmount` | Total customer credit |
| implied | decimal | `totalStoreCreditAmount` | Total store reimbursement |

---

### SalesReportStoreChain

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `storeChainName` | Chain name |
| not required | string | `storeChainNumber` | Partner-specific number |
| not required | object | `data` | Additional `{ name, value }` partner data |

---

### SalesReportRow

| Required | Type | Field | Description |
|----------|------|-------|-------------|
| required | string | `coupontypeName` | Coupon/discount name |
| not required | string | `couponExternalIdentifier` | External coupon ID |
| required | string | `productArticleNumber` | Article number |
| required | string | `productDescription` | Product description |
| not required | string | `productCustomReportText` | Custom report text |
| required | integer | `numberOfPurchases` | Number of items purchased |
| required | decimal | `salesPrice` | Single-unit sales price |
| not required | decimal | `costPrice` | Single-unit cost price |
| required | decimal | `customerCreditAmount` | Total credit given to customers |
| not required | decimal | `storeCreditAmount` | Total store reimbursement |
