# TEAM360 TELCHI — CORPORATE SALES AUGUST 2026 FINAL REPORT

**Gate:** `TEAM360_TELCHI_CORPORATE_SALES_AUGUST_2026_PASS`
**Date:** 2026-08-20

---

## A. Resultado

**TEAM360_TELCHI_CORPORATE_SALES_AUGUST_2026_PASS**

Corporate sales amount for August 2026 (MTD) delivered with full SAP traceability.

---

## B. Historical Rule

The legacy DataScience code (`activeTools01.py`, `srvSyncTelchi02.py`) used a **Canal (Channel) classification** applied per-sale:

1. **HORIZONTAL**: PriceTypeCode == 11
2. **LICITACION**: PriceTypeCode == 10
3. **ESPECIAL**: PriceTypeCode NOT IN (10,11) AND ClientSegmentationCode IN (51, 6)
4. **SALON**: PriceTypeCode NOT IN (10,11) AND ClientSegmentationCode IN (100, NULL)
5. **CORPORATIVO**: Everything else — PriceTypeCode NOT IN (10,11) AND ClientSegmentationCode NOT IN (100, NULL, 51, 6)

This was a **process of elimination** per sale (TSSale). CORPORATIVO was the catch-all for sales with non-standard pricing and non-standard customer segmentation.

**Current HANA**: Uses `OSLP.U_CATVENDEDOR` (seller category) instead of per-sale classification. This is a simplification — the legacy system classified per-sale, the current system classifies per-seller.

---

## C. SellerType Semantics

| Value | Legacy Meaning | Current HANA |
|-------|---------------|--------------|
| 0 | Salón | U_CATVENDEDOR = NULL (most sellers) |
| 21 | Calle | U_CATVENDEDOR = 1 (24 sellers) |
| 22 | Corporativo | U_CATVENDEDOR = 2 (7 sellers) |

**Confirmation: PASS** — The corporate classification is preserved in the current system via `U_CATVENDEDOR=2`.

---

## D. Legacy Pipeline

```
SAP OINV/ORIN (SlpCode)
    ↓
OSLP.SlpName (seller name)
    ↓
Legacy: PriceTypeCode + ClientSegmentationCode → Canal
Current: OSLP.U_CATVENDEDOR → Seller Category
    ↓
Filter: CORPORATIVO (cat=2)
    ↓
Sales amount
```

**Key files:**
- `activeTools01.py` (line ~2042): Canal classification logic
- `srvSyncTelchi02.py` (line ~528): Same Canal logic
- `srvSyncTelchiSB101.py`: SAP HANA extraction (no Canal logic)

---

## E. Historical Parquet

- **Discovery month**: 2022-08
- **File**: `saleSB1Product-2022-08-31.parq`
- **Rows**: 68,612
- **Has SellerType**: NO (not in Parquet schema)
- **Has PriceTypeCode**: NO
- **Has ClientSegmentation**: NO

The Canal logic was applied post-extraction, not in the Parquet itself.

---

## F. Luz 2022

| Field | Value |
|-------|-------|
| SellerCode/SlpCode | 13 |
| Seller name | Luz Guzman |
| U_CATVENDEDOR | 2 (CORPORATE) |
| Aug 2022 rows | 640 |
| Aug 2022 DocTotal | $698,029.55 |
| Classification | CORPORATE |

---

## G. Soveron 2022

| Field | Value |
|-------|-------|
| SellerCode/SlpCode | 9 |
| Seller name | Luis Soveron Yovio |
| U_CATVENDEDOR | NULL (NOT CLASSIFIED) |
| Aug 2022 rows | 0 |
| Aug 2022 DocTotal | $0 |
| Classification | NOT CORPORATE |

**Note:** Soveron was SellerType=21 (calle) in the 2020 Cruzada Excel and has no activity in Aug 2022 Parquet. In current HANA, Soveron has `U_CATVENDEDOR=NULL`.

---

## H. Corporate Sellers 2022

| SlpCode | Name | U_CATVENDEDOR | Aug 2022 Rows | Aug 2022 DocTotal |
|---------|------|--------------|---------------|-------------------|
| 10 | Federico Herrera Añez | 2 | 209 | $2,310,292.86 |
| 11 | Selva Rojas Jaimes | 2 | 734 | $2,301,950.88 |
| 12 | Kaly Franco Cassia | 2 | 438 | $454,814.92 |
| 13 | Luz Guzman | 2 | 640 | $698,029.55 |

---

## I. Rule Evidence

| Field | Value |
|-------|-------|
| Accepted rule | OSLP.U_CATVENDEDOR = 2 |
| Key | SlpCode (seller-level) |
| Temporal | YES — seller category can change |
| Customer dependent | NO (current rule is seller-level) |
| Other dimensions | None — single field classification |

