# PostgreSQL Knowledge Graph Navigation — Fase 1.6c

**Date:** 2026-06-09 14:39 UTC
**Graph:** 27 nodes, 48 edges
**Traversal cases:** 12

## Resumen ejecutivo

- **5/12** casos pasaron criterio de aceptación (41.7%)
- **0** nodos prohibidos encontrados en total
- **Score total:** -3 (rango posible: -36 a 36)

### ¿PostgreSQL 18 + adjacency tables + recursive CTE alcanza para KnowledgeMap?

- Casos fallidos: 7/12
- Casos con nodos prohibidos: 0

**Conclusión: Evaluar ArangoDB si la navegación del grafo es insuficiente para el alcance requerido.**

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
- **Nodos visitados:** 8 (concrete_orientation, minimum_slots, useful_diagnosis, commercial_limits, sales_diagnosis, planned_extension, automatable, sellable_today)
- **Caminos encontrados:** 7
- **Esperados encontrados:** 3/3 → concrete_orientation, minimum_slots, useful_diagnosis
- **Razón comercial:** _Validar que el grafo permite profundizar desde el dominio general hasta conceptos concretos._

### ❌ `tc_02` — Retroceder desde whatsapp_handoff: debe llevar a planned_extension → commercial_

- **Estado:** FALLÓ
- **Score:** -3
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 1 (whatsapp_handoff)
- **Caminos encontrados:** 0
- **Esperados encontrados:** 0/2 → 
- **Faltantes:** planned_extension, commercial_limits
- **Razón comercial:** _WhatsApp handoff no debe aparecer como capacidad lista. Debe llevar a planned_extension y límites._

### ❌ `tc_03` — Retroceder desde step_to_action: debe llevar a planned_extension → commercial_li

- **Estado:** FALLÓ
- **Score:** -3
- **Dirección:** backward, max_depth=3
- **Nodos visitados:** 1 (step_to_action)
- **Caminos encontrados:** 0
- **Esperados encontrados:** 0/2 → 
- **Faltantes:** planned_extension, commercial_limits
- **Razón comercial:** _Step-to-Action es planned_extension. Nunca debe conectar a sellable_today._

### ❌ `tc_04` — Desde automatable: no debe llegar a sellable_today como equivalente. Demostrar q

- **Estado:** FALLÓ
- **Score:** +1
- **Dirección:** bidirectional, max_depth=2
- **Nodos visitados:** 2 (sellable_today, automatable)
- **Caminos encontrados:** 1
- **Esperados encontrados:** 1/2 → sellable_today
- **Faltantes:** commercial_limits
- **Razón comercial:** _Crucial: automatable != sellable_today. El grafo debe mostrar la relación not_equivalent y los límites._

### ✅ `tc_05` — Desde chunk_offer_decision: navegar a commercial_limits → planned_extension → su

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 3 (planned_extension, commercial_limits, chunk_offer_decision)
- **Caminos encontrados:** 2
- **Esperados encontrados:** 2/2 → planned_extension, commercial_limits
- **Razón comercial:** _Un chunk recuperado por pgvector debe conectar a límites comerciales y extensiones planificadas._

### ✅ `tc_06` — Desde knowledge_base_service: navegar a metadata_auditability → access_tags → cr

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=4
- **Nodos visitados:** 15 (cross_customer_isolation, node_path_hierarchy, minimum_slots, commercial_limits, sales_diagnosis, knowledge_base_service, access_tags, useful_diagnosis...)
- **Caminos encontrados:** 14
- **Esperados encontrados:** 3/3 → access_tags, cross_customer_isolation, metadata_auditability
- **Razón comercial:** _Knowledge Base as a Service requiere metadatos auditables, tags de acceso y aislamiento._

### ✅ `tc_07` — Filtro por package_code pkg_sales_diagnosis

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2 (package_sales_diagnosis, sales_diagnosis)
- **Caminos encontrados:** 1
- **Esperados encontrados:** 1/1 → sales_diagnosis
- **Razón comercial:** _El paquete debe contener solo su dominio. No filtrar nodos de otros paquetes._

### ❌ `tc_08` — Filtro por knowledge_scope_code ks_team360_sales_diagnosis

- **Estado:** FALLÓ
- **Score:** -3
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 1 (knowledge_scope_sales_diagnosis)
- **Caminos encontrados:** 0
- **Esperados encontrados:** 0/1 → 
- **Faltantes:** package_sales_diagnosis
- **Razón comercial:** _Scope debe aislar su paquete. No debe devolver nodos fuera de este scope._

### ❌ `tc_09` — Filtro por runtime target team360_live / team360_public_site

- **Estado:** FALLÓ
- **Score:** -3
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 1 (runtime_target_team360_live)
- **Caminos encontrados:** 0
- **Esperados encontrados:** 0/1 → 
- **Faltantes:** knowledge_scope_sales_diagnosis
- **Razón comercial:** _Runtime target define el contexto de ejecución. No debe mezclar con otros targets._

### ✅ `tc_10` — Cross-customer isolation: nodo de otro scope simulado no debe aparecer

- **Estado:** PASÓ
- **Score:** +2
- **Dirección:** forward, max_depth=3
- **Nodos visitados:** 2 (cross_customer_isolation, knowledge_scope_sales_diagnosis)
- **Caminos encontrados:** 1
- **Esperados encontrados:** 1/1 → knowledge_scope_sales_diagnosis
- **Razón comercial:** _Aislamiento cross-customer: un scope de cliente A no debe devolver nodos de cliente B._

### ❌ `tc_11` — Navegación parent/child: package → domain → concepts

- **Estado:** FALLÓ
- **Score:** +1
- **Dirección:** forward, max_depth=5
- **Nodos visitados:** 5 (concrete_orientation, minimum_slots, useful_diagnosis, sales_diagnosis, package_sales_diagnosis)
- **Caminos encontrados:** 4
- **Esperados encontrados:** 4/5 → concrete_orientation, minimum_slots, useful_diagnosis, sales_diagnosis
- **Faltantes:** commercial_limits
- **Razón comercial:** _Desde el paquete debe poder navegarse la jerarquía completa hasta conceptos hoja._

### ❌ `tc_12` — Overpromise protection: lead_capture, whatsapp_handoff, diagnostic_code deben ll

- **Estado:** FALLÓ
- **Score:** -3
- **Dirección:** backward, max_depth=4
- **Nodos visitados:** 1 (lead_capture)
- **Caminos encontrados:** 0
- **Esperados encontrados:** 0/2 → 
- **Faltantes:** planned_extension, commercial_limits
- **Razón comercial:** _Toda capacidad futura debe navegar a planned_extension. Nunca a sellable_today ni ready._

## Decisión recomendada

### Criterios

1. **Navegación de grafo básica:** 5/12 casos pasan (41.7%)
2. **Nodos prohibidos en resultados:** 0 casos con leaks al scope incorrecto
3. **Complejidad máxima probada:** 4 niveles de profundidad, bidireccional
4. **Tipos de relaciones probadas:** requiere, soporta, limita, planifica, identifica, organiza, deriva

### Recomendación

**Evaluar ArangoDB para la implementación productiva de KnowledgeMap.**
El enfoque PostgreSQL muestra limitaciones en los casos de navegación probados.

### Próximos pasos

1. Si se adopta PostgreSQL: migrar golden graph a tablas productivas con migración 004
2. Si se evalúa ArangoDB: comparar el mismo golden graph contra AQL traversal queries
3. Crear endpoints de navegación: GET /knowledge/graph/traverse
4. Integrar con retrieval: los chunks de pgvector pueden enriquecerse con navegación de grafo

---

_Generated by Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment_