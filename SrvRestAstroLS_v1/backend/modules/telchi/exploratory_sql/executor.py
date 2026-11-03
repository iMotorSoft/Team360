"""Fail-closed execution boundary for the F1 isolation-blocked environment.

There is deliberately NO worker executing SQL until filesystem/network/process
and OS resource controls are accredited. Neither an env flag, read_only nor a
successful namespace probe is sufficient to authorize a worker.
"""
from dataclasses import dataclass
import subprocess
import threading
import time

from . import FEATURE_ENABLED_DEFAULT
from .contracts import Decision, ExploratoryQueryResult, SecurityDecision
from .validator import validate


@dataclass(frozen=True)
class IsolationProbe:
    available: bool
    reason: str


def probe_isolation():
    """Trusted /usr/bin/true only; no SQL, secrets, backend env or data mounts.

    A probe success is necessary but NOT sufficient for sandbox accreditation.
    No alternate namespace flags or privilege mechanisms are attempted on failure.
    """
    command = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
               "/usr/bin/true"]
    try:
        result = subprocess.run(command, env={"PATH": "/usr/bin", "LANG": "C"},
                                cwd="/", stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                close_fds=True, timeout=3, check=False)
        return IsolationProbe(result.returncode == 0,
                              "namespace_probe_only" if result.returncode == 0 else "namespace_unavailable")
    except (OSError, subprocess.TimeoutExpired):
        return IsolationProbe(False, "namespace_unavailable")


class ResearchBudget:
    """Local budget accounting port; not an OS CPU/memory/scan enforcement claim."""
    def __init__(self, budget, *, clock=time.monotonic):
        self.budget, self.clock = budget, clock
        self.started = clock()
        self.count, self.active = 0, 0
        self.lock = threading.Lock()

    def reserve(self):
        with self.lock:
            if (self.clock() - self.started >= self.budget.total_seconds
                    or self.count >= self.budget.queries or self.active >= self.budget.concurrency):
                return False
            self.count += 1
            self.active += 1
            return True

    def release(self):
        with self.lock:
            if self.active <= 0:
                raise ValueError("no_active_reservation")
            self.active -= 1


class ExploratoryExecutor:
    """Optional internal capability, unavailable until a future isolation gate.

    Accepts proposals, NEVER caller-constructed validated SQL. Revalidates current
    context on every attempt. No tools/handlers/routes register this prototype.
    """
    def __init__(self, *, enabled=FEATURE_ENABLED_DEFAULT):
        self.enabled = enabled

    def execute(self, proposal, context, *, cancel=None):
        def stopped(decision, reason, query=None):
            query_id = query.query_id if query else ""
            return SecurityDecision(decision, reason, query_id or None), ExploratoryQueryResult(
                query_id=query_id, declared_grain=proposal.expected_grain,
                publication=context.publication, snapshot=context.snapshot,
                limitations=(reason, "no_sql_executed", "os_resource_limits_not_accredited"),
            )
        if not self.enabled:
            return stopped(Decision.DENY, "feature_disabled")
        if cancel is not None and cancel.is_set():
            return stopped(Decision.RESOURCE_BLOCKED, "cancelled_before_execution")
        decision, query = validate(proposal, context)
        if query is None:
            return stopped(decision.decision, decision.reason)
        # No caller injection, bool flag, probe result or model text can bypass this.
        return stopped(Decision.RESOURCE_BLOCKED, "execution_isolation_not_accredited", query)
