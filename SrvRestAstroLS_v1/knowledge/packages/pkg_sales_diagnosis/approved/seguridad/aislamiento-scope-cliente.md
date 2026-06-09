---
document_code: aislamiento_scope_cliente
document_type: policy
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
area_key: seguridad
topic_key: aislamiento_scope
node_path: "/seguridad/aislamiento-scope-cliente"
title: "Aislamiento por scope y cliente — políticas de seguridad"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - ceo
  - director_comercial
  - director_tecnico
  - gerente_tecnico
  - analista_tecnico
evidence_level: validated_by_source
evidence_sources:
  - knowledge_scope_mapping
  - access_tags_yaml
  - team360_sales_diagnosis_package_manual
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
risk_level: high
approval_notes: >
  Política de aislamiento entre clientes, organizaciones, workspaces
  y knowledge scopes. Define cómo se evita la fuga de conocimiento
  cross-customer y cross-workspace.
---

# Aislamiento por scope y cliente

## Principio fundamental

Cada consulta de retrieval se ejecuta contra un knowledge_scope específico. No hay mezcla automática entre scopes, organizaciones ni workspaces.

---

## knowledge_scope como barrera de aislamiento

El `knowledge_scope_code` delimita el universo de chunks disponibles para una consulta. Un retrieval solo ve chunks de su propio scope.

**Reglas:**
- Cada organización tiene su(s) knowledge_scope(s) asignado(s).
- Cada workspace dentro de una organización puede tener su propio scope.
- No se puede acceder a chunks de un scope diferente desde una consulta.
- El aislamiento es por diseño, no por convención.

**Ejemplo:**
- `ks_team360_sales_diagnosis` solo contiene chunks de Team360.live.
- Un cliente diferente (organización distinta) tendría su propio scope.
- Una consulta en `ks_team360_sales_diagnosis` no ve chunks de otro scope.

---

## Cross-customer isolation

**NUNCA compartir conocimiento entre clientes distintos.**

Cada cliente/organización tiene su propio knowledge_scope aislado. Aunque dos clientes tengan procesos de negocio idénticos, sus scopes son independientes.

**Cómo responder:**
- "No podemos usar conocimiento de otro cliente. Cada organización tiene su knowledge_scope aislado por diseño."
- "Si el caso de uso se repite, debe documentarse en cada scope por separado."

**Riesgo si no se aplica:** Fuga de información sensible entre clientes. Violación de privacidad y confidencialidad.

---

## Workspace isolation

Cada workspace tiene su propio knowledge_scope. Workspaces de la misma organización no comparten knowledge automáticamente.

**Reglas:**
- `organization_code` identifica la organización.
- `workspace_code` identifica el workspace dentro de la organización.
- El retrieval filtra por ambos.
- Un workspace no puede acceder al knowledge de otro workspace.

**Ejemplo Team360:**
- Organización: `team360_live`
- Workspace: `team360_public_site`
- Scope: `ks_team360_sales_diagnosis`

---

## Runtime target vs package context

El package tiene dos niveles de contexto:

### Package/platform context
El paquete vive como entidad de plataforma en:
- `organization_code: team360`
- `workspace_code: team360_platform`

### Runtime/default target
El primer despliegue cliente corre en:
- `default_runtime_organization_code: team360_live`
- `default_runtime_workspace_code: team360_public_site`

**Regla:** No mezclar ambos contextos. El package context es de plataforma. El runtime target es del cliente. Un documento puede targetear el runtime sin que eso signifique que el package cambie de contexto.

---

## Access tags como protección adicional

Los `access_tags` definen qué roles pueden acceder a cada documento. Ver `_metadata/access-tags.yaml` para la lista completa.

**Reglas:**
- Cada documento en approved debe declarar sus access_tags.
- El retrieval debe respetar los tags del contexto de la consulta.
- Un documento sin tag `public` no debe ser visible en consultas públicas.

---

## Qué NO está permitido

- No mezclar chunks de diferentes knowledge_scopes en una misma consulta.
- No exponer chunks de una organización a otra.
- No permitir que un workspace acceda a chunks de otro workspace sin configuración explícita.
- No usar knowledge de un cliente para responder a otro, aunque los casos sean similares.

---

## Cómo responder preguntas de scope

**"¿Puedo usar conocimiento de otro cliente?"**
"No. Cada organización tiene su knowledge_scope aislado. No se comparte conocimiento entre clientes."

**"¿El paquete de ventas puede responder sobre otras áreas?"**
"El paquete de ventas (pkg_sales_diagnosis) cubre diagnóstico de automatización de ventas y procesos afines. No responde fuera de su alcance."

**"¿Team360.live puede usar knowledge de otro workspace?"**
"No. Cada workspace tiene su propio knowledge_scope independiente."

**"¿Puedo mezclar knowledge de diagnóstico de ventas con automation_diagnosis?"**
"Son scopes separados. Cada consulta se ejecuta contra un scope específico. No hay mezcla automática."

---

## Referencias

- `[[identificadores-y-nombres-comerciales]]`: Códigos y alcances
- `[[reglas-anti-overpromise]]`: Reglas vinculantes
- `[[team360_sales_diagnosis_package_manual]]`: Offer Decision
- `_metadata/access-tags.yaml`: Tags de acceso válidos
- `_metadata/knowledge-scope-mapping.yaml`: Mapeo de scopes