---

## J. Sales Metric

| Field | Value |
|-------|-------|
| Historical metric | DocTotal (header-level, per invoice) |
| Formula | SUM(OINV.DocTotal) WHERE SlpCode IN (cat=2 sellers) AND CANCELED='N' |
| Discount handling | Included in DocTotal (SAP calculates net) |
| Credit notes | Subtracted (SUM(ORIN.DocTotal) for same filter) |
| Cancellation | Excluded via CANCELED='N' |

---

## K. Current Translation

The legacy Canal rule used `PriceTypeCode` + `ClientSegmentationCode` per-sale. The current system uses `OSLP.U_CATVENDEDOR` per-seller. The translation is:

```
Legacy: Canal=CORPORATIVO (per-sale rule)
Current: U_CATVENDEDOR=2 (per-seller attribute)
```

This is documented as a simplification. The per-seller classification is stable and auditable in SAP.

---

## L. August 2026

| Field | Value |
|-------|-------|
| Period | 2026-08-01 → 2026-08-20 |
| Status | **MTD (month to date)** |
| Gross corporate invoices | **$1,516,859.75** |
| Corporate credit notes | **$45,889.46** |
| **Net corporate sales** | **$1,470,970.29** |
| Corporate invoices | 376 |
| Corporate customers | 162 |
| Corporate sellers (active) | 4 |
| Line items | 1,349 |
| Corporate share of total | 1.7% |

---

## M. By Seller

| SlpCode | Name | Invoices | DocTotal | Credit Notes | Net | Customers |
|---------|------|----------|----------|-------------|-----|-----------|
| 11 | Selva Rojas Jaimes | 85 | $764,459.63 | 1 ($23,000) | $741,459.63 | 34 |
| 139 | Heglin Sigfredo Justiniano Camacho | 36 | $350,328.59 | 1 ($17,654.80) | $332,673.79 | 22 |
| 13 | Luz Guzman | 219 | $220,870.83 | 4 ($4,594.66) | $216,276.17 | 86 |
| 236 | Diego Barrientos | 36 | $181,200.70 | 1 ($640.00) | $180,560.70 | 20 |

---

## N. Luz / Soveron Current

| Seller | Classification | Aug 2026 Invoices | Aug 2026 Net |
|--------|---------------|-------------------|-------------|
| Luz Guzman (13) | cat=2 (CORPORATE) | 219 | $216,276.17 |
| Luis Soveron Yovio (9) | cat=NULL (NOT CLASSIFIED) | 0 | $0 |

---

## O. Other Corporate Sellers

Corporate sellers with NO August 2026 activity:

| SlpCode | Name | U_CATVENDEDOR |
|---------|------|--------------|
| 10 | Federico Herrera Añez | 2 |
| 12 | Kaly Franco Cassia | 2 |
| 165 | Carmen Dora Valdez Mergar | 2 |

---

## P. SAP Traceability

| Field | Value |
|-------|-------|
| DocEntry | PRESERVED |
| LineNum | PRESERVED |
| Source tables | OINV, ORIN, OSLP |
| Link | OINV.SlpCode = OSLP.SlpCode |
| Filter | OSLP.U_CATVENDEDOR = 2 |
| Sample validation | PASS (grain verified: DocEntry unique) |

---

## Q. Cancelled

| Field | Value |
|-------|-------|
| Policy | Excluded via CANCELED='N' |
| Documents affected | 0 corporate cancelled in Aug 2026 |

---

## R. Credit Notes

| Field | Value |
|-------|-------|
| Policy | Subtracted from gross |
| Gross invoices | $1,516,859.75 |
| Credit notes | $45,889.46 (7 notes) |
| Net | $1,470,970.29 |

---

## S. Sanity

| Check | Result |
|-------|--------|
| Double counting | NO (DocEntry unique) |
| Grain | PASS (document + line) |
| Corporate <= total sales | PASS (376 <= 22,058) |
| Credit notes < invoices | PASS ($45,889 < $1,516,860) |

---

## T. Files

| Artifact | Path |
|----------|------|
| Rule evidence | `validation/corporate_sales/corporate_rule_evidence.json` |
| Aug 2026 results | `validation/corporate_sales/august_2026_corporate_sales.json` |
| Final report | `validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md` |

All under: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/`

---

## U. Parquet

| Field | Value |
|-------|-------|
| Legacy modified | NO |
| New Parquet | NO |

---

## V. SAP

| Field | Value |
|-------|-------|
| Writes | **NONE** |
| Reads | Read-only (SELECT) |

---

## W. Infrastructure

| Field | Value |
|-------|-------|
| VPN | UNCHANGED |
| Podman | UNCHANGED |

---

## X. Team360

| Field | Value |
|-------|-------|
| GLOBAL CHANGES | **NONE** |
