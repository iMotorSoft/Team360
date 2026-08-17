import base64
import copy
from dataclasses import FrozenInstanceError
from datetime import timezone
from email import message_from_bytes

import pytest

from modules.messaging.providers.gmail import GmailClient, normalize_gmail_message
from modules.messaging.providers.gmail.config import GmailConfigurationError


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _gmail_payload(*, subject: str | None = "Poste", body: str = "Necesito ayuda"):
    headers = [
        {"name": "From", "value": "Vecina <vecina@example.com>"},
        {"name": "To", "value": "Mesa <mesa@example.com>"},
        {"name": "Date", "value": "Tue, 12 Aug 2026 10:30:00 -0300"},
        {"name": "Message-ID", "value": "<external-1@example.com>"},
        {"name": "References", "value": "<root@example.com>"},
    ]
    if subject is not None:
        headers.append({"name": "Subject", "value": subject})
    return {
        "id": "gmail-message-1",
        "threadId": "gmail-thread-1",
        "internalDate": "1786530600000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encoded(body)}},
                {"mimeType": "text/html", "body": {"data": _encoded("<p>html</p>")}},
            ],
        },
    }


def test_normalizes_headers_plain_body_and_ids_without_mutation():
    raw = _gmail_payload(body="Poste en Olleros")
    original = copy.deepcopy(raw)

    message = normalize_gmail_message(raw)

    assert raw == original
    assert message.provider == "gmail"
    assert message.channel == "email"
    assert message.external_message_id == "gmail-message-1"
    assert message.external_thread_id == "gmail-thread-1"
    assert message.sender == "vecina@example.com"
    assert message.recipients == ("mesa@example.com",)
    assert message.subject == "Poste"
    assert message.text_body == "Poste en Olleros"
    assert message.received_at.tzinfo == timezone.utc
    assert message.metadata["rfc_message_id"] == "<external-1@example.com>"
    assert message.metadata["references"] == "<root@example.com>"


def test_missing_subject_is_normalized_to_empty_string():
    assert normalize_gmail_message(_gmail_payload(subject=None)).subject == ""


def test_automated_message_headers_are_exposed_in_metadata():
    headers = [
        {"name": "From", "value": "Tecnico <tech@alquimiablue.com>"},
        {"name": "To", "value": "Mesa <mesa@example.com>"},
        {"name": "Date", "value": "Tue, 12 Aug 2026 10:30:00 -0300"},
        {"name": "Message-ID", "value": "<auto-1@example.com>"},
        {"name": "In-Reply-To", "value": "<routing-1@example.com>"},
        {"name": "Auto-Submitted", "value": "auto-replied"},
        {"name": "Precedence", "value": "auto_reply"},
        {"name": "X-Autoreply", "value": "yes"},
        {"name": "X-Failed-Recipients", "value": "unknown@example.com"},
    ]
    payload = _gmail_payload(subject="Re: caso")
    payload["payload"]["headers"] = headers
    payload["payload"]["mimeType"] = "multipart/report"

    message = normalize_gmail_message(payload)

    assert message.metadata["auto_submitted"] == "auto-replied"
    assert message.metadata["precedence"] == "auto_reply"
    assert message.metadata["x_autoreply"] == "yes"
    assert message.metadata["x_failed_recipients"] == "unknown@example.com"
    assert message.metadata["content_type"] == "multipart/report"
    assert message.metadata["in_reply_to"] == "<routing-1@example.com>"

    from modules.flow.domain import is_automated_message

    assert is_automated_message(message) is True


def test_plain_reply_has_no_automated_markers():
    message = normalize_gmail_message(_gmail_payload(subject="Re: caso"))
    assert message.metadata["auto_submitted"] == ""
    assert message.metadata["precedence"] == ""
    assert message.metadata["content_type"] == "multipart/alternative"

    from modules.flow.domain import is_automated_message

    assert is_automated_message(message) is False


def test_normalized_message_is_immutable():
    message = normalize_gmail_message(_gmail_payload())
    with pytest.raises(FrozenInstanceError):
        message.subject = "changed"
    with pytest.raises(TypeError):
        message.metadata["new"] = "value"


