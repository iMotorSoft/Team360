"""Read-only inspection of this evaluation's interrupted message, never retry it."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings

async def main():
    control=json.loads(Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-dev-control.json').read_text())
    os.environ.update(control['env'])
    approval=json.loads(Path(control['approval']).read_text())
    questions=json.loads(Path('modules/telchi/investigation/validation/blind_investigative_v1/questions.json').read_text())
    question=questions['cases']['H_sales_stock_cross'][0]
    pool=create_pool(replace(get_database_settings(), min_size=1,max_size=1))
    await open_pool(pool)
    try:
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            await conn.execute("SET LOCAL statement_timeout='5s'")
            rows=await (await conn.execute("""SELECT id,thread_id,status,payload_jsonb->'telchi_assistant_v1' AS audit
                FROM message_events WHERE workspace_id=%s AND payload_jsonb->>'text'=%s LIMIT 2""",
                (approval['workspace_id'],question))).fetchall()
        output=Path('../../data/reports/telchi/blind-investigative-v1/question-11-aborted.json')
        assert not output.exists()
        output.write_text(json.dumps(dict(question=question,records=rows,
            classification='BLOCKED',reason='ENVIRONMENTAL_ABORT: own runner terminated after resource guard incident; no retry',
            latency_seconds=None,llm_calls=None,sql_calls=None),ensure_ascii=False,indent=2,default=str)+'\n')
        print('ABORTED_MESSAGE_RECORDS',len(rows))
    finally:
        await close_pool(pool)

asyncio.run(main())
