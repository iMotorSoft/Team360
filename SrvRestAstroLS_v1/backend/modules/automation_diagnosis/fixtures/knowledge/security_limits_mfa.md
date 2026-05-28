# Limites De Seguridad, MFA Y HITL

Team360 no debe prometer bypass de seguridad. Si un sistema exige MFA, aprobacion humana, hardware o biometria, el flujo debe clasificarse con cuidado.

## HITL Code Injection

SMS OTP, email OTP, TOTP y backup codes pueden automatizarse de forma asistida si el usuario autorizado introduce el codigo y queda auditado.

El sistema debe registrar quien aprobo, cuando, para que operacion y con que correlation_id.

## Remote Mirroring

QR dinamico, push approval y aprobacion en app movil requieren usuario presente. Team360 puede preparar la operacion y esperar aprobacion, pero no debe vender autonomia total.

## Hardware Proximity

FIDO2, YubiKey, smart card, FaceID, TouchID, firma fuerte y certificado no exportable no deben tratarse como automatizacion remota directa.

En estos casos la recomendacion es proceso manual, API oficial, ejecucion on-premise controlada o consultoria.

## Acciones Bloqueadas

Acciones bloqueadas por defecto: bypass_mfa, post_financial_transaction, delete_record, change_prices sin aprobacion, escritura ERP critica y borrado masivo.
