# PostgreSQL Knowledge Graph Navigation — Fase 1.6c

**Date:** 2026-06-09 14:41 UTC
**Graph:** 27 nodes, 48 edges
**Traversal cases:** 12
**Mode:** SQL simulation (recursive CTE generated for each case)

## Resumen ejecutivo

- **12/12** casos pasaron criterio de aceptación (100.0%)
- **0** nodos prohibidos encontrados en total
- **Score total:** 24 (rango posible: -36 a 36)

### ¿PostgreSQL 18 + adjacency tables + recursive CTE alcanza para KnowledgeMap?

- Casos fallidos: 0/12
- Casos con nodos prohibidos: 0

**Conclusión: PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para primera etapa KnowledgeMap. ArangoDB no es necesario ahora.**

### ¿Cómo escala el enfoque?

- Adjacency table: O(n) por nivel de profundidad, row estimates crecen con factor de ramificación
- Recursive CTE: bien para 3-4 niveles de profundidad en grafos de hasta ~10k nodos
- node_path + GIN index: permite filtrado por prefijo sin join recursivo
- Combinación adj + node_path: cubre navegación jerárquica + relacional

### ¿Cuándo considerar ArangoDB?

- Más de 50k nodos con más de 5 niveles de profundidad
- Traversals con múltiples condiciones de filtro en tiempo real (<100ms)
- Grafos con alta densidad de aristas (más de 10 conexiones por nodo en promedio)
- Necesidad de shortest-path, k-shortest-paths, PageRank u otros algoritmos nativos de grafo

## Resultados por caso

### ✅ `tc_01` — Profundizar desde sales_diagnosis: debe navegar a minimum_slots → useful_diagnos

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=4
- **Nodos visitados:** 8 (concrete_orientation, useful_diagnosis, planned_extension, automatable, sales_diagnosis, minimum_slots, commercial_limits, sellable_today)
- **Caminos encontrados:** 7
- **Esperados encontrados:** 3/3 → concrete_orientation, minimum_slots, useful_diagnosis
- **Razón comercial:** _Validar que el grafo permite profundizar desde el dominio general hasta conceptos concretos._

### ✅ `tc_02` — Retroceder desde whatsapp_handoff: debe llevar a planned_extension → commercial_

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 3 (planned_extension, commercial_limits, whatsapp_handoff)
- **Caminos encontrados:** 2
- **Esperados encontrados:** 2/2 → planned_extension, commercial_limits
- **Razón comercial:** _WhatsApp handoff no debe aparecer como capacidad lista. Debe llevar a planned_extension y límites._

### ✅ `tc_03` — Retroceder desde step_to_action: debe llevar a planned_extension → commercial_li

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** backward, max_depth=3
- **Nodos visitados:** 3 (planned_extension, step_to_action, commercial_limits)
- **Caminos encontrados:** 2
- **Esperados encontrados:** 2/2 → planned_extension, commercial_limits
- **Razón comercial:** _Step-to-Action es planned_extension. Nunca debe conectar a sellable_today._

### ✅ `tc_04` — Desde automatable: no debe llegar a sellable_today como equivalente. Demostrar q

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** bidirectional, max_depth=2
- **Nodos visitados:** 8 (concrete_orientation, chunk_offer_decision, useful_diagnosis, planned_extension, automatable, sales_diagnosis, commercial_limits, sellable_today)
- **Caminos encontrados:** 7
- **Esperados encontrados:** 2/2 → commercial_limits, sellable_today
- **Razón comercial:** _Crucial: automatable != sellable_today. El grafo debe mostrar la relación not_equivalent y los límites._

### ✅ `tc_05` — Desde chunk_offer_decision: navegar a commercial_limits → planned_extension → su

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 3 (planned_extension, chunk_offer_decision, commercial_limits)
- **Caminos encontrados:** 2
- **Esperados encontrados:** 2/2 → planned_extension, commercial_limits
- **Razón comercial:** _Un chunk recuperado por pgvector debe conectar a límites comerciales y extensiones planificadas._

### ✅ `tc_06` — Desde knowledge_base_service: navegar a metadata_auditability → access_tags → cr

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=4
- **Nodos visitados:** 15 (concrete_orientation, useful_diagnosis, planned_extension, node_path_hierarchy, automatable, access_tags, cross_customer_isolation, knowledge_base_service...)
- **Caminos encontrados:** 14
- **Esperados encontrados:** 3/3 → access_tags, metadata_auditability, cross_customer_isolation
- **Razón comercial:** _Knowledge Base as a Service requiere metadatos auditables, tags de acceso y aislamiento._

