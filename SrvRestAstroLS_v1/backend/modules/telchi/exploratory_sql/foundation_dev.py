"""Explicit owner-authorized, local-only DEV exception. No shared guard changes.

python -m modules.telchi.exploratory_sql.foundation_dev --authorize-dev-io-exception --output NEW.json
"""
import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import json
import os
from pathlib import Path
import threading
import time

from .contracts import Budget, Decision, ExploratoryQueryProposal, ExploratoryQueryResult, SecurityDecision
from .direct_readonly import DirectReadonlyExecutor
from .foundation import CATALOG, FoundationReadonlyExecutor, host_read_preflight, local_context
from .foundation_verifier import control_proposals, verify_control
from . import research
from .validator import canonical, context_digest, validate


@dataclass(frozen=True)
class DevBudget(Budget):
    """Separate bounded CLI policy; does not change Budget/F1/runtime ceilings."""
    query_seconds: float = 120.0
    total_seconds: float = 900.0
    result_rows: int = 5000
    result_bytes: int = 2 * 1024 * 1024
    queries: int = 12

    def __post_init__(self):
        for name, field in DevBudget.__dataclass_fields__.items():
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (name not in {'query_seconds', 'total_seconds'} and type(value) is not int)
                    or not 0 < value <= field.default):
                raise ValueError('invalid_dev_budget')
        if self.query_seconds > self.total_seconds:
            raise ValueError('invalid_dev_budget')

    def intersect(self, other):
        return DevBudget(**{k: min(getattr(self, k), getattr(other, k))
                            for k in self.__dataclass_fields__})


class DevExecutor(FoundationReadonlyExecutor):
    """IO-wait-only exception with fresh memory/swap checks and cancellation.

    SQL authorization, pinning, read-only check, lock, deadlines and fetch limits
    are still implemented by the existing executor. This is not an OS sandbox.
    """
    def __init__(self, context, *, authorized=False):
        if not authorized or context.environment != 'dev':
            raise ValueError('explicit_dev_exception_required')
        super().__init__(context)
        self.initial_swap = self.swap_bytes()
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.monitor = threading.Thread(target=self.watch, name='telchi-dev-memory')
        self.monitor.start()

    @staticmethod
    def swap_bytes():
        mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return (int(mem['SwapTotal'].split()[0]) - int(mem['SwapFree'].split()[0])) * 1024

    def healthy(self):
        mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return (int(mem['MemAvailable'].split()[0]) * 1024 >= 2 * 1024**3
                and self.swap_bytes() - self.initial_swap < 256 * 1024**2)

    def watch(self):
        while not self.done.wait(0.5):
            if not self.healthy():
                self.cancel.set()
                return

    def execute(self, proposal, context, *, cancel=None):
        decision, query = validate(proposal, context)
        if query is None or self._closed or context_digest(context) != context_digest(self.context):
            return DirectReadonlyExecutor.execute(self, proposal, context, cancel=self.cancel)
        self.last_preflight = host_read_preflight()
        self.last_preflight['io_only_exception_authorized'] = True
        if not self.healthy() or self.cancel.is_set():
            return SecurityDecision(Decision.RESOURCE_BLOCKED, 'dev_memory_or_swap_pressure'), ExploratoryQueryResult(query_id=query.query_id, status='NOT_EXECUTED')
        own_cancel = self.cancel
        class CombinedCancellation:
            def is_set(self):
                return own_cancel.is_set() or (cancel is not None and cancel.is_set())
        return DirectReadonlyExecutor.execute(self, proposal, context, cancel=CombinedCancellation())

    def close(self):
        self.done.set()
        self.monitor.join()
        super().close()


