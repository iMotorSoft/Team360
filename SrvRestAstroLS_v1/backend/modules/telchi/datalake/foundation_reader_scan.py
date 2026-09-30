"""Reproducible static inventory for Telchi Foundation readers."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parents[1]

# The allowlist is intentionally narrow.  Investigation validation preserves
# historical SAP-vs-DuckLake evidence; the exact Data Lake files are producers,
# migration/maintenance tools, or validation runners rather than runtime
# consumers.
ALLOWLIST: tuple[dict[str, str], ...] = (
    {
        "path": "investigation/validation/**",
        "classification": "VALIDATION_ONLY",
        "reason": "reconciliation, forensics and historical evidence",
    },
    {
        "path": "datalake/tests/**",
        "classification": "TEST_ONLY",
        "reason": "isolated contract fixtures",
    },
    {
        "path": "datalake/comparison.py",
        "classification": "VALIDATION_ONLY",
        "reason": "bounded SAP-vs-DuckLake comparison helper",
    },
    {
        "path": "datalake/operational_validation.py",
        "classification": "VALIDATION_ONLY",
        "reason": "baseline validation and benchmark runner",
    },
    {
        "path": "datalake/oinm_pilot.py",
        "classification": "VALIDATION_ONLY",
        "reason": "historical OINM pilot evidence runner",
    },
    {
        "path": "datalake/create_initial.py",
        "classification": "LEGACY",
        "reason": "initial-build producer and migration tooling",
    },
    {
        "path": "datalake/update.py",
        "classification": "LEGACY",
        "reason": "manual producer; direct reads are pre/post-publication validation",
    },
    {
        "path": "datalake/receivables_collections_atomic.py",
        "classification": "VALIDATION_ONLY",
        "reason": "additive Atomic producer with direct post-capture lineage and gold validation; never a Foundation consumer",
    },
    {
        "path": "datalake/receivables_collections_business.py",
        "classification": "VALIDATION_ONLY",
        "reason": "additive deterministic Atomic-to-Business producer; never a Foundation consumer",
    },
    {
        "path": "datalake/receivables_collections_foundation.py",
        "classification": "SHARED_LIBRARY",
        "reason": "exact-id, snapshot-pinned Receivables Foundation publication and reader boundary",
    },
    {
        "path": "datalake/rebuild.py",
        "classification": "LEGACY",
        "reason": "maintenance/rebuild tooling",
    },
    {
        "path": "datalake/source_coverage.py",
        "classification": "LEGACY",
        "reason": "maintenance and coverage audit tooling",
    },
    {
        "path": "datalake/foundation_reader.py",
        "classification": "SHARED_LIBRARY",
        "reason": "canonical access boundary; all Atomic relations are snapshot-pinned",
    },
)

_PATTERN_DEFINITIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TELCHI_ATOMIC", re.compile(r"telchi\s*\.\s*atomic", re.IGNORECASE)),
    ("ATOMIC_SALES", re.compile(r"\batomic_sales\b", re.IGNORECASE)),
    ("ATOMIC_INVENTORY", re.compile(r"\batomic_inventory\b", re.IGNORECASE)),
    (
        "IMPLICIT_LATEST_PUBLICATION",
        re.compile(
            r"max\s*\([^\n]*publication_id|"
            r"order\s+by[^\n]*(?:created_at|published_at)[^\n]*desc[^\n]*limit\s+1|"
            r"latest[ _-]*(?:publication|snapshot|parquet)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class DirectReadFinding:
    path: str
    line: int
    pattern: str
    classification: str
    allowlisted: bool
    reason: str
    excerpt: str


def _classification(path: str) -> tuple[str, bool, str]:
    for item in ALLOWLIST:
        allowed = item["path"]
        if allowed.endswith("/**") and path.startswith(allowed[:-3] + "/"):
            return item["classification"], True, item["reason"]
        if path == allowed:
            return item["classification"], True, item["reason"]
    if path.startswith("investigation/"):
        return "INVESTIGATION_ONLY", False, "historical investigation outside explicit validation allowlist"
    if path.startswith("runtime/"):
        return "PRODUCTIVE", False, "Telchi runtime path"
    if path.startswith("datalake/"):
        return "SHARED_LIBRARY", False, "Data Lake shared library path"
    return "UNKNOWN", False, "unclassified Telchi path"


def scan_direct_reads(root: Path = MODULE_ROOT) -> dict[str, Any]:
    findings: list[DirectReadFinding] = []
    files: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".py", ".sql"} or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == "datalake/foundation_reader_scan.py":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        classification, allowlisted, reason = _classification(relative)
        for line_number, line in enumerate(lines, start=1):
            for name, pattern in _PATTERN_DEFINITIONS:
                if pattern.search(line):
                    findings.append(
                        DirectReadFinding(
                            path=relative,
                            line=line_number,
                            pattern=name,
                            classification=classification,
                            allowlisted=allowlisted,
                            reason=reason,
                            excerpt=line.strip()[:240],
                        )
                    )
                    files.add(relative)
    records = [asdict(item) for item in findings]
    productive = [item for item in records if item["classification"] == "PRODUCTIVE"]
    shared_unsafe = [
        item
        for item in records
        if item["classification"] == "SHARED_LIBRARY" and not item["allowlisted"]
    ]
    unclassified = [item for item in records if item["classification"] == "UNKNOWN"]
    return {
        "patterns": [name for name, _ in _PATTERN_DEFINITIONS],
        "findings": records,
        "reader_files": sorted(files),
        "DIRECT_READ_PATTERNS_FOUND": len(records),
        "DIRECT_READ_PATTERNS_PRODUCTIVE": len(productive),
        "DIRECT_READ_PATTERNS_ALLOWLISTED": sum(item["allowlisted"] for item in records),
        "UNCLASSIFIED_DIRECT_READS": len(unclassified),
        "PRODUCTIVE_DIRECT_ATOMIC_READERS": len({item["path"] for item in productive}),
        "SHARED_LIBRARY_DIRECT_ATOMIC_READERS": len({item["path"] for item in shared_unsafe}),
    }


def reader_inventory(root: Path = MODULE_ROOT) -> list[dict[str, Any]]:
    scan = scan_direct_reads(root)
    grouped: dict[str, dict[str, Any]] = {}
    for finding in scan["findings"]:
        entry = grouped.setdefault(
            finding["path"],
            {
                "path": finding["path"],
                "classification": finding["classification"],
                "allowlisted": finding["allowlisted"],
                "reason": finding["reason"],
                "patterns": set(),
                "occurrences": 0,
                "uses_canonical_foundation": finding["path"] == "datalake/foundation_reader.py",
            },
        )
        entry["patterns"].add(finding["pattern"])
        entry["occurrences"] += 1
    # The canonical entrypoint is a reader even if pattern wording changes.
    grouped.setdefault(
        "datalake/foundation_reader.py",
        {
            "path": "datalake/foundation_reader.py",
            "classification": "SHARED_LIBRARY",
            "allowlisted": True,
            "reason": "canonical snapshot-pinned Foundation access boundary",
            "patterns": set(),
            "occurrences": 0,
            "uses_canonical_foundation": True,
        },
    )
    result = []
    for item in grouped.values():
        result.append({**item, "patterns": sorted(item["patterns"])})
    return sorted(result, key=lambda item: item["path"])


__all__ = ["ALLOWLIST", "DirectReadFinding", "reader_inventory", "scan_direct_reads"]
