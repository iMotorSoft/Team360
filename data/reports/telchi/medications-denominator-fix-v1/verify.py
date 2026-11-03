"""Verify saved evidence and replay the actual turn through the fixed formatter."""
import hashlib
import json
from pathlib import Path
from modules.telchi.assistant.commercial_continuity import shares, denominator_accredited, format_category_analysis

here = Path(__file__).resolve().parent
load = lambda name: json.loads((here / name).read_text())
real = load('real-turn.json')[0]
s = real['confirmed_state']
a = real['category_analysis']
d = a['denominator']
assert a['denominator_status'] == 'NOT_ACCREDITED' and d['accreditation'] == 'verified'
assert denominator_accredited(s, d) and shares(s, a['components'], d) == {}
replay = format_category_analysis(s, a['components'], d, {})
assert '8.048.691,58' in replay and 'falta acreditar un total global' not in replay
turns = load('conversation.json')['turns']
assert len(turns) == 8 and len({t['thread_id'] for t in turns}) == 1
for i, t in enumerate(turns):
    assert t['classification'] == 'DIRECT_AVAILABLE', i
    assert t['confirmed_state']['period'] == s['period'], i
    assert '8.048.691,58' in t['text'], i
    assert 'falta acreditar un total global' not in t['text'], i
    assert not t['contract_error'], i
    assert len(t['text']) <= 1500, i
for i, percent in [(1, '33,29'), (2, '10,43'), (3, '31,24'), (7, '33,29')]:
    assert percent + ' %' in turns[i]['text']
assert 'SUPPORTED' in turns[3]['text']
for i in (4, 5, 6):
    assert turns[i]['confirmed_state']['analysis_categories'] == ['MEDICATIONS']
    assert 'clasificación no acreditada' in turns[i]['text']
    assert 'no los equiparo con productos terminados' in turns[i]['text']
    assert 'falta identificar qué importe' in turns[i]['text']
for i in (5, 6):
    assert 'no hice una nueva consulta' in turns[i]['text']
biz = load('biz01.json')
assert biz['conversation_pass'] and biz['turns_correct'] == 10
gates = load('six-gates.json')
assert gates['SIX_GATES'] == 'VALID'
backend = here.parents[3] / 'SrvRestAstroLS_v1/backend'
files = ['commercial_continuity.py', 'handler.py', 'repository.py', 'tests/test_commercial_continuity_v2.py']
report = dict(
    branch='feature/console-backend-core', REAL_TURN_AUDITED='YES',
    real_event_id=real['event_id'], real_thread_id=real['thread_id'],
    ROOT_CAUSE='An empty percentages mapping was used as denominator accreditation in handler and formatter. With medications unclassified the numerator is absent, but the authorized compatible base is verified.',
    DENOMINATOR_PRESERVED='PASS', MEDICATIONS_CLASSIFICATION_WARNING='PASS',
    FALSE_UNAVAILABILITY_REMOVED='PASS', BUSINESS_ANSWER_FIRST='PASS',
    CONVERSATION_REGRESSION='PASS', conversation_turns=8, BIZ01='PASS', biz01_correct='10/10',
    TESTS=gates['validations']['result'], SIX_GATES=gates['SIX_GATES'],
    RUNTIME_STATE='STOPPED', WHATSAPP_E2E='NOT_RUN', READY_FOR_MANUAL_START='YES',
    real_turn_replay=replay,
    audit_comparison='Real and synthetic cases agree: verified denominator, empty components/percentages; no classification inferred. Luna proposed EXPLAIN/ANALYSIS_UNAVAILABLE; business contract committed September/MEDICATIONS correctly. Failure occurred after execution, not in period retention.',
    scope_extension='Repository read is necessary for requested explanation follow-ups. It loads only a bounded same-owner/same-conversation/exact-state prior authorized composition, strips unneeded product breakdown, revalidates permissions and never executes from EXPLAIN.',
    files_modified={str(backend / 'modules/telchi/assistant' / f):hashlib.sha256((backend / 'modules/telchi/assistant' / f).read_bytes()).hexdigest() for f in files},
    evidence=['real-turn.json', 'conversation.json', 'biz01.json', 'six-gates.json'],
    limitations=['Provider request body was not retained; exact user text, persisted pre-turn scope, Luna proposal, committed state, capability result and prepared response were audited.',
        'One live attempt failed the pre-existing missing-period model preflight before conversation execution; rerun passed. Earlier conversation runs exposed raw category-label and explanation-continuity defects now covered by regression tests.',
        'Four opt-in tests skipped; no WhatsApp delivery certification or provider-outage induction.',
        'Classifications remain current, not historical; September observed coverage ends September 24, not a certified monthly close.'],
    operations=dict(whatsapp_sends=0, runtime_sessions_started=0, operational_grants_changed=0,
        foundation_changes=0, credential_changes=0, unrelated_processes_terminated=0,
        gate_reaccreditation='Six fresh real probes; isolated pg_temp authorization fixtures, forced rollback; normal preflight valid. Versioned private manifest published with backup by existing procedure, not an artificial hash edit.'),
    HOST_PREFLIGHT='SAFE', RESOURCE_GUARD='PASS', CONCURRENCY_USED='One sequential runner; gate PG pool max 3, only two concurrent claims of one event; no browsers.',
    ENVIRONMENTAL_ABORTS=0, OWN_PROCESSES_LEFT_RUNNING=0,
    next_step='Owner manual start and targeted WhatsApp check only; no automatic start.')
(here / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
print('REAL_REPLAY=PASS CONVERSATION=8/8 BIZ01=10/10 SIX_GATES=VALID')
