"""Read-only exact-turn audit; publish only non-personal scope and evidence."""
import asyncio
import hashlib
import json
from pathlib import Path
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from dataclasses import replace

async def main():
    l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    assert (await asyncio.to_thread(l.status))['state'] == 'STOPPED'
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute('SET TRANSACTION READ ONLY')
                await conn.execute('SET LOCAL statement_timeout = 5000')
                rows = await (await conn.execute("SELECT id,thread_id,payload_jsonb FROM message_events WHERE direction='inbound' AND lower(payload_jsonb->>'text') LIKE %s ORDER BY occurred_at_utc DESC LIMIT 5", ('%entonces cuanto es el porcentaje de medicamentos vendidos%',))).fetchall()
                result = []
                for row in rows:
                    a = row['payload_jsonb'].get('telchi_assistant_v1', {})
                    # Raw audit kept privately, no sender or transport payload copied.
                    private = d.PRIVATE_ROOT / ('medications-audit-' + str(row['id']) + '.json')
                    if not private.exists():
                        d.save_private(private, a)
                    analysis = a.get('category_analysis') or {}
                    denominator = analysis.get('denominator') or {}
                    result.append(dict(event_id=str(row['id']), thread_id=str(row['thread_id']),
                        audit_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
                        interpretation_proposed=a.get('interpretation_proposed'),
                        business_contract_proposal=a.get('business_contract_proposal'),
                        previous_scope={k:a.get('previous_state', {}).get(k) for k in ('period','analysis_categories')},
                        confirmed_state=a.get('confirmed_state'),
                        category_analysis=dict(components=analysis.get('components'),
                            percentages=analysis.get('percentages'), denominator_status=analysis.get('denominator_status'),
                            authorization=analysis.get('authorization'),
                            denominator={k:denominator.get(k) for k in ('source','parameters','total','accreditation','reconciliation','definition','coverage','currency','exceptions')}),
                        response_prepared=a.get('response_prepared'), execution_status=a.get('execution_status')))
                out = Path(__file__).with_name('real-turn.json')
                out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str)+'\n')
                print(json.dumps(dict(matches=len(rows), output=str(out), event_ids=[x['event_id'] for x in result])))
    finally:
        await close_pool(pool)
asyncio.run(main())
