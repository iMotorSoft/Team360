"""Opt-in monotonic DEV profiling; stores labels/times only, never SQL or config."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import time

_ACTIVE = ContextVar('telchi_query_profile', default=None)


def enabled():
    return os.getenv('TEAM360_TELCHI_PRE_SQL_PROFILE') == '1'


class Trace:
    def __init__(self):
        self.origin = time.perf_counter_ns()
        self.events = []

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    def export(self):
        return {'schema': 'telchi-pre-sql-profile-v1', 'clock': 'perf_counter_ns',
                'spans': self.events, 'total_ms': (time.perf_counter_ns()-self.origin)/1e6}


@contextmanager
def span(label):
    trace = _ACTIVE.get()
    if trace is None:
        yield
        return
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        end = time.perf_counter_ns()
        trace.events.append({'label': label, 'start_ms': (start-trace.origin)/1e6,
                             'end_ms': (end-trace.origin)/1e6, 'duration_ms': (end-start)/1e6})


def active_trace():
    return _ACTIVE.get()


def measured(label, function, *args, **kwargs):
    with span(label):
        return function(*args, **kwargs)
