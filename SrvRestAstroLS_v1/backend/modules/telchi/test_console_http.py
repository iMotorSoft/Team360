"""HTTP contract tests only; not an authenticated enterprise E2E claim."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from modules.console.auth import verify_console_access_token
from .routes import ROUTE_HANDLERS
from .exploratory_sql.test_console_bridge import PAIR, token
from .exploratory_sql.authorized_foundation import EffectiveScope, SourcePolicy
from .exploratory_sql.validator import Rejected
from .exploratory_sql.contracts import Decision


class Service:
    keys = {PAIR.key_id: PAIR.public_pem}
    issuer = 'fixture'
    policies = (SourcePolicy('sales_line', 'existing.sales.read', 'org1', 'w1', whole_dataset=True),)
    denied = False
    calls = []

    async def resolve(self, value):
        principal = verify_console_access_token(value, public_keys_by_id=self.keys, issuer=self.issuer)
        if principal.user_id != 'u1':
            raise Rejected('denied', Decision.DENY)
        return EffectiveScope('u1', 'org1', 'w1',
            frozenset() if self.denied else frozenset({'existing.sales.read'}))

    async def ask(self, value, question, save, *, progress, conversation_id):
        self.calls.append((question, conversation_id))
        progress('Investigando: consulta 1')
        return dict(status='VERIFIED_WITH_LIMITATIONS', business_answer='Respuesta acreditada',
            publication='foundation_test', snapshot='1', question_coverage='PARTIAL',
            model_answer='PRIVATE', sql='PRIVATE', secret='PRIVATE')


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setenv('TEAM360_TELCHI_CONSOLE_ENABLED', '1')
    app = Litestar(route_handlers=list(ROUTE_HANDLERS))
    svc = Service()
    svc.calls = []
    app.state.telchi_console_runtime = SimpleNamespace(service=svc, evidence_sink=lambda: lambda _: None)
    with TestClient(app=app) as client:
        yield client, svc


def headers(**claims):
    return {'Authorization': 'Bearer ' + token(amr=['pwd'], credential_version=1, **claims)}


def test_real_session_required_not_uuid_bootstrap(client):
    http, _ = client
    assert http.get('/api/telchi/luna/session').status_code == 401
    assert http.get('/api/telchi/luna/session', headers={'Authorization': 'Bearer ' + token()}).status_code == 401
    assert http.get('/api/telchi/luna/session', headers=headers()).status_code == 200


def test_permissions_denied_before_research(client):
    http, svc = client
    svc.denied = True
    response = http.post('/api/telchi/luna/ask', headers=headers(),
        json={'question': 'ventas', 'conversation_id': str(uuid4())})
    assert response.status_code == 403
    assert svc.calls == []


def test_stream_presentation_allowlist_and_conversation(client):
    http, svc = client
    conversation = str(uuid4())
    for question in ('ventas octubre', '¿y septiembre?'):
        response = http.post('/api/telchi/luna/ask', headers=headers(),
            json={'question': question, 'conversation_id': conversation})
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        assert 'event: result' in response.text
        assert 'Respuesta acreditada' in response.text
        assert 'PRIVATE' not in response.text
        assert response.headers['cache-control'] == 'no-store'
    assert svc.calls == [('ventas octubre', conversation), ('¿y septiembre?', conversation)]


@pytest.mark.parametrize('body', [
    {'question': 'ventas', 'conversation_id': str(uuid4()), 'role': 'admin'},
    {'question': '', 'conversation_id': str(uuid4())},
    {'question': 'ventas', 'conversation_id': '../other'},
])
def test_request_cannot_supply_authority(client, body):
    http, svc = client
    assert http.post('/api/telchi/luna/ask', headers=headers(), json=body).status_code == 400
    assert not svc.calls


def test_production_disabled(client, monkeypatch):
    http, _ = client
    monkeypatch.setenv('TEAM360_ENV', 'production')
    assert http.get('/api/telchi/luna/session', headers=headers()).status_code == 404


def test_execution_failure_is_not_fictional_answer(client):
    http, svc = client
    async def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE failure')
    svc.ask = fail
    response = http.post('/api/telchi/luna/ask', headers=headers(),
        json={'question': 'ventas', 'conversation_id': str(uuid4())})
    assert 'event: error' in response.text
    assert 'event: result' not in response.text
    assert 'PRIVATE' not in response.text
