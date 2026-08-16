from modules.flow.domain import (
    ApprovalDecision,
    approval_reason_after_command,
    approval_rfc_message_id,
    approval_sender_authorized,
    approval_token_for,
    approval_token_from_subject,
    deterministic_approval_decision,
)


def test_approval_token_is_deterministic_16_hex_letter_first():
    first = approval_token_for("gmail", "msg-abc")
    second = approval_token_for("gmail", "msg-abc")
    assert first == second
    assert len(first) == 16
    assert all(c in "0123456789abcdef" for c in first)
    # routing-key-shaped: keeps the operational correlator from stealing the
    # supervisor decision via the single-routing subject fallback.
    assert first[0] in "abcdef"


def test_approval_token_differs_per_source_message():
    assert approval_token_for("gmail", "msg-abc") != approval_token_for(
        "gmail", "msg-def"
    )


def test_approval_rfc_message_id_contains_token():
    token = approval_token_for("gmail", "msg-abc")
    assert approval_rfc_message_id(token) == (
        f"<team360-flow-closure-{token}@alquimiablue.com>"
    )


def test_approval_token_from_subject_extracts_hex_token():
    subject = "[Team360 Flow][CIERRE][R:a2454e105606dbe1][uuid] Aprobación de cierre"
    assert approval_token_from_subject(subject) == "a2454e105606dbe1"


def test_approval_token_from_subject_ignores_routing_keys():
    subject = "[Team360 Flow][R:alumbrado_level_2][uuid]"
    assert approval_token_from_subject(subject) is None


def test_deterministic_approve_commands():
    for text in ("APROBAR", "aprobado", "AUTORIZO CIERRE", "autorizar"):
        assert deterministic_approval_decision(text) == ApprovalDecision.APPROVE


def test_deterministic_reject_commands():
    for text in ("RECHAZAR", "rechazado", "NO APROBAR", "rechazo"):
        assert deterministic_approval_decision(text) == ApprovalDecision.REJECT


def test_deterministic_decision_returns_none_for_ambiguous():
    assert deterministic_approval_decision("Ok, lo veo.") is None
    assert deterministic_approval_decision("gracias") is None
    assert deterministic_approval_decision("") is None


def test_reject_reason_after_command():
    assert (
        approval_reason_after_command("RECHAZAR: falta verificar la luminaria")
        == "falta verificar la luminaria"
    )


def test_reject_reason_empty_without_colon():
    assert approval_reason_after_command("APROBAR") == ""


def test_approval_sender_authorized_accepts_internal_domain():
    assert approval_sender_authorized(
        "mario.rojas@alquimiablue.com",
        "alumbrado.n2@alquimiablue.com",
        "vecino@example.com",
    ) is True


def test_approval_sender_authorized_rejects_external_citizen():
    assert approval_sender_authorized(
        "vecino@example.com", "alumbrado.n2@alquimiablue.com"
    ) is False


def test_approval_sender_authorized_rejects_citizen_on_same_domain():
    assert approval_sender_authorized(
        "vecino@alquimiablue.com",
        "alumbrado.n2@alquimiablue.com",
        "vecino@alquimiablue.com",
    ) is False


def test_approval_sender_authorized_rejects_empty_sender():
    assert approval_sender_authorized("", "alumbrado.n2@alquimiablue.com") is False
