"""Dirty historical scope model; detection sources remain outside this package."""
from __future__ import annotations

from .contracts import DirtyScope, DirtyScopeStatus
from .stores import DirtyScopeStore


class DirtyScopeTracker:
    def __init__(self, store: DirtyScopeStore) -> None:
        self.store = store

    def detect(self, scope: DirtyScope) -> DirtyScope:
        if scope.status is not DirtyScopeStatus.DIRTY:
            raise ValueError("new dirty scopes must start DIRTY")
        self.store.save_dirty_scope(scope)
        return scope

    def transition(self, dirty_scope_id: str, target: DirtyScopeStatus) -> DirtyScope:
        scope = self.store.get_dirty_scope(dirty_scope_id)
        if scope is None:
            raise KeyError(dirty_scope_id)
        scope.transition(target)
        self.store.save_dirty_scope(scope)
        return scope
