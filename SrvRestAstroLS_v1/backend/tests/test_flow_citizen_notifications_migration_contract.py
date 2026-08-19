from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/022_team360_flow_citizen_notifications_v1.sql"
)


def test_migration_creates_citizen_notification_trace():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists flow_citizen_notifications" in sql
    assert "request_id" in sql and "references flow_requests(id)" in sql


def test_migration_defines_the_four_public_notification_types():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "'citizen_received'" in sql
    assert "'citizen_in_progress'" in sql
    assert "'citizen_info_required'" in sql
    assert "'citizen_resolved'" in sql


def test_migration_has_deterministic_dedupe_key():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "unique (request_id, notification_type)" in sql
    assert "dedupe_key" in sql


def test_migration_tracks_delivery_state_and_provider_evidence():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "'pending'" in sql
    assert "'sent'" in sql
    assert "'delivery_uncertain'" in sql
    assert "'delivery_failed'" in sql
    assert "provider_message_id" in sql
    assert "attempt_count" in sql
    assert "sent_at_utc" in sql


def test_migration_keeps_channel_to_email_v1():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "channel = 'email'" in sql


def test_migration_has_no_scheduler_reopen_or_whatsapp_scope():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "scheduler" not in sql
    assert "reopened" not in sql
    assert "alumbrado.n4" not in sql
