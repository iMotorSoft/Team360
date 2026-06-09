---
document_code: knowledge_base_as_a_service
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
topic_key: knowledge_base_service
node_path: "/automatizaciones/knowledge-base-service"
title: "Knowledge Base como servicio — alcance y límites"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - director_tecnico
  - gerente_tecnico
  - analista_tecnico
  - ceo
evidence_level: validated_by_source
evidence_sources:
  - team360_sales_diagnosis_package_manual
  - knowledge_scope_mapping
implementation_status: prototype
commercial_status: sellable_pilot
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
  Define qué se puede ofrecer como Knowledge Base gestionada,
  qué requisitos debe cumplir y cuáles son los límites actuales.
---

# Knowledge Base como servicio

## ¿Qué es una Knowledge Base gestionada?

Team360 puede ofrecer una knowledge base curada como servicio para clientes que necesitan un asistente con documentación propia: políticas, procedimientos, manuales, FAQ, catálogos, guías.

No es un RAG genérico sobre cualquier documento. Es una base curada con documentos approved, metadata, scopes, trazabilidad y revisión.

---

## Qué SÍ se puede ofrecer

- Asistente sobre documentos propios del cliente, con alcance definido.
- Curaduría de documentos: selección, clasificación, metadata.
- Ingesta controlada con script de carga/update.
- Retrieval sobre PostgreSQL/pgvector con scope aislado por cliente.
- Ciclo de revisión y reingesta con aprendizaje documentado.

---

## Qué requiere una knowledge base confiable

### Documentos fuente
- Formato Markdown (canónico) o PDF (solo lectura humana).
- Contenido claro, secciones autocontenidas, headings descriptivos.
- Sin datos sensibles, secretos ni credenciales.

### Metadata
- Por documento: document_type, area_key, topic_key, access_tags, visibility.
- Por capacidad: evidence_level, implementation_status, commercial_status, service_maturity, offer_decision.

### Scopes
- Un knowledge_scope por cliente/organización.
- Aislamiento total entre scopes (ver `[[aislamiento-scope-cliente]]`).
- Access tags por rol.

### Trazabilidad
- `last_validated_at`: fecha de última validación.
- `validated_by`: quién validó.
- `evidence_sources`: fuentes de evidencia.
- `review_cycle`: cada cuánto se revisa.

### Revisión
- Los documentos approved no son inmutables. Siguen un ciclo: prueba → aprendizaje → curaduría → update → nueva prueba.
- Los aprendizajes de uso no entran automáticamente a approved. Deben pasar por curaduría.

---

## Límites actuales

- No hay interfaz de administración de knowledge (admin UI). La carga es mediante script controlado.
- No hay Milvus ni ArangoDB. El retrieval usa PostgreSQL/pgvector.
- El corpus actual es pequeño (~40 chunks). La calidad del retrieval mejora con más contenido chunkable, no con cambio de BD.
- No hay re-embedding automático. Los embeddings se generan con script controlado.
- No hay versioneo automático de documentos. El versionado es manual por metadata.

---

## Qué NO se debe prometer

- "Cualquier documento funciona." No. Los documentos deben estar curados, con metadata y alcance claro.
- "Se integra con cualquier fuente de datos." No. La ingesta es sobre documentos curados, no sobre bases de datos externas.
- "Actualización en tiempo real." No. La reingesta es controlada, no automática.
- "Escala infinitamente." El retrieval actual es PostgreSQL/pgvector. Escala hasta 50k-100k chunks antes de evaluar Milvus.

---

## Cómo responder comercialmente

**"¿Pueden hacer un asistente con mis documentos?"**
"Sí. Ofrecemos knowledge base gestionada con documentos curados, metadata, scopes aislados y retrieval sobre PostgreSQL."

**"¿Qué documentos puedo subir?"**
"Documentos en Markdown preferentemente. Deben estar curados: contenido claro, sin datos sensibles, con metadata. Nosotros ayudamos con la curaduría."

**"¿Se actualiza automáticamente?"**
"No. La ingesta es controlada. Cuando tengas documentos nuevos o actualizados, coordinamos una reingesta."

**"¿Soporta muchos documentos?"**
"La plataforma actual maneja eficientemente hasta decenas de miles de chunks. Para volúmenes mayores, evaluamos escalar la infraestructura."

---

## Referencias

- `[[aislamiento-scope-cliente]]`: Aislamiento por cliente
- `[[reglas-anti-overpromise]]`: Reglas vinculantes
- `[[alcance-productivo-inicial]]`: Qué se puede vender hoy
- `[[team360_sales_diagnosis_package_manual]]`: Ciclo evolutivo del knowledge
