"""Bounded read-only DEV diagnostic, no model, publication writes or bypasses."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from time import perf_counter


def worker(output):
    import faulthandler
    from modules.telchi.datalake.query_profile import Trace
    from modules.telchi.datalake.sales_query import execute_query, MONETARY_OPERATION
    class Events(list):
        def append(self, event):
            super().append(event)
            with output.with_suffix('.jsonl').open('a') as stream:
                stream.write(json.dumps(event)+'\n')
    trace = Trace()
    trace.events = Events()
    with output.with_suffix('.stack').open('w') as stack:
        faulthandler.dump_traceback_later(25, repeat=True, file=stack)
        try:
            with trace.activate():
                result = execute_query(MONETARY_OPERATION, dict(date_from='2026-09-01', date_to_exclusive='2026-10-01', currency='BS'))
            output.write_text(json.dumps(dict(result=result, trace=trace.export()), indent=2))
        finally:
            faulthandler.cancel_dump_traceback_later()


async def run(output):
    if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
        raise RuntimeError('DEV only')
    if output.exists() or output.with_suffix('.jsonl').exists():
        raise RuntimeError('new evidence path required')
    output.parent.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'modules.telchi.assistant.tests.profile_sales_worker', '--worker', '--output', str(output))
    canceled = False
    try:
        await asyncio.wait_for(process.wait(), 120)
    except asyncio.TimeoutError:
        canceled = True
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        output.with_suffix('.lifecycle.json').write_text(json.dumps(dict(total_seconds=perf_counter()-start, timeout_seconds=120, canceled=canceled, returncode=process.returncode, worker_reaped=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args.output)
    else:
        asyncio.run(run(args.output))
