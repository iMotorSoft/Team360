# PostgreSQL Knowledge Graph Navigation — Reporte detallado

**Experimento:** PostgreSQL Knowledge Graph Navigation — Fase 1.6c
**Grafo:** 27 nodos, 48 aristas
**Casos de traversal:** 12

---

## 1. Resumen ejecutivo

- **Resultado:** 12/12 casos pasaron (100.0%)
- **Score total:** 24 (rango: -36 a 36)
- **Nodos prohibidos encontrados:** 0

### Decisión

**PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para primera etapa KnowledgeMap.**
ArangoDB no es necesario ahora.

## 2. Resultados por caso de traversal

### 2.1 Casos exitosos (12)

#### ✅ `tc_01` — Profundizar desde sales_diagnosis: debe navegar a minimum_slots → useful_diagnos

- **Score:** +2
- **Dirección:** forward, max_depth=4
- **Nodos visitados:** 8
- **Nodos esperados encontrados:** 3/3
- **Razón comercial:** _Validar que el grafo permite profundizar desde el dominio general hasta conceptos concretos._

#### ✅ `tc_02` — Retroceder desde whatsapp_handoff: debe llevar a planned_extension → commercial_

- **Score:** +2
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 3
- **Nodos esperados encontrados:** 2/2
- **Razón comercial:** _WhatsApp handoff no debe aparecer como capacidad lista. Debe llevar a planned_extension y límites._

#### ✅ `tc_03` — Retroceder desde step_to_action: debe llevar a planned_extension → commercial_li

- **Score:** +2
- **Dirección:** backward, max_depth=3
- **Nodos visitados:** 3
- **Nodos esperados encontrados:** 2/2
- **Razón comercial:** _Step-to-Action es planned_extension. Nunca debe conectar a sellable_today._

#### ✅ `tc_04` — Desde automatable: no debe llegar a sellable_today como equivalente. Demostrar q

- **Score:** +2
- **Dirección:** bidirectional, max_depth=2
- **Nodos visitados:** 8
- **Nodos esperados encontrados:** 2/2
- **Razón comercial:** _Crucial: automatable != sellable_today. El grafo debe mostrar la relación not_equivalent y los límites._

#### ✅ `tc_05` — Desde chunk_offer_decision: navegar a commercial_limits → planned_extension → su

- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 3
- **Nodos esperados encontrados:** 2/2
- **Razón comercial:** _Un chunk recuperado por pgvector debe conectar a límites comerciales y extensiones planificadas._

#### ✅ `tc_06` — Desde knowledge_base_service: navegar a metadata_auditability → access_tags → cr

- **Score:** +2
- **Dirección:** forward, max_depth=4
- **Nodos visitados:** 15
- **Nodos esperados encontrados:** 3/3
- **Razón comercial:** _Knowledge Base as a Service requiere metadatos auditables, tags de acceso y aislamiento._

#### ✅ `tc_07` — Filtro por package_code pkg_sales_diagnosis

- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2
- **Nodos esperados encontrados:** 1/1
- **Razón comercial:** _El paquete debe contener solo su dominio. No filtrar nodos de otros paquetes._

#### ✅ `tc_08` — Filtro por knowledge_scope_code ks_team360_sales_diagnosis

- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 3
- **Nodos esperados encontrados:** 1/1
- **Razón comercial:** _Scope debe aislar su paquete. No debe devolver nodos fuera de este scope._

#### ✅ `tc_09` — Filtro por runtime target team360_live / team360_public_site

- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2
- **Nodos esperados encontrados:** 1/1
- **Razón comercial:** _Runtime target define el contexto de ejecución. No debe mezclar con otros targets._

#### ✅ `tc_10` — Cross-customer isolation: nodo de otro scope simulado no debe aparecer

- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 4
- **Nodos esperados encontrados:** 1/1
- **Razón comercial:** _Aislamiento cross-customer: un scope de cliente A no debe devolver nodos de cliente B._

#### ✅ `tc_11` — Navegación parent/child: package → domain → concepts

- **Score:** +2
- **Dirección:** forward, max_depth=5
- **Nodos visitados:** 6
- **Nodos esperados encontrados:** 5/5
- **Razón comercial:** _Desde el paquete debe poder navegarse la jerarquía completa hasta conceptos hoja._

