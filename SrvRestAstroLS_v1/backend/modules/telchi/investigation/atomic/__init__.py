"""TELCHI Atomic Data Lake — logical model layer.

Storage-independent contracts and pure semantic logic.

Design contract:
- Never depend on storage (parquet/postgres) — logical model only.
- Every SAP-derived field carries a confidence: CONFIRMED | LEGACY_REFERENCED | CANDIDATE.
- Every cross-system relation declares a match_method and confidence.
"""