---
document_code: alcance_productivo_inicial
document_type: guide
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
area_key: automatizaciones
topic_key: alcance_inicial
node_path: "/automatizaciones/alcance-inicial"
title: "Alcance productivo inicial — qué se puede vender hoy"
visibility: public
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
  - director_comercial
evidence_level: validated_by_source
evidence_sources:
  - team360_sales_diagnosis_package_manual
  - breaking_points_lab_results
implementation_status: prototype
commercial_status: core_offer
service_maturity: CORE_VALIDADO
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
  Documento que define el alcance productivo inicial del diagnosis
  package. Qué puede hacer el asistente hoy, con qué límites y
  qué no debe prometerse. Basado en el test ácido de retrieval
  que confirmó que el punto de ruptura actual es content_gap,
  no el backend vectorial.
---

# Alcance productivo inicial

## Lo que el asistente SÍ puede hacer hoy

### Conversación guiada
El asistente puede mantener una conversación natural para entender la situación del cliente, detectar contexto y guiar el diagnóstico.

### Extracción de slots mínimos
Puede detectar y extraer campos clave de la conversación: industria, proceso, herramientas actuales, dolor principal, urgencia. Ver la lista completa en `[[team360_sales_diagnosis_package_manual]]`.

### Diagnóstico útil
Puede clasificar la oportunidad del cliente en: automatizable, vendible hoy, piloto, oportunidad futura, requiere revisión humana.

### Orientación concreta
Después del diagnóstico, puede sugerir pasos concretos que el vendedor puede seguir. No ejecuta acciones automáticas.

### Recuperación desde knowledge approved
Puede recuperar chunks de documentos approved para responder preguntas sobre capacidades, límites, reglas y procedimientos.

### FAQ inteligente
Puede responder preguntas frecuentes si el contenido del negocio está cargado en el knowledge scope.

### Captura de consulta
Puede capturar la consulta del cliente si está dentro del flujo definido y el alcance lo permite.

### Derivación humana con resumen
Puede preparar un resumen del caso para derivar a un humano, si esa funcionalidad está implementada en el paquete/proyecto específico.

---

## Lo que el asistente NO debe hacer hoy

- ❌ No prometer acciones automáticas reales. El diagnóstico termina en orientación, no en ejecución.
- ❌ No ejecutar Step-to-Action. Es planned_extension.
- ❌ No capturar leads de forma productiva general. Es planned_extension.
- ❌ No hacer handoff automático a WhatsApp. Es planned_extension.
- ❌ No generar diagnostic_code. Es planned_extension.
- ❌ No integrar con CRM automáticamente sin configuración específica.
- ❌ No ejecutar workflows sobre sistemas externos.
- ❌ No enviar campañas WhatsApp automáticas.
- ❌ No gestionar agenda/turnos automáticamente.
- ❌ No reemplazar el juicio humano en decisiones críticas.
- ❌ No inventar información que no esté en el knowledge.

---

## Cuándo una capacidad es "vendible hoy"

Una capacidad es vendible hoy si cumple TODAS estas condiciones:

1. Está documentada en approved con metadata completa.
2. Tiene implementation_status distinto de `not_implemented`.
3. Tiene commercial_status distinto de `not_offered` y `future_package`.
4. Tiene service_maturity `CORE_VALIDADO` o `PILOTO_VALIDADO`.
5. Tiene offer_decision `sellable_now` o `pilot`.
6. Existe evidencia de que funciona (evidence_level validated_by_source, validated_by_pilot o validated_by_production).
7. No depende de integraciones no existentes para el cliente específico.

---

## Límites del alcance productivo inicial

- El corpus actual tiene ~40 chunks. El retrieval es funcional para conceptos presentes en el corpus.
- Fuera del corpus, el sistema debe decir "no tengo información" en lugar de inventar.
- El test ácido mostró que 20/25 preguntas adversariales fallaron por content_gap. Esto NO es problema del backend vectorial. Es falta de contenido chunkable.
- A medida que se agreguen más documentos approved, el retrieval cubrirá más conceptos sin cambiar la infraestructura.

---

## Cómo responder preguntas sobre alcance

**"¿Qué puede hacer el asistente?"**
"Puedo mantener una conversación para entender tu situación, diagnosticar oportunidades de automatización, clasificar tu caso y sugerir pasos concretos. Todo basado en el knowledge curado de Team360."

**"¿Puede ejecutar acciones automáticas?"**
"No. El diagnóstico actual termina en orientación y recomendación. La ejecución automática de acciones es una capacidad futura."

**"¿Puede conectarse con mi CRM?"**
"Puedo referir información sobre integraciones CRM si está documentada en el knowledge. La integración real requiere evaluación técnica caso por caso."

**"¿Puede reemplazar a un vendedor?"**
"No. El asistente es una herramienta de diagnóstico y orientación. La decisión comercial final y la ejecución requieren intervención humana."

---

## Referencias

- `[[reglas-anti-overpromise]]`: Reglas vinculantes para no prometer de más
- `[[capacidades-futuras-e-integraciones]]`: Lo que no está listo hoy
- `[[team360_sales_diagnosis_package_manual]]`: Manual completo del paquete
- `[[knowledge-base-as-a-service]]`: Knowledge Base como servicio
