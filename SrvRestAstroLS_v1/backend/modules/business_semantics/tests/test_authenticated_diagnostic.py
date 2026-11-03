"""Diagnostic mode is opt-in, with independent, operator-provided subjects."""
import json
import uuid

import pytest

from modules.business_semantics.authenticated_gate import load_manifest


def manifest(tmp_path):
    workspace = str(uuid.uuid4())
    identities = [dict(slot=s, email=s+'@example.invalid', workspace='other' if s == 'tenant-b' else 'telchi',
                       user_id=str(uuid.uuid4()), workspace_id=str(uuid.uuid4()) if s == 'tenant-b' else workspace)
                  for s in ('admin', 'tenant-b', 'user-a')]
    path = tmp_path / 'manifest.json'
    return path, identities


def test_diagnostic_enrollment_is_rejected_before_any_login(monkeypatch, tmp_path):
    from modules.business_semantics import authenticated_gate as gate
    output = tmp_path / 'result.json'
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setattr(gate, 'read_config', lambda _: {})
    def forbidden(*args, **kwargs):
        pytest.fail('diagnostic enrollment must fail before manifest, DB or subprocess')
    monkeypatch.setattr(gate, 'load_manifest', forbidden)
    monkeypatch.setattr(gate.subprocess, 'run', forbidden)
    monkeypatch.setattr(gate.sys, 'argv', ['gate', '--auth-config', str(tmp_path / 'config'),
        '--manifest', str(tmp_path / 'manifest'), '--output', str(output),
        '--mode', 'diagnostic-three', '--enroll-authorized'])
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 1
    assert json.loads(output.read_text())['status'] == 'FAIL'


def test_three_identities_require_explicit_mode(tmp_path):
    path, identities = manifest(tmp_path)
    path.write_text(json.dumps({'identities': identities}))
    with pytest.raises(ValueError, match='four_explicit'):
        load_manifest(path)
    assert [i['slot'] for i in load_manifest(path, 'diagnostic-three')] == ['user-a', 'tenant-b', 'admin']
    with pytest.raises(ValueError, match='unknown_ceremony_mode'):
        load_manifest(path, 'automatic')


@pytest.mark.parametrize('invalid', ['duplicate_subject', 'same_workspace', 'different_telchi_workspace',
                                      'missing_admin', 'extra_reader', 'empty_login', 'invalid_uuid'])
def test_diagnostic_rejects_invalid_manifests(tmp_path, invalid):
    path, identities = manifest(tmp_path)
    if invalid == 'duplicate_subject':
        identities[0]['user_id'] = identities[2]['user_id']
    elif invalid == 'same_workspace':
        identities[1]['workspace_id'] = identities[0]['workspace_id']
    elif invalid == 'different_telchi_workspace':
        identities[0]['workspace_id'] = str(uuid.uuid4())
    elif invalid == 'missing_admin':
        identities.pop(0)
    elif invalid == 'extra_reader':
        identities.append(dict(identities[2], slot='user-b', user_id=str(uuid.uuid4())))
    elif invalid == 'empty_login':
        identities[0]['email'] = ''
    else:
        identities[0]['user_id'] = 'not-a-uuid'
    path.write_text(json.dumps({'identities': identities}))
    with pytest.raises(ValueError):
        load_manifest(path, 'diagnostic-three')
