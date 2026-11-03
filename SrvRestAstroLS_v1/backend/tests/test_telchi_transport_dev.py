"""Explicit operator send authorization remains distinct from DEV credentials."""
import pytest
from modules.telchi.assistant.transport_dev import create_app


@pytest.mark.parametrize('environment',['production','prod','staging',''])
def test_v1_composition_never_runs_outside_explicit_dev(monkeypatch, environment):
    monkeypatch.setenv('TEAM360_ENV',environment)
    with pytest.raises(ValueError,match='DEV transport composition required'):
        create_app()


def test_activating_revision_does_not_authorize_sending(monkeypatch):
    from modules.messaging import transport_runtime
    monkeypatch.setenv('TEAM360_ENV','dev')
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG','/synthetic/private.json')
    monkeypatch.delenv('TEAM360_TELCHI_V1_SEND_AUTHORIZED',raising=False)
    monkeypatch.setattr(transport_runtime,'private_document',lambda _: {'admission_open':True})
    with pytest.raises(ValueError,match='Explicit WhatsApp test activation'):
        create_app()
