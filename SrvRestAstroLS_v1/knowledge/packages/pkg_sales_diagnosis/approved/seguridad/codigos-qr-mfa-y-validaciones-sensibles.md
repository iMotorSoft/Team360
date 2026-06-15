---
document_code: codigos_qr_mfa_validaciones
document_type: policy
version: "1.0"
status: approved
ingestion_status: ready
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360_live
workspace_code: team360_public_site
area_key: seguridad
topic_key: validaciones_sensibles
node_path: "/seguridad/codigos-qr-mfa-validaciones-sensibles"
title: "Códigos QR, MFA y validaciones sensibles — límites del diagnóstico"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-14
access_tags:
  - ceo
  - director_comercial
  - director_tecnico
  - gerente_tecnico
  - analista_tecnico
evidence_level: validated_by_source
implementation_status: prototype
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
review_cycle: per_release
last_validated_at: 2026-06-14
validated_by: Team360
risk_level: high
approval_notes: >
  Política que define cómo el diagnóstico debe responder cuando una aplicación
  del cliente requiere validaciones sensibles como QR, MFA, Face ID o tokens.
  Team360 no evade, intercepta ni automatiza estos controles.
---

# Códigos QR, MFA y validaciones sensibles

## Propósito

Definir qué puede y qué no puede hacer el diagnóstico de Team360 cuando una
aplicación del cliente requiere validaciones sensibles como códigos QR, MFA,
Face ID, tokens, OTP o aprobaciones manuales.

## Regla central

Team360 no pide, guarda, intercepta, genera ni evade mecanismos de validación
sensible. Cuando una app exige una validación de este tipo, la acción debe ser
realizada por el usuario autorizado en el canal correspondiente.

El diagnóstico puede preparar contexto, guiar los pasos necesarios y registrar
el estado de la operación, pero no puede saltar ni automatizar el control de
seguridad.

## Qué puede hacer Team360

- Detectar que una aplicación requiere validación sensible.
- Indicar qué tipo de validación se necesita (QR, MFA, token, Face ID, etc.).
- Guiar al usuario autorizado paso a paso para completar la validación.
- Registrar en el diagnóstico que la validación fue requerida y si se completó.
- Diferenciar entre validaciones automatizables y las que requieren
  intervención humana (human_review_required).

## Qué no puede hacer Team360

- Generar, solicitar o interceptar códigos QR, tokens, OTP, PINs o
  credenciales de acceso.
- Completar un flujo MFA/2FA en nombre del usuario.
- Almacenar códigos de verificación, biometric data, Face ID tokens ni
  ninguna credencial sensible.
- Automatizar el envío de códigos de verificación a terceros.
- Eludir controles de seguridad de la aplicación del cliente.
- Prometer que diagnostic_code o validación automática están disponibles
  como funcionalidad activa. Siguen siendo planned_extension.

## Señales de human_review_required

El diagnóstico debe marcar `human_review_required` cuando:

- La aplicación requiere MFA, 2FA, Face ID o validación biométrica.
- Se necesita un código QR, token o código de verificación que solo el
  usuario autorizado puede obtener.
- La operación requiere aprobación manual de un responsable.
- La aplicación exige una credencial que Team360 no tiene acceso a generar.

## Cómo debe responder el diagnóstico

Ante una consulta sobre validaciones sensibles, el diagnóstico debe:

1. Identificar el tipo de validación requerida.
2. Explicar que Team360 no puede realizar esa validación automáticamente.
3. Indicar qué debe hacer el usuario autorizado.
4. Si aplica, marcar `human_review_required`.
5. Si la consulta menciona diagnostic_code o QR automático, aclarar que
   no está activo y que sigue siendo planned_extension.

## Términos de búsqueda / aliases

- QR, código QR
- MFA, 2FA, autenticación multifactor
- Face ID, reconocimiento facial, biometría
- token, token de seguridad, OTP, código de verificación
- PIN, clave dinámica
- diagnostic_code, código de diagnóstico
- usuario autorizado
- human_review_required, revisión manual
- validación sensible, credencial, autenticación
- paso seguro, verificación de identidad
