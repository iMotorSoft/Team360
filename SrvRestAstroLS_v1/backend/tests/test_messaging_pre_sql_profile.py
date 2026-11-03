"""Opt-in trace is metadata-only; continuation refuses incomplete/drifted evidence."""
import asyncio
import json

import pytest

from modules.telchi.datalake.query_profile import Trace, span, measured, active_trace, enabled
from modules.messaging import pre_sql_profile_session as session


def test_opt_in_and_monotonic_nested_spans(monkeypatch):
    monkeypatch.delenv('TEAM360_TELCHI_PRE_SQL_PROFILE',raising=False)
    assert not enabled() and active_trace() is None
    sentinel=object()
    assert measured('not-recorded',lambda:sentinel) is sentinel
    monkeypatch.setenv('TEAM360_TELCHI_PRE_SQL_PROFILE','1')
    assert enabled()
    trace=Trace()
    with trace.activate():
        with span('outer'):
            assert measured('inner',lambda:sentinel) is sentinel
    assert active_trace() is None
    result=trace.export()
    inner,outer=result['spans']
    assert 0 <= outer['start_ms'] <= inner['start_ms'] <= inner['end_ms'] <= outer['end_ms'] <= result['total_ms']
    assert all(set(s)=={'label','start_ms','end_ms','duration_ms'} for s in result['spans'])


def test_tunnel_log_redacts_challenge_query_before_persistence():
    from io import StringIO
    line='ERR dest=https://example.test/webhook/meta?hub.verify_token=PRIVATE&hub.challenge=ready event=0\n'
    log=StringIO()
    session.drain_tunnel(StringIO(line),log)
    assert 'PRIVATE' not in log.getvalue()
    assert '?[REDACTED]' in log.getvalue()
    assert session.redact_tunnel_line('INF https://example.test\n')=='INF https://example.test\n'


def test_context_reset_on_exception_and_async_isolation():
    async def task(label):
        trace=Trace()
        with trace.activate():
            with span(label):
                await asyncio.sleep(0)
        return trace.export()['spans']
    async def exercise():
        a,b=await asyncio.gather(task('a'),task('b'))
        assert [s['label'] for s in a]==['a']
        assert [s['label'] for s in b]==['b']
    asyncio.run(exercise())
    with pytest.raises(ValueError):
        with Trace().activate():
            with span('failure'):
                raise ValueError('test')
    assert active_trace() is None


def test_continuation_requires_real_status_profile_and_unchanged_foundation(monkeypatch,tmp_path):
    monkeypatch.setattr(session,'REPORT',tmp_path)
    baseline={k:'test-'+k for k in ['result_hash','query_hash','executed_sql_hash','foundation_publication_id','ducklake_snapshot_id']}
    (tmp_path/'direct.json').write_text(json.dumps([baseline]))
    result=dict(baseline,read_only=True,sap_accessed=False,profile={
        'schema':'telchi-pre-sql-profile-v1','parent':{'total_ms':1},
        'spans':[{'label':label} for label in ['attachment_open_including_catalog_session',
                 'duckdb_sql_execute','fetch','materialization','foundation_resolution','duckdb_connect']]})
    sample={'result':result,'messaging_profile':{'pre_send_ms':1},'transport_status':'delivered'}
    session.validate_sample(sample)  # synthetic unit data, not real WhatsApp evidence
    sample['transport_status']='sent'
    with pytest.raises(AssertionError): session.validate_sample(sample)
    sample['transport_status']='read';result['foundation_publication_id']='changed'
    with pytest.raises(AssertionError): session.validate_sample(sample)


def test_continuation_transport_preflight_failure_sanitizes_and_starts_nothing(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from modules.messaging.providers.evolution.config import EvolutionConfig
    from modules.messaging.settings import MessagingDevSettings
    monkeypatch.setattr(session,'REPORT',tmp_path)
    monkeypatch.setattr(EvolutionConfig,'from_env',lambda:SimpleNamespace())
    monkeypatch.setattr(MessagingDevSettings,'from_env',lambda:SimpleNamespace())
    monkeypatch.setenv('META_TEAM360_APP_ID','unit-app')
    monkeypatch.setenv('META_TEAM360_APP_SECRET','UNIT_SECRET')
    def fail(*args,**kwargs):
        raise RuntimeError('UNIT_SECRET in private inspection must not be saved')
    def unexpected(*args,**kwargs):
        pytest.fail('No process may start after failed preflight')
    monkeypatch.setattr(session.subprocess,'check_output',fail)
    monkeypatch.setattr(session.subprocess,'run',unexpected)
    monkeypatch.setattr(session.subprocess,'Popen',unexpected)
    assert asyncio.run(session.main())==2
    result=next(tmp_path.glob('human-*/continuation.json'))
    state=json.loads(result.read_text())
    assert state['status']=='BLOCKED' and state['layer']=='transport preflight'
    assert 'UNIT_SECRET' not in result.read_text()
    assert not list(tmp_path.glob('human-*/session'))
