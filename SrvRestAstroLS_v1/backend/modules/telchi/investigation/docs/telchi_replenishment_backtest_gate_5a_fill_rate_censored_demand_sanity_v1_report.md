# TELCHI — Replenishment Backtest Gate 5A
## Fill rate / censored demand sanity check V1

**Gate:** `TELCHI_REPLENISHMENT_BACKTEST_GATE_5A_FILL_RATE_CENSORED_DEMAND_SANITY_CHECK`\
**Stage:** `INVESTIGATION` · `SAP_HANA + DATA_LAKE` · `READ ONLY` · `SAP_WRITE_COUNT=0`\
**Primary universe:** `ItemCode LIKE 'L%'` · `Branch=2A` · 10 products L\
**Level B:** not executed.

## A. Verdict

`FILL_RATE_CEILING_EFFECT_DETECTED`.

The observed fill rate cannot be used alone to distinguish “we sold everything
requested” from “we had no product and the request disappeared from SAP”. The
comparability contract passed for all 10 pairs, but four products had stockout
days while their observed fill rate remained 100%. One of those four also has
sufficient pre/post/replenishment evidence for a `POSSIBLE_CENSORED_DEMAND`
day. This is not a confirmed lost-sale amount.

Decision: `DO_NOT_EXECUTE_LEVEL_B_100_PRODUCTS_UNTIL_GATE_5A_REVIEWED`.

## B. Current fill-rate audit

Window: **2025-09-12..2026-09-11**, 365 daily rows per `ItemCode × Branch`.
`fulfilled_observed_demand` equals observed demand by definition of the CURRENT
observable baseline; therefore every product with positive observed demand has
an observed fill rate of 1.0.

| ItemCode | Observed demand | Fulfilled observed | Current fill | Stockout days | Episodes | Mean duration | `stock <= 0` days | Sales during stockout days | Sales 30d before | Sales 30d after | Censoring signal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| L00003 | 74,175 | 74,175 | 100.00% | 1 | 1 | 1.0 | 1 | 498 | 4,380 | 5,224 | No: demand was observed on the stockout day |
| L00503 | 20,827 | 20,827 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L00504 | 67,491 | 67,491 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L00505 | 25,609 | 25,609 | 100.00% | 1 | 1 | 1.0 | 1 | 295 | 5,629 | 1,548 | No: demand was observed on the stockout day |
| L01013 | 8,038 | 8,038 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L01059 | 25,384 | 25,384 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L01675 | 8,835 | 8,835 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L01785 | 6,675 | 6,675 | 100.00% | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 | None |
| L02467 | 100,000 | 100,000 | 100.00% | 339 | 2 | 169.5 | 339 | 100,000 | 100,000 | 0 | No: no recurrent pre/post + replenishment pattern |
| L03192 | 12,625 | 12,625 | 100.00% | 2 | 1 | 2.0 | 2 | 50 | 1,925 | 800 | `POSSIBLE_CENSORED_DEMAND` on 1 zero-demand day |

Summary: **4/10** have `stockout > 0` and observed fill near 100%; **1/10**
has a reproducible possible-censoring signal. The audit does not relabel the
498, 295 or 100,000 units observed during stockout as lost sales.

Other CURRENT metrics across the 10 pairs:

- observed demand: **349,659**;
- stockout days mean: **34.3**;
- availability rate mean (`stock > 0`): **90.60%**;
- average inventory mean: **1,216.58**;
- observed sales during stockout days: **100,843**;
- possible-censoring zero-demand days: **1**.

## C. Comparability contract

All 10/10 pairs passed. CURRENT and the simulator used:

- the same **365-day period** and daily rows;
- the same daily `OBSERVED_DEMAND` sequence in the observed/LOW comparison;
- the same observed-demand-only fulfillment definition;
- the same initial stock reconstruction;
- the same convention: `opening → scheduled arrivals → policy → observed demand → closing`.

The initial state is auditable rather than silently assumed. For example,
`L00003` has first-day stock 527 and net movement -200, so both paths use
inferred opening stock **727**. The per-pair signatures and checks are in
`comparability.jsonl`.

The simulator does not reconstruct a formula for CURRENT; CURRENT remains a
descriptive historical baseline. This avoids comparing a fitted policy against
a different baseline semantic.

