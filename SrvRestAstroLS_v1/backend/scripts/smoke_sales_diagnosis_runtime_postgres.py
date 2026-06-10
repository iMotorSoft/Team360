"""Backend-only runtime integration smoke for sales diagnosis assistant.

Runs the real AssistantConversationRuntime with:
- real PostgreSQL 18 for ConversationState (via sync psycopg 3 bridge)
- fake RetrievalProvider (no Milvus)
- fake LLMProvider (no OpenAI/LiteLLM)
- real PromptPolicy and GuardrailPolicy
- fake MetricsRecorder and AuditTrail

Requires:
- TEAM360_DB_URL set (or resolved via globalVar.get_team360_db_url())
- migration 007 applied on the target database

Usage:
    TEAM360_DB_URL=postgresql://user:pass@host:port/team360 \\
        uv run python scripts/smoke_sales_diagnosis_runtime_postgres.py

No endpoint, no frontend, no real LLM, no real Milvus.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    ConversationStateSerializer,
    GuardrailPolicy,
    PromptPolicy,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    SalesDiagnosisRuntimeError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.providers import (
    AuditTrail,
    LLMProvider,
    MetricsRecorder,
    RetrievalProvider,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

CONTROLLED_CHUNKS = [
    RetrievedChunk(
        chunk_id="smoke_doc_1",
        document_id="smoke_doc_1",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/smoke/automation.md",
        title="Procesos automatizables",
        node_path="/ventas/automatizacion",
        score=0.92,
        content_preview="Los procesos de venta repetitivos son candidatos a automatizacion.",
        content="Los procesos de venta repetitivos, como la calificacion de leads "
        "y el envio de cotizaciones, son candidatos ideales para automatizacion.",
    ),
    RetrievedChunk(
        chunk_id="smoke_doc_2",
        document_id="smoke_doc_2",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/smoke/crm.md",
        title="Integracion CRM",
        node_path="/ventas/crm",
        score=0.85,
        content_preview="Team360 se integra con CRM via API REST.",
        content="Team360 se integra con sistemas CRM externos mediante API REST "
        "estandar para sincronizar oportunidades y contactos.",
    ),
]


class FakeRetrievalProvider:
    """Fake retrieval that returns controlled chunks, no Milvus."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks = chunks or list(CONTROLLED_CHUNKS)

    def retrieve(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        top_k: int = 5,
        top_n: int = 20,
    ) -> list[RetrievedChunk]:
        return self._chunks


class FakeLLMProvider:
    """Fake LLM with configurable response modes, no OpenAI.

    Modes:
        safe: returns a safe response that passes guardrails
        too_many_questions: triggers max_questions_exceeded guardrail
        unsafe_claim: triggers forbidden_claims guardrail (lead_capture ready)
        empty: triggers empty_response guardrail
    """

    SAFE_TEXT = (
        "Segun la documentacion disponible, Team360 puede ayudarte a "
        "automatizar procesos de venta repetitivos como la calificacion de "
        "leads. Te recomendamos comenzar con un diagnostico gratuito."
    )

    TOO_MANY_QUESTIONS_TEXT = (
        "Te hago algunas preguntas para entender mejor tu situacion: "
        "que canal usas? cual es tu volumen mensual de leads? "
        "cuantos vendedores tienes? que tecnologia usas actualmente? "
        "como capturas leads hoy? tienes equipo interno de tecnologia? "
        "cual es tu industria? en que region operas? "
        "hace cuanto tiempo buscas una solucion de automatizacion?"
    )

    UNSAFE_CLAIM_TEXT = (
        "Ya tenemos lead_capture listo y WhatsApp handoff "
        "automatico con SLA garantizado."
    )

    EMPTY_TEXT = "   "

    def __init__(self, mode: str = "safe") -> None:
        self._mode = mode

    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        if self._mode == "too_many_questions":
            return self.TOO_MANY_QUESTIONS_TEXT
        if self._mode == "unsafe_claim":
            return self.UNSAFE_CLAIM_TEXT
        if self._mode == "empty":
            return self.EMPTY_TEXT
        return self.SAFE_TEXT


