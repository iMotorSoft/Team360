# Temporal commercial purpose contract V1

This additive contract separates dated product usage from legacy accumulated purpose. It binds an explicit candidate and preserves all existing product fields and quantity files.

## Compatibility and meaning

The existing `commercial_purpose` field retains the V1 observed/intended classification bounded by its source windows. Its values are unchanged; it never asserts permanent or current-period exclusivity.

`commercial_purpose_semantics_version=legacy-bounded-v1` makes that compatibility meaning explicit. The original source flags, confidence, evidence and classification remain byte-for-byte equivalent at logical row level. The component envelope stays compatible; the additive contract `temporal_commercial_purpose_v1` has its own version `1.0.0`.

`historical_usage_profile` describes only observed positive uses in available dated evidence. Values are MIXED, COMMERCIAL_EVIDENCE_ONLY, INTERNAL_EVIDENCE_ONLY and UNKNOWN. The evidence-only values describe facts, not exclusive intent or complete lifetime history. Both uses at different dates can establish historical MIXED.

## Temporal facts and reader

Dates precede classification. Each product retains commercial and internal first/last dates and sorted distinct usage dates, with source relations and coverage provenance in the sealed component.

The four fact fields are `commercial_evidence_first_date`, `commercial_evidence_last_date`, `internal_use_evidence_first_date` and `internal_use_evidence_last_date`. `temporal_usage_dates` preserves product/day/domain observations; native event relations remain pinned in the contract rather than copied as a new fact engine.

`TemporalPurposeReader(component).commercial_purpose_for_period(ItemCode, period_from, period_to, lookback_days=0)` reads one hash-verified product row. It fails closed without the explicit versioned contract or a unique product. It never resolves latest sources or falls back to a different candidate. Dates are inclusive.

Positive commercial evidence is a noncancelled valid invoice line with positive native quantity. Even an isolated invoice establishes an observed commercial event; it does not establish exclusive intent. Positive internal evidence is an actual noncancelled positive production issue with source-native `BaseType=202`. Flags, BOM and warehouse role alone are not dated consumption events.

## Period classification and coverage

The classifier uses positive observations inside the evaluated interval. Absence has meaning only with explicit proof that the opposite entire usage domain is covered for that product and interval.

MIXED requires positive commercial and internal events within the same evaluated interval, though they need not occur on the same day. COMMERCIAL_ONLY requires positive commerce and proven complete coverage without internal events. INTERNAL_ONLY applies symmetrically. No events, incomplete opposite coverage or undated intent preserve UNKNOWN.

Coverage proofs include inclusive intervals, completeness status, source proof, domain scope and item scope. Adjacent intervals can cover a period; holes, missing proofs, a different product scope or production-only coverage cannot prove whole-domain absence. Observed min/max dates and sealed files do not imply completeness.

The materialized candidate retains `sales_coverage_from/to` and `production_coverage_from/to`, plus `temporal_usage_coverage` distinguishing captured windows from proven completeness. Current inputs are PARTIAL for whole-domain absence: the last source day is intraday and production issues do not certify every internal purpose. Thus UNKNOWN with positive commercial evidence is valid and analytically evaluable.

## Explicit lookback

Lookback is a caller parameter, never a hidden universal rule. The result identifies both the requested period and the enlarged evaluated interval.

`lookback_days=365` extends evaluation start by 365 days. Provenance retains period, effective interval, lookback and coverage. `commercial_purpose_without_lookback` and `requested_period_evidence` preserve the strict requested-period result; a lookback MIXED never silently becomes MIXED within 2026.

The 365-day scenario in the 24-case matrix is diagnostic. Case groups are disjoint: MIXED_WITHIN_2026 first, otherwise MIXED_WITH_LOOKBACK, otherwise HISTORICALLY_MIXED_ONLY, otherwise INSUFFICIENT_TEMPORAL_EVIDENCE. All 24 are historically mixed and none is mixed strictly in 2026; fifteen qualify under explicit lookback and nine require older evidence. The business replay uses zero lookback.

## Business query eligibility

The period replay requires positive commerce in the requested interval or strict period COMMERCIAL_ONLY/MIXED. An UNKNOWN purpose can be evaluated when its period commercial evidence is positive.

Undated source intent, historical-only commerce and BOM alone do not establish period commerce. This deliberately excludes products with only undated commercial intent or historical sales from this temporal commercial replay. A future query for intended commercial assortment is a different explicitly named contract; it must not silently supply eligibility here.

Stock, UoM resolution, quantity window and ranking remain pinned. Net zero from actual period invoices/credits can still be evaluated. The existing quantity sidecar supports only its declared window; this gate replays exactly 2026-01-01 through 2026-09-24 and preserves its September 23 closed-day coverage metric.

The ranking remains ratio descending, last sale ascending, sales days ascending, then ItemCode. Preserved products retain identical stock and net quantity. L01791, L02492 and L02170 enter TOP 10 because their valid period sales now establish evidence even while purpose is UNKNOWN. L01200, L02135 and L02158 remain evaluable but fall below those entries.

## Gold controls and publication boundary

Gold checks distinguish legacy purpose, period facts and eligibility. A temporal UNKNOWN does not erase a verified source flag or establish the opposite use.

L00002 has both observed uses within 2026 and remains temporal MIXED. L02475 has production consumption without period commerce and stays conservative. L00954 has period commerce without demonstrated internal consumption; BOM does not make it MIXED. L00759 and L00761 retain legacy INTERNAL_ONLY/non-sellable controls and remain outside the commercial replay; partial coverage cannot invent period exclusivity or consumption for L00759.

A fresh immutable candidate uses the official publication store. All eight original components, legacy product fields and UoM files remain exact. The 422 ingestion gaps and 384 business unknown records are preserved, not reopened. PASS here validates semantics and reproducibility, not source completeness or zero UNKNOWN.

Promotion is a separate gate. This gate may mark the validated candidate READY_TO_COMMIT and report semantic eligibility, but never calls logical commit or changes CURRENT. Reports and the 24-case matrix live in `data/reports/telchi/temporal_commercial_purpose_v1/`; runners live in `investigation/validation/temporal_commercial_purpose_v1/`.
