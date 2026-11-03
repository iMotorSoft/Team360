"""Password ceremony feeding existing Console PASETO, never caller-selected identity."""
import asyncio
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from modules.console.auth import ConsoleAuthError, verify_console_access_token
from modules.console.login_repository import ConsoleLoginRepository
from modules.console.passwords import DUMMY_HASH, hash_password, verify_password
from modules.security.paseto_tokens import issue_paseto_v4_public


class ConsoleLoginService:
    def __init__(self, settings, repository=None):
        if (not settings.enabled or not settings.private_key_pem or not settings.public_key_pem
                or not 1 <= settings.ttl_seconds <= 900):
            raise ValueError('explicit_persistent_issuer_required')
        private_key = serialization.load_pem_private_key(settings.private_key_pem.encode(),password=None)
        public_key = serialization.load_pem_public_key(settings.public_key_pem.encode())
        if (not isinstance(private_key,Ed25519PrivateKey)
                or private_key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
                != public_key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)):
            raise ValueError('matching_persistent_ed25519_keys_required')
        self.settings = settings
        self.repository = repository or ConsoleLoginRepository()
        self.kdf_slots = asyncio.Semaphore(2)

    async def enroll(self, conn, *, user_id, workspace_id, password):
        actor = await self.repository.actor(conn,user_id,workspace_id)
        if not actor:
            raise PermissionError('existing_active_user_required')
        async with self.kdf_slots:
            encoded = await asyncio.to_thread(hash_password,password)
        await self.repository.enroll(conn,user_id,encoded)
        await self.repository.audit(conn,user_id,workspace_id,'enroll')

    async def login(self, conn, *, workspace_slug, email, password):
        # Invalid, unknown, disabled, cross-workspace and locked accounts all return None.
        if (not isinstance(workspace_slug,str) or not isinstance(email,str)
                or not 0 < len(workspace_slug) <= 100 or not 0 < len(email) <= 254
                or not isinstance(password,str) or len(password) > 256):
            return None
        workspace_slug, email = workspace_slug.strip(), email.strip().lower()
        key = hashlib.sha256((workspace_slug+'\0'+email).encode()).hexdigest()
        if not await self.repository.throttle(conn,key):
            return None
        row = await self.repository.credential(conn,workspace_slug,email)
        encoded = row['password_hash'] if row and not row['disabled'] else DUMMY_HASH
        async with self.kdf_slots:
            valid = await asyncio.to_thread(verify_password,password,encoded)
        if not valid or not row or row['disabled']:
            await self.repository.failed(conn,key)
            return None  # Caller must commit failure counters, not raise/rollback.
        cfg = self.settings
        token = issue_paseto_v4_public(
            {'sub':'user:'+row['user_id'],'user_id':row['user_id'],
             'workspace_id':row['workspace_id'],'amr':['pwd'],
             'credential_version':row['credential_version']},
            private_key_pem=cfg.private_key_pem,key_id=cfg.key_id,
            ttl_seconds=cfg.ttl_seconds,issuer=cfg.issuer,token_type='console_access')
        await self.repository.succeeded(conn,key)
        await self.repository.audit(conn,row['user_id'],row['workspace_id'],'login')
        return token

    async def verify_session(self, conn, token, *, workspace_id):
        cfg = self.settings
        principal = verify_console_access_token(token,public_keys_by_id={cfg.key_id:cfg.public_key_pem},
                                                 issuer=cfg.issuer,leeway_seconds=0)
        claims = principal.claims
        if (claims.get('amr') != ['pwd'] or claims.get('workspace_id') != workspace_id
                or type(claims.get('credential_version')) is not int
                or not await self.repository.session_active(conn,principal.user_id,workspace_id,claims['credential_version'])):
            raise ConsoleAuthError('inactive_or_wrong_scope_session')
        return principal
