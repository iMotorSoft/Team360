"""PHASE 9 — Application / channel origin classifier (pure logic).

Classifies SAP document origin using explicit UDF markers observed in the
TELCHI schema (EXACT signals) plus heuristic fallbacks.

Classification inputs (per document):
  - U_ORIGIN          : 'SAP' | 'DMS' (explicit addon marker)
  - U_SO1_01RETAILONE : 'Y' | 'N' (explicit Retail One marker)
  - Series            : numeric series id (DMSxx-xx in NNM1)
  - SeriesName        : name from NNM1
  - UserSign          : technical user id (soluone, dms, manager...)

Rules (validated against real OINV distribution 2026-08-26):
  1. U_ORIGIN='DMS' -> DMS (EXACT)
  2. U_ORIGIN='SAP' AND U_SO1_01RETAILONE='Y' -> RETAIL_ONE (EXACT)
  3. U_ORIGIN='SAP' AND U_SO1_01RETAILONE='N' -> SAP_DIRECT (EXACT)
  4. SeriesName LIKE 'DMS%' -> DMS (STRONG)
  5. technical user dms -> DMS (HEURISTIC)
  6. technical user soluone -> RETAIL_ONE (HEURISTIC)
  else UNKNOWN
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Origin(str, Enum):
    SAP_DIRECT = "SAP_DIRECT"
    RETAIL_ONE = "RETAIL_ONE"
    DMS = "DMS"
    INTEGRATION = "INTEGRATION"
    BATCH = "BATCH"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    EXACT = "EXACT"
    STRONG = "STRONG"
    HEURISTIC = "HEURISTIC"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OriginClassification:
    application_origin: Origin
    confidence: Confidence
    signals: tuple[str, ...]
    reason: str = ""


# Technical integration user codes (from OUSR)
TECHNICAL_USERS = {
    "dms": Origin.DMS,
    "soluone": Origin.RETAIL_ONE,
    "alianza": Origin.INTEGRATION,
    "B1i": Origin.INTEGRATION,
    "EDsUser": Origin.INTEGRATION,
    "Workflow": Origin.INTEGRATION,
    "AlertSvc": Origin.INTEGRATION,
}


def classify_origin(
    u_origin: str | None,
    retail_one: str | None,
    series: str | None = None,
    series_name: str | None = None,
    user_code: str | None = None,
) -> OriginClassification:
    """Classify a document's application origin.

    Order matters: explicit markers first, then heuristics.
    Never returns a heuristic as EXACT.
    """
    signals: list[str] = []

    u_origin_norm = (u_origin or "").upper().strip()
    retail_norm = (retail_one or "").upper().strip()
    series_name_norm = (series_name or "").upper().strip()
    user_norm = (user_code or "").upper().strip()

    # 1. Explicit U_ORIGIN marker
    if u_origin_norm == "DMS":
        return OriginClassification(
            Origin.DMS, Confidence.EXACT,
            ("U_ORIGIN=DMS",), "explicit addon origin marker")

    if u_origin_norm == "SAP":
        if retail_norm == "Y":
            return OriginClassification(
                Origin.RETAIL_ONE, Confidence.EXACT,
                ("U_ORIGIN=SAP", "U_SO1_01RETAILONE=Y"),
                "explicit Retail One marker")
        if retail_norm == "N":
            return OriginClassification(
                Origin.SAP_DIRECT, Confidence.EXACT,
                ("U_ORIGIN=SAP", "U_SO1_01RETAILONE=N"),
                "explicit non-Retail-One SAP marker")

    # 2. Series name heuristic
    if series_name_norm.startswith("DMS"):
        return OriginClassification(
            Origin.DMS, Confidence.STRONG,
            ("SeriesName=DMS*",), "DMS numbering series")

    # 3. Technical user heuristic
    tech_norm = {k.upper(): v for k, v in TECHNICAL_USERS.items()}
    if user_norm in tech_norm:
        origin = tech_norm[user_norm]
        return OriginClassification(
            origin, Confidence.HEURISTIC,
            (f"technical_user={user_norm}",),
            "technical integration user")

    return OriginClassification(Origin.UNKNOWN, Confidence.UNKNOWN, (), "no marker")


def classify_origin_basic(u_origin: str | None, retail_one: str | None) -> OriginClassification:
    """Minimal classifier using only the two explicit UDFs."""
    return classify_origin(u_origin, retail_one, None, None, None)