class FakeMetricsRecorder:
    """In-memory metrics recorder."""

    def __init__(self) -> None:
        self.turns: list[tuple[AssistantTurnInput, Any]] = []

    def record_turn(self, input: AssistantTurnInput, output: Any) -> None:
        self.turns.append((input, output))


class FakeAuditTrail:
    """In-memory audit trail."""

    def __init__(self) -> None:
        self.records: list[tuple[AssistantTurnInput, Any]] = []

    def record(self, input: AssistantTurnInput, output: Any) -> None:
        self.records.append((input, output))


# ---------------------------------------------------------------------------
# Postgres state repository (sync bridge for smoke)
# ---------------------------------------------------------------------------

TABLE_NAME = "sales_diagnosis_conversation_states"


def _check_table_exists(dsn: str) -> bool:
    """Check if the conversation state table exists in PostgreSQL."""
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables "
                    "  WHERE table_schema = 'public' "
                    "  AND table_name = %(tbl)s"
                    ")",
                    {"tbl": TABLE_NAME},
                )
                row = cur.fetchone()
                return bool(row["exists"]) if row else False
    except Exception:
        return False


def _delete_smoke_session(dsn: str, session_id: str) -> None:
    """Delete a smoke test session from PostgreSQL."""
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {TABLE_NAME} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
            conn.commit()
    except Exception:
        pass


