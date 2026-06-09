---
document_code: identificadores_y_nombres_comerciales
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
area_key: glosario
topic_key: identificadores_tecnicos
node_path: "/glosario/identificadores-tecnicos"
title: "Identificadores técnicos y nombres comerciales"
visibility: public
locale: es
owner: Team360
last_review: 2026-06-09
access_tags:
  - public
  - ejecutivo_comercial
  - gerente_ventas
  - director_comercial
  - analista_tecnico
evidence_level: validated_by_source
evidence_sources:
  - package_profile_yaml
  - knowledge_scope_mapping
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
risk_level: low
approval_notes: >
  Tabla de equivalencias entre nombres comerciales visibles y
  códigos técnicos del sistema. Sirve para que el retrieval
  distinga correctamente entre nombre comercial e identificador
  de sistema.
---

# Identificadores técnicos y nombres comerciales

## Propósito

Este documento existe porque el test ácido de retrieval (Fase 1.6d) mostró que el sistema confunde nombres comerciales con identificadores técnicos. Vera es nombre comercial, no package_code ni knowledge_scope_code.

---

## Regla fundamental

**Vera es nombre comercial visible. NO es identificador técnico.**

Vera no debe usarse como:
- ❌ `package_code`
- ❌ `knowledge_scope_code`
- ❌ `assistant_instance_code`
- ❌ `service_code`
- ❌ `template_code`

---

## Tabla de equivalencias

| Concepto | Nombre comercial | Identificador técnico |
|----------|-----------------|----------------------|
| Asistente | Vera / Asistente Inteligente Vera | `team360_sales_diagnosis` |
| Paquete de conocimiento | — | `pkg_sales_diagnosis` |
| Scope de conocimiento | — | `ks_team360_sales_diagnosis` |
| Servicio | — | `svc_sales_diagnosis` |
| Template | — | `team360_sales_automation_diagnosis` |
| Organización (plataforma) | Team360 | `team360` |
| Organización (runtime) | Team360.live | `team360_live` |
| Workspace (runtime) | Team360 Public Site | `team360_public_site` |
| Workspace (plataforma) | Team360 Platform | `team360_platform` |

---

## Identificadores del paquete

| Campo | Valor |
|-------|-------|
| `package_code` | `pkg_sales_diagnosis` |
| `knowledge_scope_code` | `ks_team360_sales_diagnosis` |
| `assistant_instance_code` | `team360_sales_diagnosis` |
| `service_code` | `svc_sales_diagnosis` |
| `template_code` | `team360_sales_automation_diagnosis` |
| `commercial_name` | Vera / Asistente Inteligente Vera |
| `organization_code` (platform) | `team360` |
| `workspace_code` (platform) | `team360_platform` |
| `default_runtime_organization_code` | `team360_live` |
| `default_runtime_workspace_code` | `team360_public_site` |

---

## Estructura de un knowledge_scope

```
ks_{organization}_{domain}
```

Ejemplo: `ks_team360_sales_diagnosis` = scope de knowledge de Team360 para diagnóstico de ventas.

---

## Estructura de un package_code

```
pkg_{domain}
```

Ejemplo: `pkg_sales_diagnosis` = paquete de conocimiento de diagnóstico de ventas.

---

## Estructura de un service_code

```
svc_{domain}
```

Ejemplo: `svc_sales_diagnosis` = servicio de diagnóstico de ventas.

---

## Estructura de un assistant_instance_code

```
{organization}_{domain}
```

Ejemplo: `team360_sales_diagnosis` = instancia del asistente de Team360 para diagnóstico de ventas.

---

## Cómo responder preguntas sobre identificadores

**"¿Vera es el package?"**
"No. Vera es el nombre comercial del asistente. El package_code es `pkg_sales_diagnosis`."

**"¿Qué código técnico tiene Vera?"**
"Vera no tiene código técnico. El assistant_instance_code es `team360_sales_diagnosis`."

**"¿Cuál es el knowledge scope?"**
"`ks_team360_sales_diagnosis` para el paquete de diagnóstico de ventas."

**"¿Vera y team360_sales_diagnosis son lo mismo?"**
"Vera es el nombre comercial visible. `team360_sales_diagnosis` es el identificador técnico de la instancia del asistente. Son el mismo asistente, pero Vera es el nombre que ve el usuario."

---

## Referencias

- `[[aislamiento-scope-cliente]]`: Cómo se usan los scopes para aislar conocimiento
- `[[reglas-anti-overpromise]]`: Regla de no confundir Vera con identificador técnico
- `[[team360_sales_diagnosis_package_manual]]`: Contexto del paquete
- `_metadata/package-profile.yaml`: Perfil completo del paquete