#### ✅ `tc_12` — Overpromise protection: lead_capture, whatsapp_handoff, diagnostic_code deben ll

- **Score:** +2
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 4
- **Nodos esperados encontrados:** 2/2
- **Razón comercial:** _Toda capacidad futura debe navegar a planned_extension. Nunca a sellable_today ni ready._

## 3. Estadísticas de navegación

### Nodos por frecuencia de visita

| Rango | Nodo | Label | Visitas |
|-------|------|-------|---------|
| 1 | `commercial_limits` | Límites comerciales | 8 |
| 2 | `planned_extension` | Extensión planificada | 7 |
| 3 | `sales_diagnosis` | Diagnóstico de automatización de ventas | 7 |
| 4 | `package_sales_diagnosis` | Paquete pkg_sales_diagnosis | 5 |
| 5 | `concrete_orientation` | Orientación concreta | 4 |
| 6 | `useful_diagnosis` | Diagnóstico útil | 4 |
| 7 | `knowledge_scope_sales_diagnosis` | Knowledge scope ks_team360_sales_diagnosis | 4 |
| 8 | `automatable` | Automatizable | 3 |
| 9 | `minimum_slots` | Slots mínimos | 3 |
| 10 | `sellable_today` | Vendible hoy | 3 |
| 11 | `whatsapp_handoff` | WhatsApp Handoff | 2 |
| 12 | `chunk_offer_decision` | Chunk: Offer Decision | 2 |
| 13 | `cross_customer_isolation` | Aislamiento cross-customer | 2 |
| 14 | `step_to_action` | Step-to-Action | 1 |
| 15 | `node_path_hierarchy` | Jerarquía node_path | 1 |

### Distribución de profundidad

- max_depth=2: 1 casos
- max_depth=3: 6 casos
- max_depth=4: 4 casos
- max_depth=5: 1 casos

## 4. Efectividad de tipos de relación

El grafo contiene 48 aristas con los siguientes tipos de relación:

| Tipo de relación | Frecuencia |
|------------------|------------|
| `planned_extension_of` | 4 |
| `depends_on` | 4 |
| `includes` | 3 |
| `requires` | 2 |
| `supports` | 2 |
| `not_equivalent` | 2 |
| `references_concept` | 2 |
| `describes_capability` | 2 |
| `feeds_into` | 2 |
| `mentions_concept` | 2 |
| `scoped_by` | 2 |
| `aims_for` | 2 |
| `defines` | 1 |
| `limits` | 1 |
| `triggers` | 1 |
| `bounded_by` | 1 |
| `uses` | 1 |
| `enforced_by` | 1 |
| `contains_domain` | 1 |
| `scopes_package` | 1 |
| `deploys_scope` | 1 |
| `identifies` | 1 |
| `derived_from` | 1 |
| `belongs_to_package` | 1 |
| `respects` | 1 |
| `protects_against_overpromise` | 1 |
| `organizes` | 1 |
| `supports_answer` | 1 |
| `enables` | 1 |
| `leverages` | 1 |
| `exemplifies` | 1 |

## 5. Recomendaciones

### Implementación PostgreSQL

Si se adopta PostgreSQL, implementar con:

- `knowledge_graph_nodes` con node_id (PK), node_type, node_path, knowledge_scope_code, metadata JSONB
- `knowledge_graph_edges` con edge_id (PK), from_node_id (FK), to_node_id (FK), relation_type, direction, weight, metadata JSONB
- Índice GIN en node_path para filtro por prefijo jerárquico
- Índice GIN en metadata para filtros semánticos
- Vistas materializadas para traversals frecuentes

### Cuándo reconsiderar ArangoDB

- Más de 50k nodos con 5+ niveles de profundidad
- Traversals con múltiples condiciones de filtro en <100ms
- Grafos con >10 conexiones/nodo en promedio
- Necesidad de shortest-path, PageRank u otros algoritmos nativos de grafo

## 6. Próximos pasos

1. Migrar golden graph a tablas productivas (migración 004)
2. Crear endpoints de navegación: `GET /knowledge/graph/traverse`
3. Integrar con retrieval: enriquecer chunks de pgvector con navegación de grafo
4. Agregar más casos al golden graph (cross-package, cross-scope, cross-customer)
5. Benchmark contra ArangoDB con el mismo dataset (opcional)

---

_Generado por Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment. 2026-06-09 14:42 UTC_