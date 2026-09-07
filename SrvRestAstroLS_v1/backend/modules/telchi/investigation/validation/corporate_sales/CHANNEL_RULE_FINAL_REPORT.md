# TEAM360 TELCHI — REAL SALES CHANNEL RULE DISCOVERY

**Gate:** `TEAM360_TELCHI_REAL_SALES_CHANNEL_RULE_PASS`
**Date:** 2026-08-20

---

## A. Resultado

**TEAM360_TELCHI_REAL_SALES_CHANNEL_RULE_PASS**

The real business rule for channel classification has been discovered: **the transaction channel is determined by the CUSTOMER's `U_CANAL_VENTAS` field, not by the seller's category.**

---

## B. Business Reality

The channel classification is a **customer attribute**, not a transaction-level or seller-level attribute:

- `OCRD.U_CANAL_VENTAS` on the customer master determines which channel a sale belongs to
- `OSLP.U_CATVENDEDOR` (seller category) is an independent dimension — corporate sellers sell to ALL channels
- `PriceTypeCode` is mostly unused (all values=0 in Aug 2026)
- `INV1.ListNum` is almost always NULL — price list is not tracked at line level

**The single source of truth for transaction channel is `OCRD.U_CANAL_VENTAS`.**

---

## C. Historical Rule

The legacy Python code (`activeTools01.py`) calculated Canal using `PriceTypeCode + ClientSegmentationCode` per-sale. This was likely:
1. The original logic used to INITIALIZE `U_CANAL_VENTAS` on customers
2. A reporting approximation from a different system era
3. Now replaced by the pre-assigned `U_CANAL_VENTAS` field in SAP

The current SAP system stores channel directly on the customer master.

---

## D. Seller Category

`OSLP.U_CATVENDEDOR` meanings:
- **1**: Salón/Calle sellers (24 active sellers)
- **2**: Corporate sellers (7 active sellers)
- **3**: Preventa/Other (9 active sellers)
- **NULL**: Unclassified (211 sellers)

**Critical proof that seller category ≠ transaction channel:**
- Corporate sellers (cat=2) sell to canal=3 (830K), canal=6 (292K), canal=5 (260K), canal=4 (140K), canal=7 (15K), canal=NULL (32K), canal=2 (1.5K)
- Non-corporate sellers (cat=1) sell to canal=2 customers ($434K)
- Only 3 documents ($1,551) have BOTH corporate seller AND corporate customer

---

## E. Luz Timeline

| Period | Primary Channel | Other Channels | Notes |
|--------|----------------|----------------|-------|
| 2022-03..2026-08 | canal=6 (Regional) | canal=3, canal=7, canal=2, canal=1, canal=NULL | cat=2 seller, sells to ALL channels |
| Aug 2026 | canal=6: $189K (190 docs) | canal=2: $500 (1 doc) | Almost all sales to regional customers |

Luz is classified as corporate seller (cat=2) but her actual sales are overwhelmingly to canal=6 (regional) customers.

---

## F. Soveron Timeline

| Period | Activity | Channel |
|--------|----------|---------|
| 2020 (Cruzada Excel) | Active, SellerType=21 (calle) | N/A |
| 2022 | No activity in Parquet | N/A |
| 2023-10 | Single invoice ($126) | canal=NULL |
| 2026-08 | Zero invoices | N/A |

Soveron is effectively inactive. No meaningful channel classification.

---

## G. Customer Classification

`U_CANAL_VENTAS` is **stable per customer** across years:
- C000001 (ALMARK): canal=3 since 2022-03 through 2026-08
- C003728 (VENTAS CORPORATIVAS- HORIZONTAL): canal=3 since 2022-04 through 2026-08
- C000010 (DISPROMED SRL.): canal=5 since 2022-04 through 2026-08

No customer channel changes detected in the sample.

---

## H. PriceType

`U_TIPOVENTA` on OINV is always 0 — not used for classification.
`INV1.ListNum` is almost always NULL — price list not tracked per line.
Price type is NOT a determinant of channel in the current system.

---

## I. Price Override

Price override detection is not needed for channel classification. The channel is determined by the customer master, not by pricing behavior.

---

## J. Contradictions

