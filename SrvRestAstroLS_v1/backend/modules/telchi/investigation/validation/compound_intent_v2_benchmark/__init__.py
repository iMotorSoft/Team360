"""Compound Intent V2 benchmark preparation. Investigation-only package.

This package does NOT implement V2, does not import the operational runtime and
is never imported by production code. It provides a measurement contract, a gold
schema, a sealed holdout and a deterministic evaluator used to decide whether a
future passive V2 ledger may be implemented.
"""