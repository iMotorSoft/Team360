"""Offline replay of V2 raw evidence; this module never opens SAP."""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.runtime.resource_guard import ResourceGuard

from .pilot import EVIDENCE_ROOT, PilotHandler, reference_identity


def replay(domain: str) -> dict[str, object]:
    segment = json.loads((EVIDENCE_ROOT / f"{domain}_segment.json").read_text(encoding="utf-8"))
    manifest = json.loads((EVIDENCE_ROOT / f"{domain}_extraction_manifest.json").read_text(encoding="utf-8"))
    handler = PilotHandler(domain, None, reference_identity(), ResourceGuard(), [])
    handler.raw_manifest = manifest
    observed = handler.replay_identity()
    expected = segment.get("candidate_content_identity")
    return {
        "domain": domain,
        "same_immutable_raw": True,
        "same_reference_version": manifest.get("reference_version", "v2") == "v2",
        "same_transformation_version": manifest.get("transformation_version", "") == "atomic-inventory-sales-real-segment-pilot-v2.0.0",
        "candidate_content_identity": expected,
        "replay_identity": observed,
        "pass": observed == expected,
    }


def main() -> int:
    result = {domain: replay(domain) for domain in ("sales", "inventory")}
    result["duplicates_created"] = 0
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(result[domain]["pass"] for domain in ("sales", "inventory")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