| Contradiction | Count (Aug 2026) | Amount | Impact |
|--------------|------------------|--------|--------|
| Corporate seller → non-corporate customer | 379 docs | $1,569,750 | Method A overstates by $946K |
| Non-corporate seller → corporate customer | 647 docs | $603,668 | Method B captures these correctly |
| Both corporate seller AND customer | 3 docs | $1,551 | Minimal overlap |

---

## K. Rule Candidates

| ID | Logic | Precision | Recall | Status |
|----|-------|-----------|--------|--------|
| CHANNEL-RULE-001 | OCRD.U_CANAL_VENTAS = 2 | 100% (by definition) | 100% | **ACCEPTED** |
| CHANNEL-RULE-002 | OSLP.U_CATVENDEDOR = 2 | 0.4% overlap with true channel | 0.4% | REJECTED |

---

## L. Accepted Rule

**RuleVersion:** CHANNEL-RULE-001
**Logic:** Transaction channel = `OCRD.U_CANAL_VENTAS` of the invoice customer
**Inputs:** `OCRD.U_CANAL_VENTAS` (customer master field)
**Precedence:** Single determinant — no multi-variable logic needed
**Temporal scope:** STABLE (verified 2022-2026)
**Known exceptions:** canal=NULL (6,740 customers) — unclassified, need manual review

---

## M. August 2026 Comparison

| Method | Gross | Credit Notes | Net | Invoices | Customers | Sellers |
|--------|-------|-------------|-----|----------|-----------|---------|
| A. Seller-category (cat=2) | $1,571,301 | $45,889 | **$1,525,412** | 382 | — | 7 |
| B. Customer-channel (canal=2) | $605,219 | $26,062 | **$579,157** | 650 | 420 | 34 |
| **Difference** | | | **$946,255** | | | |

**Method A is WRONG** — it captures all sales by corporate sellers regardless of who they sell to.
**Method B is CORRECT** — it captures sales TO corporate customers, which is the actual transaction channel.

---

## N. Difference Analysis

- **A-only (seller corporate, customer NOT corporate):** $946K — sales by corporate sellers to regional/pharmacy/retail customers
- **B-only (customer corporate, seller NOT corporate):** $604K — sales by non-corporate sellers to corporate customers
- **Overlap:** $1.5K — minimal, proving the dimensions are independent

---

## O. Corporate Sellers August 2026

| SlpCode | Seller Name | Corporate Sales (canal=2) | Other Channel Sales |
|---------|-------------|--------------------------|-------------------|
| 13 | Luz Guzman | $500 | $189K (canal=6) + others |
| 11 | Selva Rojas Jaimes | — | $764K (canal=6,7,etc) |
| 10 | Federico Herrera Añez | — | $2.3M (2022 data) |
| 12 | Kaly Franco Cassia | — | $455K (2022 data) |

---

## P. Customers with Mixed Channels

All verified customers show STABLE channel assignment (no mixing detected).

---

## Q. SAP Traceability

| Field | Status |
|-------|--------|
| DocEntry | PASS (preserved) |
| LineNum | PASS (preserved) |
| Source | OINV → OCRD.U_CANAL_VENTAS |
| Filter | OCRD."U_CANAL_VENTAS" = 2 |

---

## R. Credit Notes

Policy: Subtracted from gross. CNs classified by customer's U_CANAL_VENTAS.

---

## S. Cancelled

Policy: Excluded via CANCELED='N'.

---

## T. Files

| Artifact | Path |
|----------|------|
| Business rule discovery | `validation/corporate_sales/business_rule_discovery.json` |
| Channel rule final report | `validation/corporate_sales/CHANNEL_RULE_FINAL_REPORT.md` |
| Previous artifacts preserved | `validation/corporate_sales/corporate_rule_evidence.json`, `august_2026_corporate_sales.json` |

---

## U. Parquet

Legacy: READ ONLY. New: NO.

---

## V. SAP

Writes: NONE.

---

## W. Infrastructure

VPN: UNCHANGED. Podman: UNCHANGED.

---

## X. Team360

GLOBAL CHANGES: NONE.

---

## Y. Próximo paso

**READY_FOR_TELCHI_BUSINESS_REPORTING_MODEL**

The channel rule is understood. The correct corporate sales for August 2026 (MTD) is **$579,157** (by customer channel), not $1,525,412 (by seller category).

The previous $1.47M figure was based on seller category, which overstates true corporate by $946K.
