"""Independent Decimal checks. Technical SQL validity never accredits revenue."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from .contracts import RelationState, Verification
from .synthetic import CATALOG, ROWS
from .validator import authorize, context_digest


def decimal_sum(values):
    values = tuple(values)
    if not all(isinstance(v, Decimal) and v.is_finite() for v in values):
        raise ValueError("decimal_required")
    return sum(values, Decimal("0"))


def sum_matches(values, claimed):
    return isinstance(claimed, Decimal) and claimed.is_finite() and decimal_sum(values) == claimed


def count_matches(rows, claimed):
    return type(claimed) is int and len(rows) == claimed


def percentage_matches(numerator, denominator, claimed, *, tolerance=Decimal("0.01")):
    for value in (numerator, denominator, claimed, tolerance):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("decimal_required")
    if denominator <= 0 or tolerance < 0:
        return False
    return abs(numerator * 100 / denominator - claimed) <= tolerance


def partitions_reconcile(expected_keys, partitions):
    """Multiset coverage AND disjointness; matching only totals is insufficient."""
    expected = Counter(expected_keys)
    seen = Counter(key for part in partitions for key in part)
    return expected == seen and all(n == 1 for n in expected.values())


@dataclass(frozen=True)
class RelationshipProfile:
    state: RelationState
    cardinality: str
    left_rows: int
    right_rows: int
    left_unique: bool
    right_unique: bool
    left_null_keys: int
    right_null_keys: int
    right_orphans: int
    matched_left: int
    unmatched_left: int
    matched_pairs: int
    left_join_rows: int
    coverage_percent: Decimal
    multiplication: bool
    baseline_total: Decimal | None
    left_join_total: Decimal | None
    totals_stable: bool | None


def profile_synthetic_relation(left_table, left_key, right_table, right_key, *, amount_column=None):
    """Trusted fixture profiling, NOT execution of proposed SQL or accreditation.

    Candidate relations remain INVESTIGATIVE even if all observed keys match.
    The function accepts logical names only and never opens a physical source.
    """
    tables = {t.name: t for t in CATALOG.tables}
    if left_table not in tables or right_table not in tables:
        raise ValueError("unknown_logical_source")
    left_cols = [c.name for c in tables[left_table].columns]
    right_cols = [c.name for c in tables[right_table].columns]
    if left_key not in left_cols or right_key not in right_cols:
        raise ValueError("unknown_logical_column")
    li, ri = left_cols.index(left_key), right_cols.index(right_key)
    left, right = ROWS[left_table], ROWS[right_table]
    lc, rc = Counter(r[li] for r in left), Counter(r[ri] for r in right)
    left_null, right_null = lc.pop(None, 0), rc.pop(None, 0)
    lu, ru = all(v == 1 for v in lc.values()), all(v == 1 for v in rc.values())
    cardinality = ("ONE" if lu else "MANY") + "_TO_" + ("ONE" if ru else "MANY")
    matched = sum(n for k, n in lc.items() if k in rc)
    pairs = sum(n * rc[k] for k, n in lc.items())
    unmatched = len(left) - matched
    baseline, joined, stable = None, None, None
    if amount_column is not None:
        if amount_column not in left_cols:
            raise ValueError("unknown_amount_column")
        ai = left_cols.index(amount_column)
        baseline = decimal_sum([row[ai] for row in left])
        joined = decimal_sum([row[ai] * max(1, rc.get(row[li], 0)) for row in left])
        stable = baseline == joined
    return RelationshipProfile(
        RelationState.INVESTIGATIVE, cardinality, len(left), len(right), lu, ru,
        left_null, right_null, sum(n for k, n in rc.items() if k not in lc),
        matched, unmatched, pairs, pairs + unmatched,
        Decimal(matched) * 100 / Decimal(len(left)) if left else Decimal("0"),
        pairs + unmatched > len(left), baseline, joined, stable,
    )


class IndependentVerifier:
    """Required policy cannot be weakened by proposal or result text.

    F1's blocked executor cannot issue authenticated execution evidence. Even
    plausible rows/sums cannot be presented as accredited business conclusions.
    """
    REQUIRED = ("integrity", "provenance", "grain", "counts", "sums", "percentages",
                "duplicates", "cardinality", "partitions")

    def verify(self, query, result, context):
        try:
            authorize(context)
            provenance = (query.context_digest == context_digest(context)
                          and query.query_id == result.query_id
                          and result.publication == context.publication
                          and result.snapshot == context.snapshot
                          and result.source == "synthetic")
        except Exception:
            provenance = False
        checks = dict.fromkeys(self.REQUIRED, False)
        checks["integrity"] = (result.status == "COMPLETED" and not result.truncated
                               and result.returned_count == len(result.rows)
                               and all(len(row) == len(result.schema) for row in result.rows))
        checks["provenance"] = provenance
        checks["grain"] = (result.declared_grain == query.declared_grain and bool(result.declared_grain))
        limits = ["execution_evidence_not_accredited", "business_claim_unverified"]
        if query.relations and ("invoices", "amount") in query.columns:
            checks["grain"] = False
            limits.append("header_amount_join_multiplication_risk")
        if tuple(query.mandatory_checks) != self.REQUIRED:
            limits.append("mandatory_verifications_missing")
        return Verification("UNVERIFIED", tuple(checks.items()), (query.query_id,), tuple(limits))

    def verify_synthetic_invoice_total(self, claimed, *, invoice_ids=None):
        """Independent controlled reference, never trusting model-declared totals.

        This fixture-only calculation proves the verifier catches fanout; it
        does not certify arbitrary SQL filter/grain equivalence.
        """
        if invoice_ids is not None and not isinstance(invoice_ids, frozenset):
            raise ValueError("trusted_scope_required")
        values = [r[1] for r in ROWS["invoices"] if invoice_ids is None or r[0] in invoice_ids]
        okay = sum_matches(values, claimed)
        return Verification("REFERENCE_MATCH" if okay else "REJECTED",
                            (("independent_decimal_sum", okay),),
                            (CATALOG.publication, CATALOG.snapshot),
                            ("synthetic_reference_only_not_sql_accreditation",))
