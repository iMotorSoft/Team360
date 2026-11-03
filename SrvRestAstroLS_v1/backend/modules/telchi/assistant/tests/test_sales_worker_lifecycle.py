"""Real subprocess cancellation; synthetic workload, never commercial evidence."""
import asyncio
from pathlib import Path
import sys

import pytest

from modules.telchi.datalake import sales_query as query


@pytest.mark.parametrize('caller_cancel', [False, True])
def test_cancel_unwinds_and_reaps_worker(tmp_path, monkeypatch, caller_cancel):
    asyncio.run(_cancel_unwinds_and_reaps_worker(tmp_path, monkeypatch, caller_cancel))


async def _cancel_unwinds_and_reaps_worker(tmp_path, monkeypatch, caller_cancel):
    original = asyncio.create_subprocess_exec
    cleanup, ready = tmp_path/'closed', tmp_path/'ready'
    children = []
    async def launch(*args, **kwargs):
        script = f'''import signal, time
from pathlib import Path
from modules.telchi.datalake.sales_query import _cancel_worker
signal.signal(signal.SIGTERM, _cancel_worker)
try:
    Path({str(ready)!r}).touch()
    time.sleep(60)
finally:
    Path({str(cleanup)!r}).touch()
'''
        process = await original(sys.executable, '-c', script, **kwargs)
        children.append(process)
        for _ in range(200):
            if ready.exists():
                break
            await asyncio.sleep(.01)
        assert ready.exists()
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', launch)
    task = asyncio.create_task(query.query_sales('sales.coverage', {}, timeout_seconds=2))
    try:
        if caller_cancel:
            while not ready.exists():
                await asyncio.sleep(.01)
            await asyncio.sleep(.05)
            task.cancel()
        with pytest.raises(asyncio.CancelledError if caller_cancel else asyncio.TimeoutError):
            await task
        assert cleanup.exists(), 'cooperative signal must run finally'
        assert children[0].returncode is not None
        assert not query._LOCK.locked()
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
                await child.wait()
