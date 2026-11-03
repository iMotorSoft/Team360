# Product commercial semantics V1

This component enriches a pinned Foundation with product purpose and comparable line quantities. It never promotes a ranking, threshold, forecast or inferred brand.

## Publication and readers

The component uses the extensible manifest envelope and the official candidate store. Existing eight components, catalog identities and base snapshot remain exact.

`product_commercial_semantics.py` builds immutable `product_purpose` and `product_sales_uom` crosswalks. `FoundationAccess.product_semantics_relation(dataset)` exposes hash-verified SQL relations. Missing components fail closed; there is no latest fallback.

The product grain is `SAP_HANA + ItemCode`. Conversion grain is `source_system + document_kind + DocEntry + LineNum`. Source facts remain in their existing Atomic datasets. Quantity conversions preserve Atomic identity and raw extraction lineage.

Every component binds the exact base Foundation, reference version, snapshot and component hash. Sealed conversion files can be reused when their hashes and dependency evidence remain valid. No CURRENT publication is edited in place.

## Purpose and uncertainty

Purpose describes defensible observed or intended usage within declared coverage. It does not certify a product's complete historical or future usage.

- `MIXED`: recurring observed sales, or an invoice corroborated by validated commercial classification, together with positive noncancelled production issues linked source-natively to production orders (`BaseType=202`).
- `INTERNAL_ONLY`: actual production consumption, or BOM participation plus validated input classification, with `SellItem=N` and no observed commercial invoices. This combines independent evidence; BOM alone does not establish actual consumption.
- `COMMERCIAL_ONLY`: supported commerce without observed production use or BOM evidence of potential contrary use. Support comes from observed sales or validated commercial classification combined with `SellItem=Y`. Provenance remains `DERIVED_PARTIAL`, confidence `MEDIUM`, because absence of issues is window bounded.
- `UNKNOWN`: insufficient or contradictory evidence, including operational consumption with an enabled sell flag but no supported sales, an isolated input sale, or commercial evidence plus BOM participation without actual production issues.

Every row retains purpose, provenance, evidence JSON and confidence. `commercially_observed` and `operationally_observed` remain independent facts. `commercially_supported` additionally includes evidence of intended commercial use.

Commercial queries may include purpose `UNKNOWN` when `commercially_observed=true`, while reporting uncertainty about the second role. This preserves sold packaging such as `L00954` without asserting that it is exclusively commercial or that BOM membership proves actual consumption.

Names, prefixes, `LIKE`, brand guesses and arbitrary inventory exits are never classification evidence. The replay's previously declared L cohort is an analytical scope, not a Foundation purpose or brand rule.

## Temporal extension V1

The existing purpose field remains the legacy accumulated observed/intended V1 classification. Period analysis uses a separate additive contract; legacy MIXED across source windows is not a permanent or current-period assertion.

The contract and reader are defined in [Temporal commercial purpose V1](TEMPORAL_COMMERCIAL_PURPOSE_V1.md). They preserve dated observations, historical usage profile, explicit whole-domain coverage and caller-specified lookback. No legacy product values or quantity files are rewritten.

`TemporalPurposeReader(component).commercial_purpose_for_period(...)` evaluates both positive uses inside an explicit interval. Missing opposite-domain completeness preserves UNKNOWN. Temporal business eligibility uses period commercial evidence rather than undated intent or historical-only MIXED.

## Units and net quantity

Comparable quantity requires a verified line factor into the same item's inventory unit. Master unit names and invoice base links never substitute for line conversion evidence.

Invoice factors are recovered through exact extraction lineage and matching Atomic keys and values. Credit factors can be supported by the hash-verified September 17 historical extraction only when line quantities, amounts, warehouse, base references, customer, currency, document amounts and cancellation match pinned raw, and document dates agree.

Credit document create/update dates must also agree and the last update must predate the historical extraction day. This is `MATCHED_HISTORICAL_SOURCE` / `UOM_RESOLVED_SUPPORTED`, not exact current extraction evidence. Unmatched or changed lines remain unresolved and require future ingestion.

States are `UOM_RESOLVED_EXACT`, `UOM_RESOLVED_SUPPORTED`, `UOM_UNRESOLVED` and `UOM_INCOMPATIBLE`. Known MASS/VOLUME conflicts are rejected without density; absent or invalid factors never default to one.

`invoice_base_qty - credit_memo_base_qty = net_sales_base_qty` is valid only at one ItemCode and inventory UoM. A single unresolved or incompatible line blocks the entire product total; duplicate keys fail. Credit quantities retain source sign and subtract from invoices without changing their accounting meaning.

The sidecar quantity coverage is January 1 through September 24, 2026. Consumers must reject requests outside the declared quantity window rather than treating missing sidecar rows as zero sales.

## Stock and consumption

Stock and actual consumption reuse pinned facts and retain temporal and unit grain. Open purchase orders remain a separate supply dimension.

`FoundationAccess.stock_availability()` exposes `on_hand_qty`, `committed_qty`, `available_qty = on_hand - committed` and `stock_as_of`, by source, product, warehouse and inventory UoM. Negative availability remains visible. Global sums require identical ItemCode, compatible UoM, identical cutoff and unique warehouses.

The component's production-consumption contract binds verified existing `production_issue` files and their manifests. Only noncancelled positive lines with `BaseType=202` establish actual production use. Parent orders outside the captured order window are reported, not erased. BOM is potential participation, not consumption.

## Brand, amount and coverage

Independent contracts retain uncertainty instead of inventing source evidence. Missing brand and monetary attribution do not invalidate resolved quantities.

Brand is `UNKNOWN`, provenance `UNRESOLVED`: the pinned brand dimension is empty and products have no explicit trusted assignment. L codes and Litel names do not define brand.

Net product amount remains `NET_PRODUCT_AMOUNT_UNRESOLVED`. Current pinned invoice evidence cannot establish source-native or confirmed header-discount allocation by product. Line-total subtraction is not presented as net product revenue.

Sales, credits, stock and consumption retain `data_as_of`, `coverage_from`, `coverage_to` where meaningful, and explicit coverage meanings. Observed document bounds are not historical completeness proofs. Stock is point-in-time; sales and credits have different intraday extraction times.

## Closure evidence

The closure remains DEGRADED and does not authorize atomic promotion. Gate D is DEGRADED, so the final candidate stays VALIDATING and CURRENT remains unchanged.

Generated evidence is in `data/reports/telchi/product_commercial_semantics_v1/`: `discovery.json`, `contract.json`, `report.json` and `replay.json`. Scripts live in `investigation/validation/product_commercial_semantics_v1/`; productive code never imports them.

`run_closure.py` performs sequential discovery, contracts, candidate creation and replay. `finalize_validation.py` can revalidate purpose using sealed UoM files without repeating capture or copying conversion datasets. Neither script invokes SAP or promotion.

The final report distinguishes all 16,934 SAP products from the baseline cohort of 720 purpose-unresolved products and 468 UoM-unresolved products. Baseline cohort comparisons must not be confused with global unknown totals.

Gold fixtures preserve the real pinned evidence for `L00759`, `L00761`, `L02475`, `L00954`, observed mixed materials and commercial examples. Compatibility includes real material-supply and receivables readers under a read-only simulated candidate CURRENT, as well as exact base identities and stock value parity.