## D. Complementary operational metrics

The observed baseline is not a single score. It must be read together with
stockout days, episodes, duration, availability, replenishment count and
inventory.

At the aggregate mean level, under the observed/LOW demand basis:

| Scenario | Best observed fill among alternatives | Mean stockout days | Mean availability | Mean inventory | Interpretation |
|---|---|---:|---:|---:|---|
| CURRENT | 100.00% | 34.3 | 90.60% | 1,216.6 | Historical reference; fill is censored |
| Best alternative, LT=0 (`MIN_MAX`) | 65.96% weighted | 28.4 | 92.22% | 10,231.1 | Fewer stockouts, but much more inventory and lower comparable service |
| Best alternative, LT=3 (`MIN_MAX`) | 65.31% weighted | 33.1 | 90.93% | 9,960.8 | Small availability gain at large inventory cost |
| Best alternative, LT=7 (`HYBRID`) | 64.43% weighted | 36.8 | 89.92% | 9,521.3 | No operational win in this comparison |

The weighted alternative fill is lower because the simulated policy is evaluated
against the same observed-demand history, while CURRENT credits every observed
sale as fulfilled. It is not evidence that CURRENT has perfect physical service.
It is evidence that the metric comparison is dominated by the ceiling/censoring
problem and must not be reduced to fill rate.

The Level A grid contains **1,140** simulations. No alternative produced a
strictly positive fill-rate delta against CURRENT in the observed run. This does
not establish that no policy can improve physical service; it establishes only
that this observable metric cannot demonstrate such an improvement here.

## E. Censored-demand sensitivity

Only the one zero-demand day in `L03192` met the reproducible evidence rule:
stockout, zero observed demand, recurrent observed sales before and after, and a
subsequent replenishment. The estimate is not reported as a sale.

| Level | Reproducible method | Imputed demand | Current fill rate under sensitivity |
|---|---|---:|---:|
| LOW | Observed demand only | 0.0 | 100.0000% |
| BASE | Prior 30-calendar-day mean | 62.5 | 99.9821% |
| HIGH | Max(BASE, prior 90-day positive-demand p90) | 237.5 | 99.9321% |

Sensitivity amount is based only on history before the affected day. Eligibility
uses retrospective post-episode evidence to determine whether a sensitivity is
allowed; consequently this is a controlled retrospective sensitivity, not a
leakage-free forecast and not a lost-sales claim.

All three scenarios re-ran the same 19 policy configurations and six lead-time
scenarios: **3,420 sensitivity simulations** in total. No sensitivity scenario
produced a strictly positive fill-rate delta against its corresponding CURRENT
sensitivity baseline. The operational metrics change only marginally around the
single imputed day; the conclusion remains driven by stockout/availability
metrics, not by a new sales estimate.

## F. Limitations and next decision

- `OBSERVED_DEMAND` is a lower-bound observable during stockout; SAP does not
  expose the unobserved request automatically.
- `POSSIBLE_CENSORED_DEMAND` means evidence-compatible, not confirmed lost sale.
- Intraday order/receipt/sale sequence remains unknown.
- Physical lead time remains unresolved; scenarios 0/1/2/3/5/7 are explicit
  assumptions, not measured physical lead times.
- Non-L products were excluded from the primary universe and were not mixed into
  these results.

**Decision:** do not execute Level B yet. If the study continues, treat fill
rate as one observable component and carry stockout days, stockout episodes,
duration, availability, replenishments and inventory as first-class outcomes.
A subsequent Level B requires an explicit review of this Gate 5A verdict.

## G. Reproducibility

Source code and tests:

- `validation/branch_replenishment/fill_rate_sanity_check.py`
- `validation/branch_replenishment/run_fill_rate_sanity_check_v1.py`
- `validation/branch_replenishment/test_fill_rate_sanity_check.py`
- `validation/branch_replenishment/backtest_engine_v1.py`

External evidence:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/branch_replenishment_fill_rate_sanity/v1_level_A/`

Artifacts include `current_fill_rate_audit.jsonl`, `comparability.jsonl`,
`observed_policy_metrics.jsonl`, `sensitivity_policy_metrics.jsonl`,
`sensitivity_comparison.jsonl`, `resource_metrics.jsonl` and `gate_result.json`.
