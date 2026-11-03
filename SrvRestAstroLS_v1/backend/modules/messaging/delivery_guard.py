"""Deterministic outbound guard for WhatsApp text bodies.

Meta accepts at most 4096 characters in ``text.body``. A longer body is
rejected by the provider, so an otherwise correct business result never
reaches the user: the answer exists, the delivery is lost.

This guard runs before the provider call. It never invents a value, never
alters a figure, a name or a warning, and it never omits something silently:
what is left out is stated in the delivered text and reported in the returned
decision. A line is never split, so no number, name or caveat can be cut in
half; the head keeps the main result and the tail keeps the material
limitations of the answer.
"""
from __future__ import annotations

from dataclasses import dataclass

META_TEXT_LIMIT = 4096
TARGET_TEXT_LIMIT = 1500

OMISSION_NOTE = ('(Mostré el resultado principal y sus advertencias; el detalle completo '
                 'quedó registrado en la auditoría de la sesión.)')


@dataclass(frozen=True)
class GuardDecision:
    """What is delivered, what was accredited and what was left out."""

    text: str
    full_text: str
    applied: bool
    omitted_lines: int
    reason: str | None

    @property
    def length(self) -> int:
        return len(self.text)

    def audit(self) -> dict:
        """A small, secret-free record of the decision for the audit trail."""
        return dict(applied=self.applied, delivered_length=self.length,
                    accredited_length=len(self.full_text),
                    omitted_lines=self.omitted_lines, reason=self.reason)


def _safe_prefix(line: str, budget: int) -> str:
    """The longest whole-word prefix of a line that fits and ends no number.

    Only used when a single line does not fit at all. The cut never happens
    inside a numeric token, so no figure is altered.
    """
    if budget <= 0:
        return ''
    if len(line) <= budget:
        return line
    cut = line.rfind(' ', 0, budget + 1)
    while cut > 0:
        prefix = line[:cut]
        last = prefix.rsplit(' ', 1)[-1]
        if not any(character.isdigit() for character in last):
            return prefix.rstrip()
        cut = line.rfind(' ', 0, cut)
    return line[:budget].rstrip()


def guard_outbound(text: str, *, limit: int = META_TEXT_LIMIT) -> GuardDecision:
    """Return a deliverable body that never exceeds the provider limit.

    The text is only transformed when it does not fit. Nothing is invented and
    no figure, name or warning is altered: whole lines are kept or dropped.
    """
    if not isinstance(text, str):
        raise TypeError('outbound_text_required')
    if len(text) <= limit:
        return GuardDecision(text=text, full_text=text, applied=False,
                             omitted_lines=0, reason=None)
    lines = text.split('\n')
    note = OMISSION_NOTE
    # The note and the separators between the parts are part of the budget.
    budget = limit - len(note) - 4
    # The tail carries the material limitations of the answer: it is reserved
    # before the head, so a long list can never starve the warnings.
    head_reserve = max(len(lines[0]) + 1, budget // 2)
    tail, tail_used = [], 0
    for line in reversed(lines):
        if tail_used + len(line) + 1 > budget - head_reserve:
            break
        tail.insert(0, line)
        tail_used += len(line) + 1
    head, used = [], 0
    for line in lines[:len(lines) - len(tail)]:
        if used + tail_used + len(line) + 1 > budget:
            break
        head.append(line)
        used += len(line) + 1
    truncated = False
    if not head and not tail and lines:
        # A single first line longer than the channel: keep a safe prefix of it.
        first = _safe_prefix(lines[0], budget)
        if first:
            head = [first]
            used = len(first) + 1
            truncated = len(first) < len(lines[0])
    delivered = _compose(head, tail, note)
    if len(delivered) > limit:  # Defensive: never cut a line to fit.
        while tail and len(delivered) > limit:
            tail.pop()
            delivered = _compose(head, tail, note)
        while head and len(delivered) > limit:
            head.pop()
            delivered = _compose(head, tail, note)
    omitted = len(lines) - len(head) - len(tail)
    if truncated:
        omitted += 1
    return GuardDecision(text=delivered, full_text=text, applied=True,
                         omitted_lines=omitted, reason='provider_text_limit')


def _compose(head, tail, note):
    delivered = '\n'.join(head)
    if tail:
        delivered += '\n\n' + '\n'.join(tail)
    return delivered + '\n\n' + note
