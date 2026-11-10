"""Read-only checks for the manually approved Telchi WhatsApp DEV session."""
import hashlib

from modules.messaging.handlers import ChannelContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.messaging.repository import MessagingRepository


async def check_session(conn, settings, evolution, approval):
    if hashlib.sha256(settings.authorized_sender.encode()).hexdigest() != approval.get('sender_sha256'):
        raise PermissionError('approved_pilot_line_mismatch')
    binding = await MessagingRepository().binding(
        conn, workspace_slug=settings.workspace_slug, channel_alias=settings.channel_alias,
        provider='evolution', instance=evolution.instance)
    if (binding.environment != 'dev' or binding.module != 'telchi'
            or binding.tenant_id != 'telchi' or binding.workspace_id != approval['workspace_id']):
        raise PermissionError('session_binding_mismatch')
    channel = ChannelContext(binding.channel_id, 'evolution', evolution.instance,
        binding.receiver_context, binding.tenant_id, binding.workspace_id, 'telchi', 'dev')
    identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
    if (identity is None or identity.user_id != approval['user_id']
            or identity.tenant_id != binding.tenant_id or identity.workspace_id != binding.workspace_id
            or identity.environment != binding.environment):
        raise PermissionError('session_identity_denied')
    user = await (await conn.execute(
        "SELECT id FROM core_users WHERE id=%s AND workspace_id=%s AND lower(trim(email))=%s AND status='active'",
        (identity.user_id, binding.workspace_id, 'devfull@telchiai.com'))).fetchone()
    if not user:
        raise PermissionError('session_pilot_mismatch')
    await MessagingRepository().validate_transport_schema(conn)
    await PhoneIdentityRepository().validate_schema(conn)
    return binding


async def recovery_inventory(conn, binding, since):
    """No payloads or writes; all replayable work fences administrative closure.

    Legacy uncertain rows pre-dating the session remain evidence, never retries.
    Current DurableWorker only selects rows carrying durable_job.
    """
    return await (await conn.execute('''SELECT
        count(*) FILTER (WHERE payload_jsonb ? 'durable_job' AND
            COALESCE(payload_jsonb->'durable_job'->>'state','') NOT IN
                ('OUTBOUND_ACCEPTED','FAILED_FINAL','CANCELED')) AS durable_pending,
        count(*) FILTER (WHERE direction='outbound' AND event_type='message' AND
            (status='pending' OR payload_jsonb->>'initial_result'='dispatch_intent')) AS resumable_outbound,
        count(*) FILTER (WHERE direction='outbound' AND transport_status='unknown'
            AND created_at_utc >= %s) AS session_uncertain_outbound,
        count(*) FILTER (WHERE direction='outbound' AND transport_status='unknown'
            AND created_at_utc < %s) AS older_uncertain_outbound,
        count(*) FILTER (WHERE direction='inbound' AND status='running'
            AND created_at_utc >= %s) AS session_running_inbound,
        count(*) FILTER (WHERE direction='inbound' AND status='running'
            AND created_at_utc < %s AND NOT payload_jsonb ? 'durable_job') AS older_legacy_running
        FROM message_events WHERE workspace_id=%s AND channel_id=%s AND provider_instance=%s''',
        (since, since, since, since, binding.workspace_id, binding.channel_id,
         binding.storage_instance))).fetchone()
