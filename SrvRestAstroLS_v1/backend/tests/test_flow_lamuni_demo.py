"""Team360 Flow LaMuni end-to-end demo coverage.

The demo harness drives the real Flow services over real PostgreSQL with
deterministic external transport. The full scenario and repeatability tests are
gated behind ``TEAM360_FLOW_LAMUNI_DEMO_TEST=1`` following the repository
convention for real-PostgreSQL suites; the transport contract tests always run.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.demo.run import cleanup_demo_cases, run_demo
from modules.flow.demo.transport import (
    DemoApprovalInterpreter,
    DemoIntakeInterpreter,
    DemoOperationalInterpreter,
    DemoReplySender,
    DemoRoutingSender,
)
from modules.flow.domain import (
    ApprovalDecision,
    ApprovalDecisionResult,
    OperationalAction,
)
from modules.messaging.domain import InboundMessage

REQUIRE = "requires TEAM360_FLOW_LAMUNI_DEMO_TEST=1"


def _citizen_message(thread_id: str, message_id: str, body: str) -> InboundMessage:
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender="vecino@example.com",
        recipients=("mesaentrada@alquimiablue.com",),
        subject="Solicitud de alumbrado publico",
        text_body=body,
        received_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        metadata={"rfc_message_id": f"<{message_id}@example.com>"},
    )


def test_demo_intake_interpreter_classifies_alumbrado():
    interpreter = DemoIntakeInterpreter("luminaria apagada", "calle 1", "LAMUNI-DEMO-TEST")
    message = _citizen_message("thread-1", "m1", "luminaria apagada")
    initial = interpreter.interpret_initial(message)
    assert len(initial.requests) == 1
    assert initial.requests[0].tentative_category == "alumbrado"
    assert "LAMUNI-DEMO-TEST" in initial.requests[0].description

    reply = interpreter.interpret_reply(message, initial.requests)
    assert reply.action == "confirm_all"


def test_demo_operational_and_approval_interpreters_are_deterministic():
    operational = DemoOperationalInterpreter()
    parsed = operational.interpret(
        _citizen_message("thread-2", "m2", "Reparada.")
    )
    assert parsed.action == OperationalAction.RESOLUTION_PROPOSED

    approval = DemoApprovalInterpreter()
    result = approval.interpret("APROBAR", correlation_id="m2")
    assert result == ApprovalDecisionResult(ApprovalDecision.APPROVE, "")


def test_demo_senders_are_deterministic_transports():
    routing = DemoRoutingSender()
    assert routing.get_message_rfc_id("x") == "<observed-x@mail.gmail.com>"
    assert routing.find_sent_message_by_rfc_message_id("<a>") is None
    assert routing.find_sent_message_by_reference("r") is None
    sent_id = routing.send_message(to="a@b.c", subject="s", body="b")
    assert "-gmail-" in sent_id

    reply = DemoReplySender()
    receipt = reply.send_reply(
        to="c@d.e", subject="s", body="b", thread_id="t"
    )
    assert "-out-" in receipt.external_message_id


@ pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_LAMUNI_DEMO_TEST") != "1",
    reason=REQUIRE,
)
def test_lamuni_demo_full_scenario_end_to_end():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            report = await run_demo(pool, settings)

            assert report.sector_id == "alumbrado"
            assert report.classification == "alumbrado"
            assert report.final_status == "RESOLVED"
            assert report.resolution_status == "APPROVED"
            assert report.approval_status == "APPROVED"
            assert report.n1_sla_status == "BREACHED"
            assert report.escalation_id
            assert report.n2_routing_id
            assert report.n2_destination != report.n1_destination
            assert report.audit_id
            assert report.audit_schema_version == 1
            assert report.audit_hash
            assert len(report.audit_hash) == 16
            assert report.directorio_visible is True
            assert report.directorio_data_source == "AUDIT_SNAPSHOT"
            assert report.directorio_status_fact == "closed"
            assert report.configuration.get("sector_id") == "alumbrado"
            assert report.configuration.get("closure_approval_level") == 2
        finally:
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())


@ pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_LAMUNI_DEMO_TEST") != "1",
    reason=REQUIRE,
)
def test_lamuni_demo_audit_snapshot_is_immutable():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            report = await run_demo(pool, settings)
            second = await run_demo(pool, settings)

            assert report.request_id != second.request_id
            assert report.marker != second.marker
            assert report.audit_id != second.audit_id
        finally:
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())
