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
