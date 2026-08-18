"""Team360 Flow LaMuni end-to-end demo harness.

A finite, deterministic and repeatable scenario that drives the real Flow
domain services over real PostgreSQL. Only the external transport (reply
sender, routing sender and AI interpreters) is replaced by deterministic fakes;
no business rule is bypassed and no status is written directly.
"""
