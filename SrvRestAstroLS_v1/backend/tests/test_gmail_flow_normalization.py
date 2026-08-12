import base64
import copy
from dataclasses import FrozenInstanceError
from datetime import timezone
from email import message_from_bytes

import pytest

from modules.messaging.providers.gmail import GmailClient, normalize_gmail_message


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
    def __init__(self, full_payload=None):
        self.full_payload = full_payload
        self.get_kwargs = None
        self.send_kwargs = None

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return _Executable(self.full_payload)

    def send(self, **kwargs):
        self.send_kwargs = kwargs
        return _Executable({"id": "out-1", "threadId": "gmail-thread-1"})


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
