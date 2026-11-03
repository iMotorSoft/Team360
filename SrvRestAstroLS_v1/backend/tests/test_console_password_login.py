"""Local synthetic credential tests; never activates a human identity."""
import asyncio
from pathlib import Path
from dataclasses import replace

import pytest

from modules.console.auth import ConsoleAuthError, verify_console_access_token
from modules.console.login_cli import private_path, write_private
from modules.console.login_service import ConsoleLoginService
from modules.console.passwords import hash_password, verify_password
from modules.security.paseto_tokens import PasetoKeyPair, PasetoConsoleSettings, issue_paseto_v4_public

PAIR = PasetoKeyPair.generate('password-fixture')
SETTINGS = PasetoConsoleSettings(enabled=True,issuer='fixture-console',key_id=PAIR.key_id,
    private_key_pem=PAIR.private_pem,public_key_pem=PAIR.public_pem,ttl_seconds=300)
PASSWORD = 'synthetic test password 1'


@pytest.fixture(scope='module')
def encoded():
    return hash_password(PASSWORD)


def test_scrypt_correct_wrong_and_salted(encoded):
    assert verify_password(PASSWORD,encoded)
    assert not verify_password('wrong password',encoded)
    assert hash_password(PASSWORD) != encoded
    assert PASSWORD not in encoded


@pytest.mark.parametrize('password',['short','x'*257,None])
def test_password_enrollment_bounds(password):
    with pytest.raises(ValueError):
        hash_password(password)


@pytest.mark.parametrize('value',['invalid','scrypt$99999999999$8$1$x$x','scrypt$131072$8$1$bad$bad'])
def test_corrupt_hash_does_not_allocate_arbitrary_work(value):
    assert not verify_password(PASSWORD,value)


def test_issuer_never_generates_fallback_keys():
    for cfg in (replace(SETTINGS,private_key_pem=None),replace(SETTINGS,public_key_pem=None),
                replace(SETTINGS,ttl_seconds=901),replace(SETTINGS,enabled=False),
                replace(SETTINGS,public_key_pem=PasetoKeyPair.generate('other').public_pem)):
        with pytest.raises(ValueError):
            ConsoleLoginService(cfg)


class Repo:
    def __init__(self,encoded):
        self.row = dict(user_id='user1',workspace_id='workspace1',password_hash=encoded,credential_version=1,disabled=False)
        self.failures=0
        self.audit_events=[]
        self.active=True
    async def throttle(self,conn,key):
        return self.failures < 5
    async def credential(self,conn,workspace,email):
        return self.row if (workspace,email)==('telchi_dev','fixture@example.test') else None
    async def failed(self,conn,key):
        self.failures+=1
    async def succeeded(self,conn,key):
        self.failures=0
    async def audit(self,conn,user,workspace,op):
        self.audit_events.append((user,workspace,op))
    async def session_active(self,conn,user,workspace,version):
        return self.active and (user,workspace,version)==('user1','workspace1',self.row['credential_version'])


def test_password_authenticates_then_existing_console_verifier_accepts(encoded):
    async def run():
        repo=Repo(encoded);service=ConsoleLoginService(SETTINGS,repo)
        token=await service.login(None,workspace_slug='telchi_dev',email=' Fixture@Example.Test ',password=PASSWORD)
        p=await service.verify_session(None,token,workspace_id='workspace1')
        assert p.user_id=='user1' and p.claims['amr']==['pwd']
        assert repo.audit_events==[('user1','workspace1','login')]
        assert 'password_hash' not in p.claims
        repo.row['credential_version']=2
        with pytest.raises(ConsoleAuthError):
            await service.verify_session(None,token,workspace_id='workspace1')
    asyncio.run(run())


@pytest.mark.parametrize('case',['wrong_password','unknown','wrong_workspace','disabled'])
def test_denial_uniform_no_token_no_success_audit(encoded,case):
    async def run():
        repo=Repo(encoded);service=ConsoleLoginService(SETTINGS,repo)
        if case=='disabled':repo.row['disabled']=True
        result=await service.login(None,workspace_slug='other' if case=='wrong_workspace' else 'telchi_dev',
            email='unknown@example.test' if case=='unknown' else 'fixture@example.test',
            password='bad' if case=='wrong_password' else PASSWORD)
        assert result is None and repo.failures==1 and repo.audit_events==[]
    asyncio.run(run())


def test_locked_account_rejected_before_kdf(encoded,monkeypatch):
    async def run():
        repo=Repo(encoded);repo.failures=5
        monkeypatch.setattr('modules.console.login_service.verify_password',lambda *a:pytest.fail('locked KDF'))
        assert await ConsoleLoginService(SETTINGS,repo).login(None,workspace_slug='telchi_dev',email='fixture@example.test',password=PASSWORD) is None
    asyncio.run(run())


def test_generic_bootstrap_token_and_cross_workspace_rejected(encoded):
    async def run():
        service=ConsoleLoginService(SETTINGS,Repo(encoded))
        generic=issue_paseto_v4_public({'sub':'user:user1','user_id':'user1'},private_key_pem=PAIR.private_pem,
            key_id=PAIR.key_id,ttl_seconds=300,issuer=SETTINGS.issuer,token_type='console_access')
        with pytest.raises(ConsoleAuthError):await service.verify_session(None,generic,workspace_id='workspace1')
        token=await service.login(None,workspace_slug='telchi_dev',email='fixture@example.test',password=PASSWORD)
        with pytest.raises(ConsoleAuthError):await service.verify_session(None,token,workspace_id='other')
    asyncio.run(run())


def test_console_subject_must_match_user_id():
    token=issue_paseto_v4_public({'sub':'user:other','user_id':'user1'},private_key_pem=PAIR.private_pem,
        key_id=PAIR.key_id,ttl_seconds=300,issuer=SETTINGS.issuer,token_type='console_access')
    with pytest.raises(ConsoleAuthError):
        verify_console_access_token(token,public_keys_by_id={PAIR.key_id:PAIR.public_pem},issuer=SETTINGS.issuer)


def test_private_files_exclusive_and_no_repository_output(tmp_path):
    tmp_path.chmod(0o700)
    path=write_private(tmp_path/'session','synthetic test token')
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):write_private(path,'replacement')
    with pytest.raises(PermissionError):private_path(Path(__file__).parent/'secret')
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(PermissionError):private_path(link,existing=True)
