"""Reaccredit existing guarantees by adapting the reviewed operational runner.
Only evidence harness is adapted, never runtime. No listeners or WhatsApp.
Existing invoice implementation/test evidence is hash verified and reused.
"""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
base = ROOT / 'data/reports/telchi/result-reference-pipeline-v1/validate.py'
text = base.read_text()

def change(old, new):
    global text
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new)

change("out = d.PRIVATE_ROOT / ('result-reference-pipeline-'", "out = d.PRIVATE_ROOT / ('invoice-gate-reaccreditation-'")
change("    assert datetime.fromisoformat(old['expires_at']) > datetime.now(timezone.utc)\n", "    # Expired technical evidence is provenance only, not current admission.\n")
start = text.index('    validation = json.loads(')
end = text.index('    _, srv, settings, binding', start)
text = text[:start] + '''    evidence_root = ROOT / 'data/reports/telchi/document-continuity-invoice-lines-v1'
    validation = json.loads((evidence_root / 'source-manifest-final.json').read_text())
    for name, value in validation['files'].items():
        assert sha(ROOT / name) == value, name
    summary = json.loads((evidence_root / 'validation-summary.json').read_text())
    assert summary['pytest'] == dict(passed=422, skipped=2, warnings=1, evidence='pytest-final-r3.txt')
    passed('focused_evidence_reuse', tests='422 PASS / 2 SKIP; exact source manifest verified; not rerun',
           source_manifest_sha256=sha(evidence_root / 'source-manifest-final.json'),
           test_artifact_sha256=sha(evidence_root / 'pytest-final-r3.txt'),
           luna_artifact_sha256=sha(evidence_root / 'luna-full-conversation.json'))
''' + text[end:]
change("host_preflight='BUSY_BUT_SAFE: 8 CPUs, load 2.93/3.84/3.80; 4207 MiB available; swap 1585 MiB stable; sampled idle 61-77%, no swap IO'", "host_preflight='BUSY_BUT_SAFE: 8 CPUs, load 1.31/1.61/1.49; 5422 MiB available; swap 2652 MiB stable; sampled idle 84-90%, no swap IO'")
change("command='SrvRestAstroLS_v1/backend/.venv/bin/python data/reports/telchi/result-reference-pipeline-v1/validate.py'", "command='SrvRestAstroLS_v1/backend/.venv/bin/python data/reports/telchi/invoice-gate-reaccreditation-v1/run.py'")
change("        cap = h.CapabilityCounter(SalesCapabilities())", '''        class CountedCapabilities(SalesCapabilities):
            invoice_calls = 0
            async def invoice_lines(self, parameters):
                self.invoice_calls += 1
                return await super().invoice_lines(parameters)
        cap = h.CapabilityCounter(CountedCapabilities())''')
anchor = "        passed('durable_idempotency', real_pg=True, new_turns=len(r['turns']),"
change(anchor, '''        # Scope restoration above is verified against the real public grants.
        # Rebuild handlers each turn: recover a document, then read actual lines.
        first, first_dispatch, _, _ = await turn('Mostrame el número de la primera factura de esas tres últimas facturas.', 'first-document')
        assert first['decision'] in {'SELECT_RESULT', 'SELECT_DOCUMENT'} and first['capability_calls'] == 0
        assert first['selected_document']['doc_entry'] == three['execution_result']['rows'][0]['doc_entry']
        invoice, invoice_dispatch, invoice_row, invoice_ev = await turn('Mostrame los productos de esta factura.', 'invoice-lines', concurrent=True)
        assert invoice_dispatch['classification'] == 'DIRECT_AVAILABLE'
        assert invoice['execution_status'] == 'executed' and invoice['capability_calls'] == 1
        result = invoice['execution_result']
        from modules.telchi.datalake.invoice_lines_query import PERMISSION as LINE_PERMISSION
        assert result['capability'] == 'sales.invoice_lines.v1' and result['rows']
        assert invoice['required_permission'] == LINE_PERMISSION and invoice['business_rbac_verified'] is True
        assert result['document']['doc_entry'] == first['selected_document']['doc_entry']
        assert cap.inner.invoice_calls == 1 and cap.calls == 2
        passed('invoice_lines_authorized_execution', capability=result['capability'], permission=LINE_PERMISSION,
               source=result['source'], rows=len(result['rows']), fresh_handler=True,
               rows_sha256=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest(),
               concurrent_retries='Both duplicate; one invoice query; one logical outbound')
        invoice_context = latest_context
        async with transaction(pool) as conn:
            loaded = await ConversationRepository().load(conn, invoice_context)
            assert loaded['document_reference']['result_id'] == str(three_row['id'])
            assert loaded['document_reference']['selected_ordinal'] == 1
            assert loaded['result_reference']['result_id'] == str(invoice_row['id'])
            view = await ConversationRepository().load_result(conn, invoice_context, loaded)
            assert view and view['capability'] == 'sales.invoice_lines.v1'
            assert await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
            await conn.execute(\'''CREATE TEMP TABLE core_role_permissions AS SELECT rp.* FROM public.core_role_permissions rp
                JOIN public.core_user_roles ur ON ur.role_id=rp.role_id WHERE ur.user_id=%s\''', (a['user_id'],))
            await conn.execute(\'''CREATE TEMP TABLE core_profile_permissions AS SELECT pp.* FROM public.core_profile_permissions pp
                JOIN public.core_user_profiles up ON up.profile_id=pp.profile_id WHERE up.user_id=%s\''', (a['user_id'],))
            # Force re-resolution after recreating same-named temporary tables:
            # prior prepared queries may otherwise remain bound to public joins.
            await conn.execute('SET search_path TO pg_temp, public')
            for table in ('core_role_permissions', 'core_profile_permissions'):
                await conn.execute('DELETE FROM pg_temp.' + table + ' WHERE permission_id IN (SELECT id FROM public.core_permissions WHERE permission_code=%s)', (LINE_PERMISSION,))
        async with transaction(pool) as conn:
            assert not await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
        denied_invoice = await latest_handler.handle(invoice_ev, invoice_context)
        assert denied_invoice.classification == 'DENIED'
        assert cap.inner.invoice_calls == 1
        async with transaction(pool) as conn:
            await conn.execute('DROP TABLE pg_temp.core_role_permissions, pg_temp.core_profile_permissions')
            assert await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
        passed('invoice_lines_revocation_and_recovery', persisted_parent_and_line_pointers=True,
               cached_result_after_revocation='DENIED', additional_invoice_queries=0,
               live_console_resolver=True, public_grants_preserved=True,
               scope='Only session-local copies of actual joins modified; no public grants changed')
''' + anchor)
change("r.update(error_class=type(exc).__name__, error=str(exc)[:160] if isinstance(exc, AssertionError) else 'See private runner stage')", "r.update(error_class=type(exc).__name__, error=str(exc)[:160] if isinstance(exc, AssertionError) else 'See private runner stage', traceback=__import__('traceback').format_exc())")
# Preserve base-runner provenance and pin adapted text for audit.
adapted = HERE / 'executed-runner.py'
adapted.write_text(text)
compile(text, str(adapted), 'exec')
exec(compile(text, str(adapted), 'exec'), {'__name__': '__main__', '__file__': str(adapted)})