SYSTEM = research.SYSTEM.replace(
    'investigating a SEALED SYNTHETIC fixture', 'investigating real TELCHI Foundation data').replace(
    'Header money is BS; line money deliberately differs. Joining movements may multiply invoice totals.',
    'Only commercial line amounts are exposed; header money is NOT exposed. Do not join unless within the conservative pair budget.').replace(
    'Evidence is a synthetic experiment, never real Calenta.',
    'Evidence is real but limited to four reference SKUs, August 2026, pinned publication/snapshot.').replace(
    '"metric":"invoice_header_total_bs"', '"metric":"reference_sku_line_total_bs"') + '''
The business question is Calenta August 2026. Four reference SKUs are NOT universal brand membership.
Commercial line amounts exclude credit memos and global adjustments; NOT net billing or collections.
Month completeness is not certified. Do not assert causality or historical channel classification.
Start with aggregates, not documentary row exports. Both logical tables are already scoped to
active August 2026 invoices and the four reference SKUs. JOINS ARE UNAVAILABLE in this pilot:
the conservative relation bounds exceed max_join_pairs. Investigate each table independently;
do not join to reapply dates or to attribute line money to channels. Finish after 2-3 successful queries. Only aggregate results and at most 3 sample rows
may be observed. SALON has SUPPORTED status, not CONFIRMED; do not accredit it as confirmed. Final claims: reference_sku_line_total_bs and sku:<item_code> only.
Every other claim is independently UNVERIFIED. Continue with a query motivated by prior observations.
'''


def proposal(sql, source):
    return ExploratoryQueryProposal(sql, 'small_readonly_probe', 'bounded first read',
                                    (source,), 'aggregate', 'one row', requested_budget=DevBudget())


def check_claim(claim, reference):
    if not isinstance(claim, dict):
        return dict(state='UNVERIFIED', reason='invalid_claim')
    metric = claim.get('metric')
    expected = reference['total'] if metric == 'reference_sku_line_total_bs' else None
    if isinstance(metric, str) and metric.startswith('sku:'):
        expected = next((r['amount'] for r in reference['breakdowns']['product']
                         if r['key'] == metric[4:]), None)
    if expected is None:
        return dict(metric=metric, state='UNVERIFIED', reason='unsupported_scope')
    try:
        raw = claim.get('value')
        if not isinstance(raw, str) or len(raw) > 40:
            raise ValueError()
        value = Decimal(raw)
        match = value.is_finite() and value == Decimal(expected)
    except (ValueError, InvalidOperation):
        match = False
    return dict(metric=metric, value=claim.get('value'), expected=expected,
                state='REFERENCE_MATCH' if match else 'REJECTED')


def accept_final(value, reference, report):
    if value.get('action') != 'final' or not isinstance(value.get('answer'), str) or not value['answer'].strip():
        raise RuntimeError('final_answer_required_no_further_sql')
    report['model_answer'] = value['answer']
    claims = value.get('claims', [])
    if not isinstance(claims, list) or len(claims) > 10:
        raise RuntimeError('invalid_claims')
    report['claim_verifications'] = [check_claim(c, reference) for c in claims]
    states = [c['state'] for c in report['claim_verifications']]
    has_total = any(c.get('metric') == 'reference_sku_line_total_bs' for c in report['claim_verifications'])
    report['status'] = ('VERIFIED_WITH_LIMITATIONS' if has_total and states and all(s == 'REFERENCE_MATCH' for s in states)
                        else 'REJECTED' if 'REJECTED' in states else 'PARTIAL')
    report['answer_scope'] = 'Only supported numeric claims independently checked; narrative not certified.'


async def final_only(luna, history, reference, report):
    # A terminal summary is NOT another execution route after a denied query.
    # No SQL is accepted or executed from this response.
    research.SYSTEM = SYSTEM + '\nQuery phase is CLOSED. Return action final now, using only observed results. Do not propose SQL.'
    payload = dict(question='Resume en español la investigación Calenta agosto 2026 y sus limitaciones.',
                   observations=history, successful_queries=sum(h.get('status') == 'COMPLETED' for h in history),
                   execution_closed=True)
    if len(canonical(payload).encode()) > 32768:
        raise RuntimeError('observation_byte_budget')
    value = await luna.next(payload, timeout=90)
    accept_final(value, reference, report)


