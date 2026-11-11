"""Free-analysis port: identity, source gate and presentation safety.

Fixtures only; real Foundation/Luna evidence lives in the closure report. This
proves the WhatsApp-facing port reuses the one researcher and fails closed.
"""
import asyncio
from contextlib import asynccontextmanager

import pytest

from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity
from modules.telchi.exploratory_sql.authorized_foundation import EffectiveScope, SourcePolicy
from modules.telchi.exploratory_sql.validator import Rejected
from modules.telchi.research_port import PRESENTATION_FIELDS, WhatsAppResearchPort

ORG, WS, USER = 'org-1', 'ws-1', 'user-1'


class Pool:
    @asynccontextmanager
    async def connection(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        yield self


class Identities:
    def __init__(self, row):
        self.row = row

    async def identity(self, conn, user_id):
        return self.row if self.row and self.row['user_id'] == user_id else None

    async def enabled_permissions(self, conn, workspace):
        return frozenset({'telchi.read.v1', 'telchi.other.read.v1'})


class Permissions:
    def __init__(self, held):
        self.held = frozenset(held)

    async def list_effective_permissions(self, conn, workspace, user):
        return set(self.held)


class Service:
    def __init__(self, report=None):
        self.pool, self.report, self.calls = Pool(), report, []

    async def ask_scope(self, resolver, question, save, *, progress=None, conversation_id,
                        business_knowledge=None, effective_scope=None):
        self.calls.append((await resolver(), question, conversation_id))
        return self.report


def identity(environment='dev'):
    channel = ChannelContext('wa', 'evolution', 'i', 'r', 'telchi', 'telchi_dev', 'telchi')
    sender = SenderIdentity(USER, 'telchi', 'telchi_dev', environment, frozenset({'telchi.read.v1'}))
    return MessageContext(channel, sender, '59170000000', 'conv-1', 'turn-1', frozenset())


def port(service, held=('telchi.read.v1',), whole=True, row=None, environment='dev'):
    row = row if row is not None else dict(user_id=USER, organization=ORG, workspace=WS)
    return WhatsAppResearchPort(
        service=service, organization=ORG, workspace=WS,
        policies=(SourcePolicy('sales_line', 'telchi.read.v1', ORG, WS, whole_dataset=whole),),
        evidence_sink_factory=lambda: (lambda report: None),
        identities=Identities(row), permissions=Permissions(held))


REPORT = dict(status='READY', business_answer='Respuesta acreditada', clarification='',
              publication='foundation_x', snapshot='1408', question_coverage='COMPLETE',
              reason='', model_calls=[{'model': 'luna'}], sql_executions=3, elapsed_seconds=1.25,
              required_measure='territorial_line_net', deterministic_continuations=[],
              deterministic_contract_completion={'value': '123.45'},
              observation_budget=dict(limit=32768, measured_bytes=41234), partial_verified_figures=2,
              raw_proposal='must never leak', evidence_path='/private/must/not/leak')


def test_only_presentation_fields_cross_the_channel():
    async def run():
        service = Service(REPORT)
        out = await port(service)('¿Cuánto vendimos?', 'conv-1', identity())
        assert out == {k: REPORT[k] for k in PRESENTATION_FIELDS}
        assert 'raw_proposal' not in out and 'evidence_path' not in out
        scope, question, conversation = service.calls[0]
        assert (scope.user_id, scope.organization, scope.workspace) == (USER, ORG, WS)
        assert question == '¿Cuánto vendimos?' and conversation == 'whatsapp:conv-1'
    asyncio.run(run())


def test_scope_intersects_effective_and_enabled_permissions():
    async def run():
        service = Service(REPORT)
        await port(service, held=('telchi.read.v1', 'telchi.disabled.read.v1'))(
            'pregunta', 'conv-1', identity())
        scope = service.calls[0][0]
        assert scope.permissions == frozenset({'telchi.read.v1'})
    asyncio.run(run())


@pytest.mark.parametrize('case', ['no_identity', 'wrong_environment', 'wrong_workspace', 'not_whole'])
def test_fail_closed_before_any_research(case):
    async def run():
        service = Service(REPORT)
        ctx = identity('prod') if case == 'wrong_environment' else identity()
        if case == 'no_identity':
            ctx = MessageContext(ctx.channel, None, '591', 'conv-1', 'turn-1', frozenset())
        row = dict(user_id=USER, organization=ORG, workspace='other') if case == 'wrong_workspace' else None
        p = port(service, whole=case != 'not_whole', row=row)
        with pytest.raises(Rejected):
            await p('pregunta', 'conv-1', ctx)
        assert service.calls == []
    asyncio.run(run())


def test_permission_revoked_between_turns_denies_the_next_access():
    async def run():
        service = Service(REPORT)
        p = port(service)
        await p('pregunta', 'conv-1', identity())
        p.permissions.held = frozenset()  # effective permission revoked in PG
        with pytest.raises(Rejected, match='no_authorized_source'):
            await p('seguimiento', 'conv-1', identity())
        assert len(service.calls) == 1
    asyncio.run(run())