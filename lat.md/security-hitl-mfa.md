# Security HITL MFA

Team360 must not promise bypass of security controls.

Security gates are business facts that must be modeled, surfaced and audited.

## MFA Modes

```text
HITL_CODE_INJECTION
REMOTE_MIRRORING
HARDWARE_PROXIMITY
NOT_AUTOMATABLE_REMOTE
```

## HITL Code Injection

Can be assisted with an authorized human:

- SMS OTP;
- email OTP;
- TOTP;
- backup codes.

The user provides the code. Team360 records who approved, when, for what operation and with which correlation_id.

## Remote Mirroring

Requires human presence:

- QR approval;
- push approval;
- mobile app approval.

Team360 can prepare the operation and wait for user approval. It must not sell full autonomy.

## Hardware Proximity

Not suitable for remote SaaS automation:

- FIDO2;
- YubiKey;
- smart card;
- FaceID;
- TouchID;
- hardware token;
- non-exportable certificates;
- strong banking signature.

These cases require manual action, official API, on-premise controlled execution or consulting.

## Blocked Actions

Blocked by default unless formally designed with approvals and audit:

- `bypass_mfa`;
- `post_financial_transaction`;
- `delete_record`;
- `change_prices`;
- critical ERP write operations;
- mass irreversible changes.

## Classifier Guidance

If a process asks for bypassing MFA, hardware keys, biometrics, strong signatures or aggressive anti-bot protection, classify as `not_recommended`, `blocked`, or assisted with HITL where legally and operationally valid.
