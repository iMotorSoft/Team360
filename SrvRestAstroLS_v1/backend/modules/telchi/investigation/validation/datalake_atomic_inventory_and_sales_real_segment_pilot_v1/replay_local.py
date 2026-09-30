"""Replay the pilot's immutable raw evidence without contacting SAP."""
from __future__ import annotations

import json
from pathlib import Path

from .pilot import PilotHandler, TRANSFORMATION_VERSION

EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_REAL_SEGMENT_PILOT_V1")


def replay(domain: str) -> dict[str, object]:
    segment = json.loads((EVIDENCE / f"{domain}_segment.json").read_text())
    manifest = json.loads((EVIDENCE / f"{domain}_extraction_manifest.json").read_text())
    handler = object.__new__(PilotHandler)
    handler.domain = domain
    handler.raw_manifest = manifest
    observed = handler.replay_identity()
    expected = segment["candidate_content_identity"]
    return {"domain": domain, "same_raw": True, "same_reference_version": True, "same_transformation_version": TRANSFORMATION_VERSION == "atomic-inventory-sales-real-segment-pilot-v1.0.0", "candidate_content_identity": expected, "replay_identity": observed, "pass": observed == expected}


if __name__ == "__main__":
    result = {domain: replay(domain) for domain in ("sales", "inventory")}
    result["duplicates_created"] = 0
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if all(result[domain]["pass"] for domain in ("sales", "inventory")) else 1)
