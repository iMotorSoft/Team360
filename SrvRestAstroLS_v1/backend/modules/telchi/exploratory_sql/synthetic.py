"""Sealed, tenant-local synthetic metadata and fixtures. No physical locations."""
from decimal import Decimal

from .contracts import (
    AuthorizedExecutionContext, Budget, CandidateRelation, Catalog, Column, LogicalTable,
)

PERMISSION = "telchi.exploratory.synthetic.read.v1"


def table(name, columns, grain, max_rows=100, constraints=()):
    return LogicalTable(name, tuple(Column(*c) for c in columns), PERMISSION,
                        grain, max_rows, constraints)


CATALOG = Catalog(
    dataset="synthetic_research_v1", organization="synthetic_org", workspace="synthetic_ws",
    publication="synthetic_publication_v1", snapshot="synthetic_snapshot_v1",
    tables=(
        table("invoices", (("id", "INTEGER"), ("amount", "DECIMAL(18,2)"),
              ("channel_id", "INTEGER", True), ("seller_id", "INTEGER"), ("series_id", "INTEGER")),
              ("id",), 3, ("Header amount is not line revenue; movement joins multiply headers.",)),
        table("lines", (("id", "INTEGER"), ("invoice_id", "INTEGER"),
              ("product_id", "INTEGER"), ("amount", "DECIMAL(18,2)")), ("id",), 4),
        table("products", (("id", "INTEGER"), ("name", "VARCHAR")), ("id",), 2),
        table("sellers", (("id", "INTEGER"), ("name", "VARCHAR")), ("id",), 2),
        table("channels", (("id", "INTEGER"), ("name", "VARCHAR")), ("id",), 2),
        table("series", (("id", "INTEGER"), ("name", "VARCHAR")), ("id",), 2),
        table("movements", (("id", "INTEGER"), ("invoice_id", "INTEGER", True),
              ("product_id", "INTEGER"), ("hour", "INTEGER"), ("quantity", "INTEGER")),
              ("id",), 8, ("invoice_id is investigative, not an accredited documentary join.",)),
    ),
    known_relations=(
        CandidateRelation("invoices", "id", "lines", "invoice_id"),
        CandidateRelation("lines", "product_id", "products", "id"),
        CandidateRelation("invoices", "seller_id", "sellers", "id"),
        CandidateRelation("invoices", "channel_id", "channels", "id"),
        CandidateRelation("invoices", "series_id", "series", "id"),
    ),
)

# All monetary values are Decimal, including deliberately unreconciled line totals.
ROWS = {
    "invoices": ((1, Decimal("100.00"), None, 1, 1),
                 (2, Decimal("80.00"), 1, 2, 1), (3, Decimal("20.00"), 2, 1, 2)),
    "lines": ((1, 1, 1, Decimal("40.00")), (2, 1, 2, Decimal("50.00")),
              (3, 2, 1, Decimal("80.00")), (4, 3, 2, Decimal("18.00"))),
    "products": ((1, "Synthetic A"), (2, "Synthetic B")),
    "sellers": ((1, "Synthetic seller A"), (2, "Synthetic seller B")),
    "channels": ((1, "Synthetic retail"), (2, "Synthetic wholesale")),
    "series": ((1, "Synthetic series A"), (2, "Synthetic series B")),
    # Five movements for invoice 1; duplicated candidate documentary key/hour;
    # invoice 3 has no movement; 999 is orphaned; NULL is deliberately present.
    "movements": ((1, 1, 1, 8, 1), (2, 1, 1, 8, 1), (3, 1, 2, 10, 2),
                  (4, 1, 2, 12, 1), (5, 1, 1, 15, 1), (6, 2, 1, 9, 1),
                  (7, 999, 1, 11, 1), (8, None, 2, 16, 1)),
}


def synthetic_context(*, investigation_id="synthetic-investigation-v1", budget=None):
    """Test-only trusted composition; no claims of real identity/RBAC integration."""
    return AuthorizedExecutionContext(
        identity="synthetic_researcher", organization=CATALOG.organization,
        workspace=CATALOG.workspace, environment="dev", permissions=frozenset({PERMISSION}),
        catalog=CATALOG, sources=tuple(t.name for t in CATALOG.tables),
        publication=CATALOG.publication, snapshot=CATALOG.snapshot,
        effective_budget=budget or Budget(), investigation_id=investigation_id,
    )