### ✅ `tc_07` — Filtro por package_code pkg_sales_diagnosis

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2 (package_sales_diagnosis, sales_diagnosis)
- **Caminos encontrados:** 1
- **Esperados encontrados:** 1/1 → sales_diagnosis
- **Razón comercial:** _El paquete debe contener solo su dominio. No filtrar nodos de otros paquetes._

### ✅ `tc_08` — Filtro por knowledge_scope_code ks_team360_sales_diagnosis

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 3 (knowledge_scope_sales_diagnosis, package_sales_diagnosis, sales_diagnosis)
- **Caminos encontrados:** 2
- **Esperados encontrados:** 1/1 → package_sales_diagnosis
- **Razón comercial:** _Scope debe aislar su paquete. No debe devolver nodos fuera de este scope._

### ✅ `tc_09` — Filtro por runtime target team360_live / team360_public_site

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2 (runtime_target_team360_live, knowledge_scope_sales_diagnosis)
- **Caminos encontrados:** 1
- **Esperados encontrados:** 1/1 → knowledge_scope_sales_diagnosis
- **Razón comercial:** _Runtime target define el contexto de ejecución. No debe mezclar con otros targets._

### ✅ `tc_10` — Cross-customer isolation: nodo de otro scope simulado no debe aparecer

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 4 (knowledge_scope_sales_diagnosis, cross_customer_isolation, package_sales_diagnosis, sales_diagnosis)
- **Caminos encontrados:** 3
- **Esperados encontrados:** 1/1 → knowledge_scope_sales_diagnosis
- **Razón comercial:** _Aislamiento cross-customer: un scope de cliente A no debe devolver nodos de cliente B._

### ✅ `tc_11` — Navegación parent/child: package → domain → concepts

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=5
- **Nodos visitados:** 6 (concrete_orientation, useful_diagnosis, sales_diagnosis, minimum_slots, commercial_limits, package_sales_diagnosis)
- **Caminos encontrados:** 5
- **Esperados encontrados:** 5/5 → concrete_orientation, useful_diagnosis, sales_diagnosis, minimum_slots, commercial_limits
- **Razón comercial:** _Desde el paquete debe poder navegarse la jerarquía completa hasta conceptos hoja._

### ✅ `tc_12` — Overpromise protection: lead_capture, whatsapp_handoff, diagnostic_code deben ll

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 4 (planned_extension, commercial_limits, lead_capture, whatsapp_handoff)
- **Caminos encontrados:** 3
- **Esperados encontrados:** 2/2 → planned_extension, commercial_limits
- **Razón comercial:** _Toda capacidad futura debe navegar a planned_extension. Nunca a sellable_today ni ready._

## Decisión recomendada

### Criterios

1. **Navegación de grafo básica:** 12/12 casos pasan (100.0%)
2. **Nodos prohibidos en resultados:** 0 casos con leaks al scope incorrecto
3. **Complejidad máxima probada:** 4 niveles de profundidad, bidireccional
4. **Tipos de relaciones probadas:** requiere, soporta, limita, planifica, identifica, organiza, deriva

### Recomendación

**PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para implementar KnowledgeMap**
en la primera etapa productiva. ArangoDB no es necesario ahora y queda como opción de escala futura.

El enfoque combinado de adjacency table (relaciones explícitas) + node_path (jerarquía)
cubre los casos de uso actuales de navegación. Implementar con:
- `knowledge_graph_nodes` (node_id, node_type, node_path, knowledge_scope_code, metadata)
- `knowledge_graph_edges` (edge_id, from_node_id, to_node_id, relation_type, direction, weight, metadata)
- Índice GIN en node_path para filtro por prefijo
- Índice GIN en metadata para filtros semánticos
- Vistas materializadas para traversals frecuentes (p.ej. package → domain → concepts)

### Próximos pasos

1. Si se adopta PostgreSQL: migrar golden graph a tablas productivas con migración 004
2. Si se evalúa ArangoDB: comparar el mismo golden graph contra AQL traversal queries
3. Crear endpoints de navegación: GET /knowledge/graph/traverse
4. Integrar con retrieval: los chunks de pgvector pueden enriquecerse con navegación de grafo

---

_Generated by Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment_