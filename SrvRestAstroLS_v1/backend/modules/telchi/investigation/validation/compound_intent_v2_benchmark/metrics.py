"""Stable measurement contract for intent comparison.

The published V1 evaluation reported two exactness predicates that disagreed:

* ``run.summarize`` counted 12 candidate-exact LlmFit turns. It filters candidate
  atoms to the field families where gold has at least one atom, then compares for
  equality. Candidate facets added in gold-empty families are invisible.
* ``evaluate.raw_score`` / ``evaluate.replay`` counted 10. It restricts candidate
  atoms to the top-level keys present in gold, then compares for equality. Added
  facets in empty-but-present fields (scope, sort, ...) are visible.

Both are legitimate answers to different questions, so the benchmark reports them
as separate named predicates and never as one ambiguous "exact" number:

``LEGACY_RECALL_FAMILY_EXACT``  -> reproduces the published 12
``LEGACY_GOLD_KEYS_EXACT``      -> reproduces the published 10
``RECALL_COMPLETE``             -> candidate contains every gold atom
``SET_EXACT``                   -> no missing and no added atom (full universe)

``SET_EXACT`` is the primary regression predicate because a passive ledger must
not fabricate requirements. ``RECALL_COMPLETE`` is reported separately because
losing a requirement and inventing one are different failure modes.
"""

from .canonicalize import atoms, canonicalize

# Top-level intent field universe. Scoring over the full universe makes added
# facets in any family visible, including families absent from a legacy gold.
INTENT_FIELDS = (
    'business_domain', 'metrics', 'dimensions', 'filters', 'scope', 'time',
    'comparison', 'reference', 'limit', 'sort', 'measure_context', 'segments',
    'granularities', 'geographies', 'relations', 'claims', 'unresolved_requirements',
)


def _restrict_keys(value, keys):
    return {k: v for k, v in value.items() if k in keys}


def _family_roots(gold_atoms):
    """Top-level field names that own at least one gold atom."""
    return {path.split('/')[1] for path, _ in gold_atoms}


def recall_family_exact(gold, candidate):
    """Reproduce ``run.summarize`` exactness (published 12)."""
    g = atoms(gold)
    if not g:
        return True
    filtered = {(p, v) for p, v in atoms(candidate) if p.split('/')[1] in _family_roots(g)}
    return g == filtered


def gold_keys_exact(gold, candidate):
    """Reproduce ``evaluate.raw_score`` exactness (published 10)."""
    g = atoms(gold)
    c = atoms(_restrict_keys(candidate, set(gold)))
    return g == c


def score(gold, candidate, canonical=True, universe=INTENT_FIELDS):
    """Layered score of one intent against gold.

    ``canonical=False`` reports raw representation differences; ``canonical=True``
    applies only the declared equivalences. The full field universe is always
    used for missing/added so fabricated facets are never hidden.
    """
    gold_proj = canonicalize(gold) if canonical else gold
    cand_proj = canonicalize(candidate) if canonical else candidate
    g = atoms({k: v for k, v in gold_proj.items() if k in universe})
    c = atoms({k: v for k, v in cand_proj.items() if k in universe})
    missing = g - c
    added = c - g
    return {
        'expected': len(g),
        'predicted': len(c),
        'preserved': len(g & c),
        'missing': sorted(missing),
        'added': sorted(added),
        'recall_complete': not missing,
        'set_exact': not missing and not added,
        'recall_family_exact': recall_family_exact(gold_proj, cand_proj),
        'gold_keys_exact': gold_keys_exact(gold_proj, cand_proj),
        'canonical': canonical,
    }


def representation_is_sole_cause(gold, candidate):
    """True iff candidate is set-exact after canonicalization but not before."""
    raw = score(gold, candidate, canonical=False)
    canon = score(gold, candidate, canonical=True)
    return (not raw['set_exact']) and canon['set_exact']


def aggregate(scores):
    """Aggregate a list of per-turn layered scores into benchmark counts."""
    n = len(scores)
    return {
        'turns': n,
        'recall_complete_turns': sum(s['recall_complete'] for s in scores),
        'set_exact_turns': sum(s['set_exact'] for s in scores),
        'legacy_recall_family_exact_turns': sum(s['recall_family_exact'] for s in scores),
        'legacy_gold_keys_exact_turns': sum(s['gold_keys_exact'] for s in scores),
        'preserved_atoms': sum(s['preserved'] for s in scores),
        'expected_atoms': sum(s['expected'] for s in scores),
        'predicted_atoms': sum(s['predicted'] for s in scores),
    }