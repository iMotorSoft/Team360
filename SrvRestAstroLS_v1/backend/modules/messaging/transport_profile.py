"""Explicit trust/credential classes. Environment variables never widen trust."""
import hashlib
import re


def trust_profile(trust):
    if trust.get('version') != 1:
        raise ValueError('Invalid transport trust')
    if trust.get('laboratory_only') is True and trust.get('profile', 'laboratory') == 'laboratory':
        return 'laboratory'
    if trust.get('laboratory_only') is False and trust.get('profile') == 'dev':
        return 'dev'
    raise ValueError('Invalid transport trust profile')


def credential_verifier(secret, profile):
    prefix, domain = {'laboratory': ('t360labv1_', 'lab'), 'dev': ('t360devv1_', 'dev')}[profile]
    if not isinstance(secret, str) or not re.fullmatch(prefix+r'[A-Za-z0-9_-]{43}', secret):
        raise ValueError('Binding credential class mismatch')
    return hashlib.sha256(('team360.transport.'+domain+'.v1\x00'+secret).encode()).hexdigest()
