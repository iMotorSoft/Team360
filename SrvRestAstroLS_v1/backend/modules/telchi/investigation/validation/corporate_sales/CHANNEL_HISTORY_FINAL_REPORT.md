# TEAM360 TELCHI — U_CANAL_VENTAS HISTORICAL VALIDITY

**Gate:** `TEAM360_TELCHI_CUSTOMER_CHANNEL_HISTORY_PASS`
**Date:** 2026-08-20

---

## A. Resultado

**TEAM360_TELCHI_CUSTOMER_CHANNEL_HISTORY_PASS**

`U_CANAL_VENTAS` was **created and bulk-loaded in 2026**. It has zero historical existence before that date. This means it CANNOT be used as historical truth for sales before 2026.

---

## B. U_CANAL_VENTAS

| Field | Value |
|-------|-------|
| SAP object | OCRD (Business Partner) |
| Field | U_CANAL_VENTAS (UDF) |
| Valid values | 1=Farmacias, 2=Corporativo, 3=Corporativo Grande, 4=Supermercados, 5=Distribuidoras, 6=Regional, 7=Publico/Retail, 8=Especiales, NULL=Unclassified |
| SAP change history | NOT_AVAILABLE |
| Creation date | UNKNOWN (SAP doesn't expose UDF creation date) |
| Earliest proven usage | **2026-01** |

---

## C. Earliest Evidence

| Source | Date | Finding |
|--------|------|---------|
| SAP OCRD.UpdateDate | 2026-01 | First customers with canal assigned |
| Zero before 2026 | confirmed | No customer had U_CANAL_VENTAS before Jan 2026 |
| clientSB1.parq snapshot | 2024-05-24 | No U_CANAL_VENTAS field exists |
| Legacy Python code | never | No reference to U_CANAL_VENTAS anywhere |
| Cruzada Excel (2020) | 2020 | Uses SellerType, not U_CANAL_VENTAS |

---

## D. Adoption Timeline

| Period | Customers with canal | Coverage | Confidence |
|--------|---------------------|----------|------------|
| Before 2026-01 | 0 | 0% | N/A — field didn't exist |
| 2026-01 | 3,246 | bulk wave 1 | HIGH |
| 2026-02 | +53 | incremental | HIGH |
| 2026-03 | +2,125 | bulk wave 2 | HIGH |
| 2026-04..08 | +748 | ongoing | HIGH |
| Total | 6,172 | of 12,912 customers | 48% |

---

## E. Customer Change History

| Metric | Value |
|--------|-------|
| Customers analyzed | 12,912 |
| With canal | 6,172 (48%) |
| Without canal | 6,740 (52%) |
| Never changed | CANNOT DETERMINE — no SAP change history |
| Changed once | CANNOT DETERMINE |
| Changed multiple | CANNOT DETERMINE |

**Limitation:** SAP change history for UDFs is not available. We cannot determine if/when individual customers changed channels.

---

## F. Bulk Changes

| Date | Customers affected | Interpretation |
|------|-------------------|----------------|
| 2026-01 | 3,246 | **Major bulk initialization** by user `faparicio` |
| 2026-03 | 2,125 | **Second bulk wave** |
| 2026-02..08 | 802 | Ongoing individual assignments |

**Primary user:** `faparicio` modified 5,287 customers (UserSign2)
**System user:** `dms` created 3,460 customers (UserSign)

---

## G. Historical Sources

| Source | Available | Contains channel info |
|--------|-----------|----------------------|
| SAP change history | NO | N/A |
| Customer snapshots | YES (2024-05) | NO U_CANAL_VENTAS (didn't exist) |
| Legacy Excel (Cruzada 2020) | YES | SellerType (0/21/22) |
| Legacy Parquet | YES | No channel field |
| Legacy Python | YES | Canal rule (PriceType + Segmentation) |

---

## H. Legacy Rule Transition

The classification evolved through three eras:

1. **2020 era (Cruzada Excel):** `SellerType` (0/21/22) assigned per-sale, not per-customer
2. **Legacy Python era:** Canal calculated from `PriceTypeCode + ClientSegmentationCode` as reporting logic
3. **2026 era (current):** `U_CANAL_VENTAS` on OCRD, bulk-loaded in Jan-Mar 2026

The 2026 bulk load was a **manual reclassification**, not a migration. The crosswalk between `ClientSLPropertyName` (old segmentation) and `U_CANAL_VENTAS` (new) shows NO clean mapping:
- Farmacias → mostly NULL (3,385 unclassified)
- Ferreterias → mostly canal=2 (corporativo)
- Veterinarias → mostly canal=2 (corporativo)

---

## I. As-Of Classification

| Period | Strategy | Confidence |
|--------|----------|------------|
| Before 2026 | U_CANAL_VENTAS **NOT AVAILABLE** as historical truth | N/A |
| 2026-01 onward | U_CANAL_VENTAS is current truth | HIGH |

**Critical implication:** When analyzing 2022 sales with `OCRD.U_CANAL_VENTAS`, we are applying a **2026 classification** to **2022 operations**. This is acceptable ONLY if:
1. We acknowledge the limitation
2. The customer's channel hasn't changed since 2022
3. We're not making business decisions that depend on historical channel accuracy

---

## J. Customer Examples

Verified stable customers (same channel from 2022 to 2026):
- C000001 (ALMARK): canal=3 since 2022-03 through 2026-08
- C003728 (VENTAS CORPORATIVAS- HORIZONTAL): canal=3 since 2022-04 through 2026-08
- C000010 (DISPROMED SRL.): canal=5 since 2022-04 through 2026-08

No channel changes detected in the sample — but this doesn't prove stability for ALL customers.

---

## K. Current vs Historical Risk

**2022 sales with current U_CANAL_VENTAS:**
- Total 2022 docs: 232,749
- With channel: 200,288 (86%)
- Without channel (NULL): 32,461 (14%, $15.3M)

**Risk:** 14% of 2022 sales have NO channel classification. The 86% that DO have a channel are using the CURRENT customer state, which was assigned in 2026.

---

## L. Channel 2 vs Channel 3

| Channel | Name | Aug 2026 Net | Customers |
|---------|------|-------------|-----------|
| 2 | Corporativo | $579,157 | 420 |
| 3 | Corporativo Grande | $798,408 | 73 |
| 2+3 combined | — | $1,377,565 | 493 |

**Evidence of grouping:** None found. No legacy evidence that channels 2 and 3 were ever combined in reporting.

**Recommendation:** Report separately. Channel 3 (Corporativo Grande) has FEWER customers but HIGHER average ticket ($10.9K vs $1.4K per customer).

---

## M. August 2026

| Method | Net | Notes |
|--------|-----|-------|
| Channel 2 only | $579,157 | "Corporativo" |
| Channel 3 only | $798,408 | "Corporativo Grande" |
| Channels 2+3 | $1,377,565 | Combined |
| Seller-category (cat=2) | $1,525,412 | WRONG — overstates by $946K |

---

## N. Effective Period Contract

| Period | Source | Method | Confidence |
|--------|--------|--------|------------|
| Before 2026 | N/A | U_CANAL_VENTAS not available | N/A |
| 2026-01 → current | OCRD.U_CANAL_VENTAS | Direct field | HIGH |

---

## O. Files

| Artifact | Path |
|----------|------|
| Channel history coverage | `validation/corporate_sales/channel_history_coverage.json` |
| Channel history final report | `validation/corporate_sales/CHANNEL_HISTORY_FINAL_REPORT.md` |
| Previous: business rule discovery | `validation/corporate_sales/business_rule_discovery.json` |
| Previous: channel rule final report | `validation/corporate_sales/CHANNEL_RULE_FINAL_REPORT.md` |

---

## P. Parquet

Legacy: READ ONLY. New: NO.

---

## Q. SAP

Writes: NONE.

---

## R. Infrastructure

VPN: UNCHANGED. Podman: UNCHANGED.

---

## S. Team360

GLOBAL CHANGES: NONE.

---

## T. Próximo paso

**READY_FOR_TELCHI_TEMPORAL_CHANNEL_CLASSIFICATION_MODEL**

The historical validity question is resolved:
- `U_CANAL_VENTAS` is **2026-only** — not historical truth
- For 2022 reporting, the field can be used as a **current approximation** with explicit limitation
- For true historical accuracy, a different approach is needed (legacy rule reconstruction or acceptance of approximation)