class _Executable:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class _MessagesApi:
    def __init__(self, full_payload=None, list_response=None):
        self.full_payload = full_payload
        self.list_response = list_response or {"messages": []}
        self.get_kwargs = None
        self.list_kwargs = None
        self.send_kwargs = None

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return _Executable(self.full_payload)

    def send(self, **kwargs):
        self.send_kwargs = kwargs
        return _Executable({"id": "out-1", "threadId": "gmail-thread-1"})

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return _Executable(self.list_response)


class _UsersApi:
    def __init__(self, messages_api):
        self.messages_api = messages_api

    def messages(self):
        return self.messages_api


class _Service:
    def __init__(self, messages_api):
        self.messages_api = messages_api

    def users(self):
        return _UsersApi(self.messages_api)


def _client(messages_api):
    client = object.__new__(GmailClient)
    client.subject = "mesa@example.com"
    client._service = _Service(messages_api)
    return client


def test_get_inbound_message_requests_full_payload_without_modifying_labels():
    api = _MessagesApi(_gmail_payload())
    message = _client(api).get_inbound_message("gmail-message-1")
    assert message.external_message_id == "gmail-message-1"
    assert api.get_kwargs == {"userId": "me", "id": "gmail-message-1", "format": "full"}


def test_get_message_rfc_id_uses_normalized_real_header():
    api = _MessagesApi(_gmail_payload())
    assert _client(api).get_message_rfc_id("gmail-message-1") == (
        "<external-1@example.com>"
    )


def test_send_reply_preserves_gmail_thread_and_rfc_reply_headers():
    api = _MessagesApi()
    result = _client(api).send_reply(
        to="vecina@example.com",
        subject="Solicitud",
        body="¿Es correcto?",
        thread_id="gmail-thread-1",
        in_reply_to="<external-1@example.com>",
        references="<root@example.com>",
    )
    sent = api.send_kwargs["body"]
    decoded = base64.urlsafe_b64decode(sent["raw"])
    email = message_from_bytes(decoded)
    assert result.external_message_id == "out-1"
    assert sent["threadId"] == "gmail-thread-1"
    assert email["Subject"] == "Re: Solicitud"
    assert email["In-Reply-To"] == "<external-1@example.com>"
    assert email["References"] == "<root@example.com> <external-1@example.com>"


def test_send_message_preserves_explicit_rfc_message_id_for_safe_retry():
    api = _MessagesApi()
    message_id = _client(api).send_message(
        to="alumbrado.n1@alquimiablue.com",
        subject="Nueva solicitud",
        body="Caso controlado",
        rfc_message_id="<team360-flow-request-1@alquimiablue.com>",
    )
    decoded = base64.urlsafe_b64decode(api.send_kwargs["body"]["raw"])
    email = message_from_bytes(decoded)
    assert message_id == "out-1"
    assert email["Message-ID"] == "<team360-flow-request-1@alquimiablue.com>"


def test_find_sent_message_uses_exact_rfc_message_id_query():
    api = _MessagesApi(list_response={"messages": [{"id": "out-1"}]})
    found = _client(api).find_sent_message_by_rfc_message_id(
        "<team360-flow-request-1@alquimiablue.com>"
    )
    assert found == "out-1"
    assert api.list_kwargs == {
        "userId": "me",
        "maxResults": 2,
        "q": "in:sent rfc822msgid:<team360-flow-request-1@alquimiablue.com>",
    }


def test_find_sent_message_by_reference_uses_quoted_sent_query():
    api = _MessagesApi(list_response={"messages": [{"id": "out-1"}]})
    found = _client(api).find_sent_message_by_reference(
        "656977af-cc29-43d6-b78c-53464818f06a",
        to="alumbrado.n1@alquimiablue.com",
    )
    assert found == "out-1"
    assert api.list_kwargs == {
        "userId": "me",
        "maxResults": 2,
        "q": (
            "in:sent to:alumbrado.n1@alquimiablue.com "
            '"656977af-cc29-43d6-b78c-53464818f06a"'
        ),
    }


@pytest.mark.parametrize("value", ["bad-id", "<bad\nBcc:x@example.com>"])
def test_send_message_rejects_invalid_rfc_message_id(value):
    with pytest.raises(GmailConfigurationError, match="RFC Message-ID is invalid"):
        _client(_MessagesApi()).send_message(
            to="alumbrado.n1@alquimiablue.com",
            subject="Nueva solicitud",
            body="Caso controlado",
            rfc_message_id=value,
        )
