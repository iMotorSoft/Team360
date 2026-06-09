---
document_code: whatsapp_limites_e_integraciones
document_type: reference
version: "1.0"
status: approved
ingestion_status: ready
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360_live
workspace_code: team360_public_site
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: integraciones
topic_key: whatsapp_limites
node_path: "/integraciones/whatsapp-limites"
title: "WhatsApp — límites comerciales e integraciones"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
  - director_comercial
  - director_tecnico
evidence_level: validated_by_source
evidence_sources:
  - team360_sales_diagnosis_package_manual
  - paquetes_whatsapp_inteligente
implementation_status: prototype
commercial_status: future_package
service_maturity: PILOTO_VALIDADO
offer_decision:
  - sellable_now
  - pilot
review_cycle: per_release
last_validated_at: 2026-06-09
validated_by: Team360
related_pilots:
  - team360_live_public_home
related_clients:
  - team360_live
risk_level: medium
approval_notes: >
  Límites y diferenciación entre WhatsApp como servicio comercial
  (paquetes WhatsApp inteligente) y WhatsApp handoff automático
  como planned_extension. Este documento existe para evitar que
  el retrieval confunda ambos conceptos.
---

# WhatsApp — límites comerciales e integraciones

## Diferenciación fundamental

Team360 tiene DOS líneas relacionadas con WhatsApp. Es vital no confundirlas:

| Aspecto | WhatsApp service offer | WhatsApp handoff automático |
|---------|----------------------|---------------------------|
| **¿Qué es?** | Paquete comercial de WhatsApp inteligente | Capacidad técnica dentro del diagnosis package |
| **¿Está disponible?** | Sí, como servicio configurable | No, es planned_extension |
| **¿Cómo se vende?** | Planes 1-4 con alcance definido | No se vende |
| **¿Requiere integración?** | Sí, según el plan | Sí, múltiples componentes |
| **¿Depende del diagnosis package?** | No, es independiente | Sí, es parte del flujo de diagnóstico |
| **Documento de referencia** | `[[paquetes-whatsapp-inteligente]]` | `[[capacidades-futuras-e-integraciones]]` |

---

## WhatsApp service offer (disponible)

Ver `[[paquetes-whatsapp-inteligente]]` para la descripción completa de los 4 planes.

Reglas:
- Se ofrece como servicio profesional configurable, no como producto automático.
- Cada implementación requiere relevamiento, configuración y prueba.
- No incluye acciones automáticas sobre sistemas externos no contratados.
- La integración con sistemas del cliente se evalúa caso por caso.

---

## WhatsApp handoff automático (NO disponible)

El handoff automático desde el diagnosis package hacia WhatsApp es planned_extension. Esto significa:

- No existe un worker que genere un mensaje automático de WhatsApp post-diagnóstico.
- No existe un diagnostic_code asociado a la conversación para handoff.
- No existe una URL o mensaje preconfigurado de continuidad comercial.
- El MVP actual termina en orientación concreta, no en handoff.

**NO confundir con:** la capacidad de un paquete WhatsApp de derivar a un humano. Eso es derivación dentro del servicio WhatsApp, no handoff automático desde el diagnosis package.

---

## Reglas de engagement con WhatsApp

### Sí está permitido
- Ofrecer paquetes de WhatsApp inteligente como servicio comercial.
- Describir qué incluye cada plan con alcance y límites.
- Mencionar que la integración con sistemas del cliente es posible con evaluación técnica.
- Indicar que la derivación humana está disponible como parte del servicio.

### No está permitido
- Decir que "WhatsApp handoff automático está listo" (es planned_extension).
- Decir que "WhatsApp se integra automáticamente con el diagnóstico" (no existe).
- Prometer campañas masivas sin proveedor, plantillas y cumplimiento.
- Prometer agenda automática sin integración real.
- Decir que "cualquier CRM se integra automáticamente" (depende de evaluación técnica).

---

## Dependencias técnicas de WhatsApp como servicio

Para cualquier paquete WhatsApp se requiere:
- Número de WhatsApp Business del cliente (obligatorio)
- Configuración del proveedor de mensajería (Twilio, Gupshup, 360dialog, WATI, etc.)
- Contenido del negocio (FAQ, servicios, horarios, precios — lo provee el cliente)
- Definición de reglas de derivación humana
- Configuración de plantillas de mensajes (para campañas o respuestas estructuradas)

Para integración con sistemas del cliente se requiere además:
- Acceso a API del sistema (CRM, ERP, calendario)
- Mapeo de campos y flujos
- Autenticación y autorización
- Pruebas de integración

---

## Cómo responder preguntas comerciales sobre WhatsApp

**"¿Conecta con WhatsApp?"**
"Sí, ofrecemos paquetes de WhatsApp inteligente como servicio. Podemos configurar un canal para tu negocio con el alcance que necesites."

**"¿Ya está integrado con WhatsApp?"**
"Como plataforma, tenemos capacidad de integrar WhatsApp. Como servicio, ofrecemos paquetes específicos. No es una integración automática para todos los clientes."

**"¿El diagnóstico puede derivar a WhatsApp?"**
"El handoff automático del diagnóstico a WhatsApp es una capacidad futura. Pero como servicio aparte, podemos ofrecerte un paquete WhatsApp con derivación humana incluida."

**"¿Puedo comprar WhatsApp + diagnóstico juntos?"**
"Sí, son compatibles. El diagnóstico de Team360 y un paquete WhatsApp pueden coexistir. Pero no están integrados automáticamente. Cada uno se configura por separado."

---

## Referencias

- `[[paquetes-whatsapp-inteligente]]`: Descripción completa de los 10 paquetes y 4 planes
- `[[capacidades-futuras-e-integraciones]]`: WhatsApp handoff como planned_extension
- `[[reglas-anti-overpromise]]`: Reglas vinculantes, especialmente Regla 6
- `[[team360_sales_diagnosis_package_manual]]`: Contexto del diagnosis package
