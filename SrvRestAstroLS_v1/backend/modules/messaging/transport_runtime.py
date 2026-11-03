"""Srv05-owned V1 sender and private callback lifecycle, admission closed by default.

Laboratory and DEV trust/credential profiles are disjoint. Changing TEAM360_ENV
cannot widen a trust root or permit legacy/global credentials.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import stat
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import uvicorn

from .providers.evolution.bound_provider import BoundEvolutionProvider
from .transport_app import create_transport_app
from .transport_callbacks import TransportCallbackReceiver
from .transport_profile import trust_profile


def private_document(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('Absolute private configuration required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        parent = path.parent.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536 or info.st_nlink != 1
                or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700):
            raise ValueError('Private configuration permissions invalid')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return json.load(stream)
    finally:
        os.close(fd)


class PeerIdentity:
    """Authenticate the local UDS peer before HTTP/body/signature processing."""
    def __init__(self, app, uid):
        self.app, self.uid = app, uid

    async def __call__(self, scope, receive, send):
        # Populated by our protocol, never by an HTTP header.
        if scope.get('type') == 'http' and scope.get('transport_peer_uid') != self.uid:
            await send({'type': 'http.response.start', 'status': 403, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})
            return
        await self.app(scope, receive, send)


from uvicorn.protocols.http.h11_impl import H11Protocol


class PrivateProtocol(H11Protocol):
    def connection_made(self, transport):
        peer = transport.get_extra_info('socket')
        try:
            _, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        except (OSError, AttributeError):
            transport.close()
            return
        # app_state is copied into each request scope by H11Protocol.
        self.app_state = {**self.app_state, 'peer_uid': uid}
        super().connection_made(transport)


class PrivateApplication:
    def __init__(self, app, uid):
        self.app, self.uid = app, uid

    async def __call__(self, scope, receive, send):
        scope['transport_peer_uid'] = scope.get('state', {}).get('peer_uid')
        await PeerIdentity(self.app, self.uid)(scope, receive, send)


class TransportRuntime:
    def __init__(self, config, document):
        if (set(document) != {'version', 'scope', 'revision', 'trust', 'signer', 'socket', 'admission_open'}
                or type(document['version']) is not int or document['version'] != 1 or type(document['revision']) is not int
                or document['revision'] < 1 or type(document['admission_open']) is not bool):
            raise ValueError('Invalid transport runtime configuration')
        trust = document['trust']
        trust_profile(trust)
        signer = Ed25519PrivateKey.from_private_bytes(base64.b64decode(document['signer'], validate=True))
        public = base64.b64encode(signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
        if public != trust['targets']['team360']['public_key']:
            raise ValueError('Transport signing identity mismatch')
        self.provider = BoundEvolutionProvider(config, scope=document['scope'], revision=document['revision'],
                                               trust=trust, signer=signer, admission_check=self.sender)
        self.document, self.server, self.task, self.sock = document, None, None, None
        self.admission_open = False
        self.path = Path(document['socket'])
        if not self.path.is_absolute() or self.path.parent.resolve() != self.path.parent:
            raise ValueError('Private callback path required')
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError('Private callback parent required')

    @classmethod
    def from_env(cls, config):
        path = os.environ.get('TEAM360_TRANSPORT_V1_CONFIG', '')
        if not path:
            raise ValueError('V1 runtime configuration required; legacy fallback forbidden')
        return cls(config, private_document(path))

    def sender(self):
        if not self.admission_open or not self.task or self.task.done():
            raise ValueError('V1 admission closed')
        return self.provider

    def close_admission(self):
        # Non-destructive rollback: retain the V1 callback/reconciliation process.
        self.admission_open = False

    async def start(self, pool, binding):
        from modules.db.transaction import transaction
        if self.task is not None:
            raise ValueError('V1 runtime already started')
        async with transaction(pool) as conn:
            await self.provider.check_transport_binding(conn, binding, require_active=self.document['admission_open'])
        receiver = TransportCallbackReceiver(trust=self.document['trust'], scope=self.document['scope'], binding=binding)
        app = create_transport_app(pool, {self.document['scope']['binding_id']: receiver})
        # Never unlink a preexisting socket: it may belong to another process.
        self.inode = None
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(str(self.path))
            self.inode = self.path.stat().st_ino
            os.chmod(self.path, 0o600)
            self.sock.listen(16)
            self.server = uvicorn.Server(uvicorn.Config(PrivateApplication(app, os.getuid()),
                http=PrivateProtocol, lifespan='off', access_log=False, log_level='error', limit_concurrency=8))
            self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
            for _ in range(200):
                if self.task.done():
                    await self.task
                    raise RuntimeError('Private callback stopped during startup')
                if self.server.started:
                    self.admission_open = self.document['admission_open']
                    return
                await asyncio.sleep(.01)
            raise RuntimeError('Private callback startup timeout')
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        self.close_admission()
        if self.server:
            self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.gather(self.task, return_exceptions=True), 10)
            except asyncio.TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        if self.sock:
            self.sock.close()
        if getattr(self, 'inode', None) is not None and self.path.exists():
            info = self.path.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_ino == self.inode:
                self.path.unlink()
        self.inode = None
        self.task = None
