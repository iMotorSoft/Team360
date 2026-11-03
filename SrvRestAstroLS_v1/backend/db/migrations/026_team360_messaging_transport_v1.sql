-- Additive messaging transport scope; existing modules' NULL scopes unchanged.
-- Do not rewrite 001 or reuse Flow state. No credentials or phone numbers.
ALTER TABLE message_threads ADD COLUMN IF NOT EXISTS provider_instance text;
ALTER TABLE message_events ADD COLUMN IF NOT EXISTS provider_instance text;
ALTER TABLE message_events ADD COLUMN IF NOT EXISTS transport_status text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_transport_thread
    ON message_threads(channel_id, provider_instance, contact_identity)
    WHERE provider_instance IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_transport_message
    ON message_events(provider_id, provider_instance, provider_message_id)
    WHERE provider_instance IS NOT NULL AND provider_message_id IS NOT NULL
      AND event_type = 'message';
CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_transport_reply
    ON message_events(thread_id, correlation_id)
    WHERE provider_instance IS NOT NULL AND direction = 'outbound'
      AND event_type = 'message' AND correlation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_transport_status
    ON message_events(provider_id, provider_instance, provider_message_id, transport_status)
    WHERE provider_instance IS NOT NULL AND event_type = 'status';

-- Operational status remains pending/completed/failed; transport_status is
-- orthogonal. Callback events survive early arrival, reordering and restart.
-- Rollback only after stopping the adapter and preserving its evidence:
-- DROP INDEX uq_messaging_transport_status;
-- DROP INDEX uq_messaging_transport_reply;
-- DROP INDEX uq_messaging_transport_message;
-- DROP INDEX uq_messaging_transport_thread;
-- ALTER TABLE message_events DROP COLUMN transport_status, DROP COLUMN provider_instance;
-- ALTER TABLE message_threads DROP COLUMN provider_instance;