class _SmokePostgresStateRepository:
    """Sync StateRepository using psycopg 3 sync directly.

    This is a test-only bridge for the smoke script.
    It opens a new connection per operation (acceptable for smoke).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def load(self, session_id: str) -> ConversationState | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT state_jsonb FROM {TABLE_NAME} "
                    f"WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
                row = cur.fetchone()
                if row is None:
                    return None
                raw = row["state_jsonb"]
                if isinstance(raw, dict):
                    return ConversationStateSerializer.from_dict(raw)
                return ConversationStateSerializer.from_dict(json.loads(raw))

    def save(self, state: ConversationState) -> None:
        raw = ConversationStateSerializer.to_dict(state)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {TABLE_NAME} "
                    f"(session_id, assistant_instance_code, package_code, "
                    f"knowledge_scope_code, state_jsonb, "
                    f"created_at_utc, updated_at_utc) "
                    f"VALUES (%(session_id)s, %(assistant_instance_code)s, "
                    f"%(package_code)s, %(knowledge_scope_code)s, "
                    f"%(state_jsonb)s::jsonb, now(), now()) "
                    f"ON CONFLICT (session_id) DO UPDATE SET "
                    f"state_jsonb = EXCLUDED.state_jsonb, "
                    f"assistant_instance_code = EXCLUDED.assistant_instance_code, "
                    f"package_code = EXCLUDED.package_code, "
                    f"knowledge_scope_code = EXCLUDED.knowledge_scope_code, "
                    f"updated_at_utc = now()",
                    {
                        "session_id": state.session_id,
                        "assistant_instance_code": state.assistant_instance_code,
                        "package_code": state.package_code,
                        "knowledge_scope_code": state.knowledge_scope_code,
                        "state_jsonb": json.dumps(raw),
                    },
                )
            conn.commit()


# ---------------------------------------------------------------------------
# Smoke runner
# ---------------------------------------------------------------------------

UNIQUE_ID = str(uuid4())[:8]
SESSION_ID = f"smoke_sd_runtime_{UNIQUE_ID}"
CHECKS: list[str] = []
FAILURES: list[str] = []


def _check(name: str, passed: bool, detail: str = "") -> None:
    if passed:
        CHECKS.append(f"  PASS  {name}")
    else:
        FAILURES.append(f"  FAIL  {name}")
        CHECKS.append(f"  FAIL  {name}")
    if detail and not passed:
        CHECKS[-1] += f"  -- {detail}"


def _build_input(user_message: str) -> AssistantTurnInput:
    return AssistantTurnInput(
        session_id=SESSION_ID,
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        user_message=user_message,
    )


def _verify_db_state_jsonb(
    dsn: str, expected_turn_count: int | None = None
) -> dict[str, Any] | None:
    """Read state_jsonb directly from Postgres for verification."""
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT state_jsonb FROM {TABLE_NAME} "
                    f"WHERE session_id = %(sid)s",
                    {"sid": SESSION_ID},
                )
                row = cur.fetchone()
                if row is None:
                    return None
                raw = row["state_jsonb"]
                if isinstance(raw, dict):
                    return raw
                return json.loads(raw)
    except Exception:
        return None


def run_smoke(dsn: str) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    print("=== Sales Diagnosis Runtime Postgres Smoke ===")
    print(f"Session ID: {SESSION_ID}")
    print()

    # ------------------------------------------------------------------
    # 0. Verify table exists
    # ------------------------------------------------------------------
    if not _check_table_exists(dsn):
        print(
            f"ERROR: Table '{TABLE_NAME}' does not exist.\n"
            f"Apply migration 007:\n"
            f"  psql $TEAM360_DB_URL < db/migrations/007_sales_diagnosis_conversation_states.sql\n"
            f"Or use: uv run python scripts/smoke_sales_diagnosis_state_postgres.py",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Table exists. Connecting...")
    print()

    repo = _SmokePostgresStateRepository(dsn)
    trace_metrics = FakeMetricsRecorder()
    trace_audit = FakeAuditTrail()

    try:
        # ==============================================================
        # TURN 1 — safe LLM, first turn
        # ==============================================================
        print("--- Turn 1: safe LLM, first interaction ---")
        runtime = AssistantConversationRuntime(
            retrieval_provider=FakeRetrievalProvider(),
            llm_provider=FakeLLMProvider(mode="safe"),
            state_repository=repo,
            metrics_recorder=trace_metrics,
            audit_trail=trace_audit,
        )
        inp1 = _build_input("Quiero automatizar mi proceso de ventas comerciales.")
        out1 = runtime.handle_turn(inp1)

        _check("output has response_text", bool(out1.response_text))
        _check(
            "output has next_state",
            out1.next_state is not None,
        )
        _check(
            "turn_count == 1 after Turn 1",
            out1.next_state is not None and out1.next_state.turn_count == 1,
            f"got {out1.next_state.turn_count if out1.next_state else None}",
        )
        _check(
            "session_id matches",
            out1.next_state is not None
            and out1.next_state.session_id == SESSION_ID,
        )
        _check(
            "assistant_instance_code preserved",
            out1.next_state is not None
            and out1.next_state.assistant_instance_code
            == "team360_sales_diagnosis",
        )

        # Verify Postgres has the state
        db_state = _verify_db_state_jsonb(dsn, expected_turn_count=1)
        _check(
            "Postgres has state_jsonb after Turn 1",
            db_state is not None,
        )
        _check(
            "Postgres turn_count == 1",
            db_state is not None and db_state.get("turn_count") == 1,
            f"got {db_state.get('turn_count') if db_state else None}",
        )
        _check(
            "Postgres state_jsonb is an object",
            db_state is not None and isinstance(db_state, dict),
        )

        print()

        # ==============================================================
        # TURN 2 — safe LLM, same session (load from Postgres)
        # ==============================================================
        print("--- Turn 2: safe LLM, same session (load from Postgres) ---")
        inp2 = _build_input(
            "Tengo 50 leads por semana. Que puedo automatizar?"
        )
        out2 = runtime.handle_turn(inp2)

        _check("Turn 2 has next_state", out2.next_state is not None)
        _check(
            "Turn 2 turn_count == 2",
            out2.next_state is not None and out2.next_state.turn_count == 2,
            f"got {out2.next_state.turn_count if out2.next_state else None}",
        )
        _check(
            "Turn 2 session_id preserved",
            out2.next_state is not None
            and out2.next_state.session_id == SESSION_ID,
        )

        db_state_2 = _verify_db_state_jsonb(dsn)
        _check(
            "Postgres has state after Turn 2",
            db_state_2 is not None,
        )
        _check(
            "Postgres turn_count == 2",
            db_state_2 is not None and db_state_2.get("turn_count") == 2,
            f"got {db_state_2.get('turn_count') if db_state_2 else None}",
        )

        print()

        # ==============================================================
        # TURN 3 — soft guardrail: too many questions (fallback applied)
        # ==============================================================
        print("--- Turn 3: soft guardrail (too many questions) ---")
        runtime_guardrail = AssistantConversationRuntime(
            retrieval_provider=FakeRetrievalProvider(),
            llm_provider=FakeLLMProvider(mode="too_many_questions"),
            state_repository=repo,
            metrics_recorder=trace_metrics,
            audit_trail=trace_audit,
        )
        inp3 = _build_input("Quiero detalles especificos del servicio.")
        out3 = runtime_guardrail.handle_turn(inp3)

        _check("Turn 3 has next_state", out3.next_state is not None)
        _check(
            "Guardrail detected max_questions_exceeded",
            out3.guardrail_result.max_questions_exceeded,
        )
        _check(
            "Turn 3 turn_count == 3",
            out3.next_state is not None and out3.next_state.turn_count == 3,
            f"got {out3.next_state.turn_count if out3.next_state else None}",
        )
        _check(
            "Fallback response not empty",
            bool(out3.response_text),
        )

        db_state_3 = _verify_db_state_jsonb(dsn)
        _check(
            "Postgres has state after Turn 3 (guardrail fallback)",
            db_state_3 is not None,
        )
        _check(
            "Postgres turn_count == 3 after guardrail",
            db_state_3 is not None and db_state_3.get("turn_count") == 3,
            f"got {db_state_3.get('turn_count') if db_state_3 else None}",
        )

        print()

        # ==============================================================
        # TURN 4 — hard guardrail: unsafe claim raises UnsafeResponseError
        # ==============================================================
        print("--- Turn 4: hard guardrail (unsafe claim) ---")
        runtime_unsafe = AssistantConversationRuntime(
            retrieval_provider=FakeRetrievalProvider(),
            llm_provider=FakeLLMProvider(mode="unsafe_claim"),
            state_repository=repo,
            metrics_recorder=trace_metrics,
            audit_trail=trace_audit,
        )
        inp4 = _build_input("Que capacidades tienen disponibles?")
        try:
            runtime_unsafe.handle_turn(inp4)
            _check("Hard guardrail raised UnsafeResponseError", False)
        except UnsafeResponseError as exc:
            _check(
                "Hard guardrail raised UnsafeResponseError",
                True,
            )
            _check(
                "Error mentions forbidden claim",
                "lead_capture" in str(exc).lower()
                or "blocked" in str(exc).lower(),
            )

        print()

        # ==============================================================
        # Summary
        # ==============================================================
        print("--- Checks ---")
        for c in CHECKS:
            print(c)
        print()

        total = len(CHECKS)
        passed = total - len(FAILURES)
        print(f"Result: {passed}/{total} passed")

        if FAILURES:
            print(f"Failures: {len(FAILURES)}")
            for f in FAILURES:
                print(f)
            sys.exit(1)

        print()
        print("=== SMOKE PASSED ===")

    finally:
        _delete_smoke_session(dsn, SESSION_ID)
        print(f"Cleanup: session {SESSION_ID} deleted.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    from globalVar import get_team360_db_url

    dsn = get_team360_db_url()
    if not dsn:
        print(
            "ERROR: TEAM360_DB_URL not set.\n"
            "Set the environment variable or configure globalVar.py.\n"
            "Example:\n"
            "  TEAM360_DB_URL=postgresql://user:pass@localhost:5432/team360 \\\n"
            "    uv run python scripts/smoke_sales_diagnosis_runtime_postgres.py",
            file=sys.stderr,
        )
        sys.exit(1)

    run_smoke(dsn)
    sys.exit(0)


if __name__ == "__main__":
    main()