async def run(report):
    context = replace(local_context('FOUNDATION_CALENTA_DEV_IO_EXCEPTION'), effective_budget=DevBudget())
    report.update(publication=context.publication, snapshot=context.snapshot, budget=asdict(context.effective_budget),
                  code_digest=research.code_digest(), status='PARTIAL', turns=[], controls=[])
    with DevExecutor(context, authorized=True) as executor:
        small = proposal('SELECT count(*) AS line_count FROM sales_line', 'sales_line')
        decision, result = executor.execute(small, context)
        report['small_query'] = dict(decision=asdict(decision), result=asdict(result))
        save(report)
        if result.status != 'COMPLETED':
            report.update(status='BLOCKED', reason=decision.reason)
            return
        results = []
        for original in control_proposals():
            p = replace(original, requested_budget=DevBudget())
            decision, result = executor.execute(p, context)
            report['controls'].append(dict(proposal=asdict(p), decision=asdict(decision), result=asdict(result)))
            save(report)
            if result.status != 'COMPLETED':
                report.update(status='BLOCKED', reason=decision.reason)
                return
            results.append(result)
        reference = verify_control(context, results, reference_proposals=tuple(
            replace(p, requested_budget=DevBudget()) for p in control_proposals()), allow_supported_channel=True)
        report['independent_verification'] = reference
        save(report)
        if reference['state'] != 'VERIFIED_WITH_LIMITATIONS':
            report.update(status='BLOCKED', reason='independent_reference_not_verified')
            return
        luna, history, completed = research.LunaSQL(), [], set()
        # This CLI has its own prompt; shared/synthetic adapters on disk stay unchanged.
        research.SYSTEM = SYSTEM
        start = time.monotonic()
        try:
            for turn in range(7):
                if time.monotonic() - start > 600 or executor.cancel.is_set():
                    raise RuntimeError('research_deadline_or_memory_pressure')
                payload = dict(question='¿Cuánto vendimos de Calenta en agosto de 2026? Investiga concentraciones y limitaciones.',
                               catalog=asdict(CATALOG), observations=history, successful_queries=len(completed), remaining_calls=7-turn)
                if len(canonical(payload).encode()) > 32768:
                    raise RuntimeError('observation_byte_budget')
                value = await luna.next(payload, timeout=90)
                report['model_calls'] = luna.calls
                save(report)
                if value.get('action') == 'final':
                    if len(completed) < 2:
                        history.append(dict(decision='BLOCKED', reason='two_distinct_queries_required'))
                        continue
                    accept_final(value, reference, report)
                    return
                p = replace(research.proposal_from(value), requested_budget=DevBudget())
                decision, result = executor.execute(p, context)
                report['turns'].append(dict(proposal=asdict(p), decision=asdict(decision), result=asdict(result)))
                # No control rows, extraction IDs or full documentary populations sent to OpenAI.
                aggregate = bool(__import__('re').search(r'\b(count|sum|min|max|avg)\s*\(', p.sql, __import__('re').I))
                rows = result.rows[:30 if aggregate else 3]
                observation = dict(decision=asdict(decision), schema=asdict(result)['schema'], rows=rows,
                                   truncated=result.truncated or len(rows) < len(result.rows), status=result.status,
                                   publication=context.publication, snapshot=context.snapshot,
                                   verification='UNVERIFIED pending independent supported claim check')
                history.append(observation)
                if result.status == 'COMPLETED' and not result.truncated:
                    completed.add(result.query_id)
                save(report)
                if decision.decision in {Decision.DENY, Decision.RESOURCE_BLOCKED}:
                    report.update(status='BLOCKED', reason=decision.reason)
                    if decision.reason == 'join_pair_budget' and len(completed) >= 2:
                        await final_only(luna, history, reference, report)
                    return
                if len(completed) >= 3:
                    await final_only(luna, history, reference, report)
                    return
            report['reason'] = 'model_call_budget_exhausted'
        finally:
            report['model_calls'] = luna.calls


OUTPUT = None


def save(report):
    temp = OUTPUT.with_suffix('.pending')
    with temp.open('w') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')
    os.replace(temp, OUTPUT)


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-dev-io-exception', action='store_true', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    OUTPUT = Path(args.output)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), environment='DEV',
                  owner_authorization='Mario: explicit DEV I/O-wait-only exception and minimal OpenAI business egress',
                  storage_health='Accessible journal has no errors; full kernel logs unavailable to current user.',
                  exception_scope='This CLI only; no global or production guard modified.',
                  os_isolation_accredited=False, process_rss_limit_enforced=False,
                  connection_setup_deadline_enforced=False, whatsapp='NOT_RUN', own_processes_left_running=0)
    fd = os.open(f'/tmp/telchi-exploratory-dev-{os.getuid()}.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with OUTPUT.open('x'):
            pass
        save(report)
        try:
            asyncio.run(run(report))
        except Exception as exc:
            report.update(status='BLOCKED', reason=type(exc).__name__ + ':' + str(exc)[:100])
        finally:
            save(report)
    print(canonical(dict(status=report.get('status'), reason=report.get('reason'), output=str(OUTPUT))))


if __name__ == '__main__':
    main()
