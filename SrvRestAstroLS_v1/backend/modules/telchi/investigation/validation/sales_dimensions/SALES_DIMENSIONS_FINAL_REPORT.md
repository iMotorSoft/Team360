# TEAM360 TELCHI — SALES DIMENSIONS + TEMPORAL CHANNEL MODEL

**Gate:** `TEAM360_TELCHI_TEMPORAL_SALES_DIMENSIONS_PASS`
**Date:** 2026-08-20

---

## A. Resultado

**TEAM360_TELCHI_TEMPORAL_SALES_DIMENSIONS_PASS**

Two independent sales dimensions are now formally separated: **Seller** and **Customer Channel**. Financial regression passes. Seller-channel independence is proven (68/72 sellers sell to multiple channels).

---

## B. Sales Dimensions

| Dimension | Source Field | Identity | Independence |
|-----------|-------------|----------|-------------|
| **Seller** | OSLP.SlpCode | SlpCode (stable) | Independent — seller sells to ALL channels |
| **Customer Channel** | OCRD.U_CANAL_VENTAS | CardCode (customer) | Independent — same customer has ONE channel |
| Seller Category | OSLP.U_CATVENDEDOR | SlpCode | Separate from channel — NOT a channel |
| Customer | OCRD.CardCode | CardCode | — |

---

## C. Seller Rule

**"¿Cuánto vendió Luz?"** is answered by:

```
SALE → SlpCode=13 → NET SALES
```

Fields used: `OINV.SlpCode`, `OINV.DocTotal`, `ORIN.DocTotal`
Fields NOT used: `U_CANAL_VENTAS`, `U_CATVENDEDOR`

**August 2026 — Luz (SlpCode=13):**

| Metric | Value |
|--------|-------|
| Gross sales | $222,457 |
| Credit notes | $4,595 |
| **Net sales** | **$217,863** |
| Channels sold to | canal=6 ($190K), canal=NULL ($20K), canal=7 ($13K), canal=2 ($500) |

---

## D. Customer Channel Current

| Field | Value |
|-------|-------|
| Source | `OCRD.U_CANAL_VENTAS` |
| Meaning | Customer classification (NOT seller, NOT transaction) |
| Effective from | 2026-01 (bulk initialization) |
| Pre-2026 | NOT AVAILABLE — field didn't exist |
| Confidence | HIGH (for 2026+) |
| Stability | Verified — 20/20 active customers show stable channel |

---

## E. Customer Changes

| Metric | Value |
|--------|-------|
| Customers analyzed (2026) | 20 (active in 3+ months) |
| Changed channel | 0 |
| Never changed | 20/20 |
| Change history coverage | CANNOT DETERMINE (no SAP change log) |
| Bulk load | Jan 2026: 3,246; Mar 2026: 2,125 |

---

## F. Effective Date Logic

For 2026+:
```
channel_at_sale_date(CardCode, DocDate) =
    OCRD.U_CANAL_VENTAS of the customer at query time
```

**Limitation:** No SAP change history. If a customer changed channel during 2026, we would use the CURRENT value for all dates. Evidence shows no changes in the sample tested.

For pre-2026:
```
channel_at_sale_date = NOT AVAILABLE via U_CANAL_VENTAS
```

---

## G. Pre-2026 Rule

| Field | Status |
|-------|--------|
| Rule version(s) | LEGACY-CHANNEL-RULE-V1 (reconstructed from `activeTools01.py`) |
| Inputs | PriceTypeCode + ClientSegmentationCode |
| Periods | Pre-2026 (exact dates uncertain) |
| Confidence | LOW — PriceTypeCode not available in current SAP, ClientSegmentationCode partially maps to GroupCode |
| Best approximation | Current U_CANAL_VENTAS (with explicit limitation) |

**Legacy rule logic:**
- HORIZONTAL: PriceTypeCode == 11
- LICITACION: PriceTypeCode == 10
- ESPECIAL: Segmentation IN (51, 6)
- SALON: Segmentation IN (100, NULL)
- CORPORATIVO: rest

---

## H. Legacy Taxonomy

| Category | Rule | Volume (2020 Cruzada) |
|----------|------|----------------------|
| SALON | Segmentation IN (100, NULL) | Large (default) |
| HORIZONTAL | PriceTypeCode == 11 | 71,958 rows (88%) |
| LICITACION | PriceTypeCode == 10 | 26 rows (0.03%) |
| ESPECIAL | Segmentation IN (51, 6) | Small |
| CORPORATIVO | rest | 4,858 rows (6%) |

---

## I. Current Taxonomy

