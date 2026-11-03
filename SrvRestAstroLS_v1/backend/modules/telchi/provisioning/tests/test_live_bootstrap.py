"""Cheap contracts for the narrowly authorized local bootstrap; no live DB writes."""
from pathlib import Path
from uuid import uuid4
import os

import pytest
from modules.telchi.provisioning.live_cli import AUTHORIZATION, validate, digest
from modules.telchi.provisioning.live_repository import EMAILS, GLOBAL_PERMISSIONS, LiveRepository
from modules.telchi.provisioning.repository import Conflict


def manifest():
    return dict(authorization=AUTHORIZATION, environment='dev', operator_uid=os.getuid(),
                target=dict(database='team360', server_port=5432),
                platform_workspace_id=str(uuid4()), global_role_id=str(uuid4()),
                user_ids=[str(uuid4()) for _ in range(3)],
                seed=dict(workspace_id=str(uuid4()), organization_id=str(uuid4()), stage='scaffold'))


@pytest.mark.parametrize('field,value', [('authorization', 'not-approved'), ('environment', 'pro'), ('operator_uid', -1)])
def test_wrong_local_authorization_rejected(field, value):
    m = manifest()
    m[field] = value
    with pytest.raises(Conflict):
        validate(m)


def test_other_database_rejected():
    m = manifest()
    m['target']['database'] = 'other'
    with pytest.raises(Conflict):
        validate(m)


def test_duplicate_identity_rejected():
    m = manifest()
    m['user_ids'][1] = m['user_ids'][0]
    with pytest.raises(Conflict):
        validate(m)


def test_grants_input_rejected():
    m = manifest()
    m['seed']['stage'] = 'grants'
    with pytest.raises(Conflict):
        validate(m)


def test_arbitrary_identity_rejected_before_sql():
    import asyncio
    with pytest.raises(Conflict):
        asyncio.run(LiveRepository().identity(None, 'unapproved@example.invalid', str(uuid4()), str(uuid4()), []))


def test_fixed_catalog_and_no_password_or_token_writes():
    assert len(EMAILS) == 3
    assert GLOBAL_PERMISSIONS == ('user.manage', 'role.manage', 'audit.view')
    from modules.telchi.provisioning import live_repository
    source = Path(live_repository.__file__).read_text()
    assert 'issue_console' not in source
    assert 'password_hash' not in source
    assert 'messaging_phone_bindings' not in source


def test_digest(tmp_path):
    import hashlib
    p = tmp_path / 'fixture'
    p.write_bytes(b'fixture')
    assert digest(p) == hashlib.sha256(b'fixture').hexdigest()
