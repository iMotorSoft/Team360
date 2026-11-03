"""Lazy optional Telchi profiling bridge; normal Messaging never imports Telchi."""
from contextlib import contextmanager, asynccontextmanager
import os
import sys


def enabled():
    return os.getenv('TEAM360_TELCHI_PRE_SQL_PROFILE') == '1'


def active_trace():
    module = sys.modules.get('modules.telchi.datalake.query_profile')
    return module.active_trace() if module is not None else None


@contextmanager
def span(label):
    module = sys.modules.get('modules.telchi.datalake.query_profile')
    if module is None:
        yield
    else:
        with module.span(label):
            yield


@asynccontextmanager
async def aspan(label):
    with span(label):
        yield