| Code | Name | Aug 2026 Net | Customers |
|------|------|-------------|-----------|
| 1 | Farmacias | $187K | 227 |
| 2 | Corporativo | $580K | 421 |
| 3 | Corporativo Grande | $798K | 73 |
| 4 | Supermercados | $140K | 4 |
| 5 | Distribuidoras | $284K | 4 |
| 6 | Regional | $1,700K | 99 |
| 7 | Publico/Retail | $780K | 29 |
| 8 | Especiales | $886K | 147 |
| NULL | Unclassified | $872K | 852 |

---

## J. Homologation

| Legacy | Current | Comparable? | Confidence |
|--------|---------|-------------|------------|
| HORIZONTAL | Multiple (1,2,6,7) | NO | LOW |
| LICITACION | 3 (partial) | PARTIAL | LOW |
| ESPECIAL | 8 | YES | MEDIUM |
| SALON | 1+7+NULL | PARTIAL | LOW |
| CORPORATIVO | 2+3 | PARTIAL | MEDIUM |
| SellerType=22 | N/A | NO | LOW |

**Conclusion:** Legacy and current taxonomies are NOT directly homologable at detail level. Cross-period comparison requires comparable families at higher abstraction.

---

## K. Luz

| Period | Net Sales | Primary Channel | Multi-channel? |
|--------|-----------|----------------|---------------|
| Aug 2026 | $217,863 | canal=6 (Regional) | YES — 4 channels |

**Seller independence proof:** Luz (cat=2 corporate seller) sells to canal=6 (Regional), canal=7 (Public), canal=NULL, and canal=2 (Corporate). Sum of channels = seller total. ✓

---

## L. Soveron

| Period | Net Sales | Activity |
|--------|-----------|----------|
| 2020 | Active (Cruzada Excel, SellerType=21) | Calle seller |
| 2022 | Zero invoices | Inactive |
| 2026-08 | Zero invoices | Inactive |

---

## M. Seller Independence

| Metric | Value |
|--------|-------|
| Sellers with multiple channels | **68 out of 72** (94%) |
| Financial regression | **PASS** — seller totals = channel totals |
| Same seller → multiple channels | Proven for all major sellers |

---

## N. Channel Changes

| Metric | Value |
|--------|-------|
| Customers tested (3+ months in 2026) | 20 |
| Channel changes detected | **0** |
| Stable channel | 20/20 |
| SAP change history | NOT AVAILABLE |

---

## O. Financial Regression

| Metric | Seller View | Channel View | Match |
|--------|------------|-------------|-------|
| Gross | $6,376,407 | $6,376,407 | ✅ |
| Credit Notes | $198,486 | $198,486 | ✅ |
| Net | $6,177,921 | $6,177,921 | ✅ |

---

## P. Corporate Historical Comparison

| Period | Definition | Net Sales |
|--------|-----------|-----------|
| Aug 2026 | Channel 2 only | $579,655 |
| Aug 2026 | Channel 3 only | $798,408 |
| Aug 2026 | Channels 2+3 | $1,378,063 |
| Pre-2026 | Legacy CORPORATIVO | NOT HOMOLOGABLE at detail level |

**Comparability:** LIMITED. Legacy CORPORATIVO was broader than current canal=2+3. Some legacy corporate sales may have been classified differently.

---

## Q. SAP Traceability

| Field | Status |
|-------|--------|
| DocEntry | PASS |
| LineNum | PASS |
| SlpCode | PASS |
| CardCode | PASS |

---

## R. Files

| Artifact | Path |
|----------|------|
| Sales dimension analysis | `validation/sales_dimensions/sales_dimension_analysis.json` |
| Channel homologation | `validation/sales_dimensions/channel_homologation.yaml` |
| Sales dimensions final report | `validation/sales_dimensions/SALES_DIMENSIONS_FINAL_REPORT.md` |
| Sales dimension script | `validation/sales_dimensions/sales_dimension_analysis.py` |

---

## S. Parquet

Legacy: READ ONLY. New: NO.

---

## T. SAP

Writes: NONE.

---

## U. Infrastructure

VPN: UNCHANGED. Podman: UNCHANGED.

---

## V. Team360

GLOBAL CHANGES: NONE.

---

## W. Próximo paso

**READY_FOR_TELCHI_SALES_REPORTING_CONTRACT**

The dimensional model is established:
- **Seller** = independent dimension (SlpCode-based)
- **Customer Channel** = independent dimension (OCRD.U_CANAL_VENTAS, 2026+)
- **Cross-period comparison** = limited by taxonomy differences
- **Pre-2026** = use current U_CANAL_VENTAS with explicit limitation
