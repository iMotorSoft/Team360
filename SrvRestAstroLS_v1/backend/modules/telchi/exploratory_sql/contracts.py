"""Immutable boundaries; only proposal is model-owned. No authority from free text."""
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from . import CONTRACT_VERSION


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"
    INVALID_QUERY = "INVALID_QUERY"


class RelationState(StrEnum):
    ACCREDITED = "ACCREDITED"
    INVESTIGATIVE = "INVESTIGATIVE"
    INSUFFICIENT = "INSUFFICIENT"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Budget:
    query_seconds: float = 2.0
    total_seconds: float = 10.0
    cpu_seconds: int = 1
    process_memory_bytes: int = 512 * 1024 * 1024
    threads: int = 1
    result_rows: int = 100
    result_bytes: int = 65536
    source_bytes: int = 65536
    queries: int = 5
    concurrency: int = 1
    max_join_pairs: int = 10000

    def __post_init__(self):
        # Conservative F1 ceilings, not arbitrary resource requests from Luna.
        ceilings = Budget.__dataclass_fields__
        for name in ceilings:
            value, cap = getattr(self, name), ceilings[name].default
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (name not in {"query_seconds", "total_seconds"} and type(value) is not int)
                    or not 0 < value <= cap):
                raise ValueError("invalid_budget")
        if self.query_seconds > self.total_seconds:
            raise ValueError("invalid_budget")

    def intersect(self, other: "Budget") -> "Budget":
        return Budget(**{k: min(getattr(self, k), getattr(other, k)) for k in self.__dataclass_fields__})


@dataclass(frozen=True)
class TypedParameter:
    name: str
    sql_type: str
    value: str | int | bool | Decimal | None


@dataclass(frozen=True)
class CandidateRelation:
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    rationale: str = ""


@dataclass(frozen=True)
class ExploratoryQueryProposal:
    sql: str
    objective: str
    justification: str
    requested_sources: tuple[str, ...]
    expected_grain: str
    expected_result: str
    candidate_relations: tuple[CandidateRelation, ...] = ()
    requested_budget: Budget = field(default_factory=Budget)
    parameters: tuple[TypedParameter, ...] = ()
    version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool = False


@dataclass(frozen=True)
class LogicalTable:
    name: str
    columns: tuple[Column, ...]
    permission: str
    grain: tuple[str, ...]
    max_rows: int
    semantic_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    dataset: str
    organization: str
    workspace: str
    publication: str
    snapshot: str
    tables: tuple[LogicalTable, ...]
    known_relations: tuple[CandidateRelation, ...]
    synthetic_only: bool = True


@dataclass(frozen=True)
class AuthorizedExecutionContext:
    """Constructed by trusted composition, never deserialized from LLM output.

    F1 only accepts the exact sealed fixture catalog. Future auth adapter must
    derive these fields from authenticated identity + operational RBAC.
    """
    identity: str
    organization: str
    workspace: str
    environment: str
    permissions: frozenset[str]
    catalog: Catalog
    sources: tuple[str, ...]
    publication: str
    snapshot: str
    effective_budget: Budget
    investigation_id: str
    version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class SecurityDecision:
    decision: Decision
    reason: str  # fixed safe code: never raw engine errors, SQL or identifiers
    query_id: str | None = None
    version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ResolvedRelation:
    left: tuple[str, str]
    right: tuple[str, str]
    state: RelationState


@dataclass(frozen=True)
class ValidatedExploratoryQuery:
    admitted_tree_json: str
    generated_sql: str  # newly emitted from allowlisted AST, not proposal text
    sources: tuple[str, ...]
    columns: tuple[tuple[str, str], ...]
    functions: tuple[str, ...]
    relations: tuple[ResolvedRelation, ...]
    parameters: tuple[TypedParameter, ...]
    limits: Budget
    required_permissions: tuple[str, ...]
    query_id: str
    context_digest: str
    declared_grain: str
    mandatory_checks: tuple[str, ...]
    version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ExploratoryQueryResult:
    query_id: str
    schema: tuple[Column, ...] = ()
    declared_grain: str = ""
    rows: tuple[tuple, ...] = ()
    aggregates: tuple[tuple[str, Decimal], ...] = ()
    returned_count: int = 0
    total_count: int | None = None
    truncated: bool = False
    elapsed_seconds: float = 0.0
    cpu_seconds: float | None = None
    peak_memory_bytes: int | None = None
    bytes_read: int | None = None  # None is not an enforced byte-scan limit
    source: str = "synthetic"
    publication: str = ""
    snapshot: str = ""
    evidence: tuple[str, ...] = ()
    status: str = "NOT_EXECUTED"
    limitations: tuple[str, ...] = ()
    version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class SQLColumnEvidence:
    """Server-owned identity and conservative AST lineage; aliases grant no authority."""
    column_id: str
    alias: str
    sql_type: str
    expression: str
    source_fields: tuple[str, ...]
    source_or_calculation: str
    metric: str | None
    metric_definition: str | None
    grain: str
    transformations: tuple[str, ...]
    unit: str | None
    currency: str | None
    classification: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SQLResultEvidence:
    result_id: str
    query_id: str
    execution_version: str
    dataset: str
    publication: str
    snapshot: str
    grain: str
    columns: tuple[SQLColumnEvidence, ...]
    row_ids: tuple[str, ...]
    relationships: tuple[ResolvedRelation, ...]
    temporal_scope: tuple[str, str]
    filter_expression: str
    group_expressions: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Verification:
    state: str
    checks: tuple[tuple[str, bool], ...]
    evidence: tuple[str, ...]
    limitations: tuple[str, ...] = ()


class ExecutionPort(Protocol):
    def execute(self, proposal: ExploratoryQueryProposal, context: AuthorizedExecutionContext,
                *, cancel=None) -> tuple[SecurityDecision, ExploratoryQueryResult]: ...


class VerificationPort(Protocol):
    def verify(self, query: ValidatedExploratoryQuery, result: ExploratoryQueryResult,
               context: AuthorizedExecutionContext) -> Verification: ...


# PLAN -> VALIDATE -> EXECUTE -> OBSERVE -> VERIFY -> REPLAN uses these values;
# no autonomous loop or operational integration is registered in F1.
