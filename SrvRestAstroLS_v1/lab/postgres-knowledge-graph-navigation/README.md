# PostgreSQL Knowledge Graph Navigation — Fase 1.6c

## Objetivo

Validar con criterio reproducible si PostgreSQL 18 + adjacency tables + recursive CTE alcanza para implementar el primer KnowledgeMap navegable de Team360, antes de decidir si hace falta ArangoDB.

## Preguntas que responde

1. ¿Se puede navegar un grafo de conocimiento con PostgreSQL sin ArangoDB?
2. ¿El enfoque adjacency table + recursive CTE escala para el dominio de Team360?
3. ¿La navegación respeta scopes de conocimiento, límites comerciales y reglas de aislamiento?
4. ¿Hay leak de conceptos prohibidos en traversals (overpromise)?
5. ¿Cuándo sería necesario migrar a ArangoDB?

## Dataset

`golden_graph/knowledge_graph_cases.json` contiene:

| Elemento | Cantidad |
|----------|----------|
| Nodos | 27 |
| Aristas | 48 |
| Casos de traversal | 12 |
| Tipos de relación | 16 |

### Nodos representan

- **domain**: dominio principal (sales_diagnosis)
- **concept**: conceptos del dominio (minimum_slots, useful_diagnosis, automatable)
- **capability**: capacidades técnicas (step_to_action, whatsapp_handoff)
- **package**: paquete de conocimiento (pkg_sales_diagnosis)
- **scope**: knowledge scope (ks_team360_sales_diagnosis)
- **runtime**: runtime target (team360_live)
- **principle**: principios transversales (cross_customer_isolation)
- **data**: objetos de datos (retrieval_chunk, approved_document)
- **chunk**: chunks concretos con embedding (chunk_offer_decision)

### Casos de traversal

| ID | Descripción | Dirección |
|----|-------------|-----------|
| tc_01 | Profundizar desde sales_diagnosis | forward |
| tc_02 | Retroceder desde whatsapp_handoff | backward |
| tc_03 | Retroceder desde step_to_action | backward |
| tc_04 | automatable != sellable_today | bidirectional |
| tc_05 | Desde chunk_offer_decision a límites | forward |
| tc_06 | Knowledge Base as a Service completo | forward |
| tc_07 | Filtro por package_code | forward |
| tc_08 | Filtro por knowledge_scope_code | forward |
| tc_09 | Filtro por runtime target | forward |
| tc_10 | Aislamiento cross-customer | forward |
| tc_11 | Jerarquía package → domain → concepts | forward |
| tc_12 | Overpromise protection desde lead_capture | backward |

## Scoring

| Condición | Puntos |
|-----------|--------|
| Path fragment exacto encontrado | +3 |
| Todos los nodos esperados encontrados | +2 |
| Al menos un nodo esperado encontrado | +1 |
| Nodo prohibido en resultados | **-5** (cada uno) |
| Ningún nodo esperado encontrado | **-3** |

## Uso

```bash
cd SrvRestAstroLS_v1

# Ejecutar experimento
uv run python lab/postgres-knowledge-graph-navigation/run_experiment.py

# Con simulación SQL
uv run python lab/postgres-knowledge-graph-navigation/run_experiment.py --sql-simulation

# Generar reporte detallado
uv run python lab/postgres-knowledge-graph-navigation/scripts/generate_report.py

# Generar infografía HTML
uv run python lab/postgres-knowledge-graph-navigation/scripts/generate_infographics.py

# Con archivo específico
uv run python lab/postgres-knowledge-graph-navigation/scripts/generate_report.py \
  --results-file results/graph_navigation_20260609_144135.json
```

## Requisitos

- Python 3.10+
- No necesita servicios externos (grafo local en JSON)
- No necesita BD, OpenAI, ni embeddings
- `--sql-simulation` solo genera SQL como referencia no ejecutable

## Output

| Archivo | Contenido |
|---------|-----------|
| `results/{prefix}.json` | Resultados completos de todos los casos |
| `results/{prefix}.md` | Reporte Markdown generado por `run_experiment.py` |
| `results/{prefix}_detailed_report.md` | Reporte detallado con estadísticas |
| `infografias/{prefix}_infografia.html` | Infografía HTML ejecutiva |

## No toca

- ❌ ArangoDB (es el objeto de evaluación, no se instala)
- ❌ Milvus
- ❌ OpenAI / embeddings
- ❌ LLM chat completion
- ❌ Endpoints HTTP
- ❌ Frontend
- ❌ Backend productivo
- ❌ Migraciones
- ❌ BD / escrituras productivas
- ❌ diagnosis / automation_diagnosis

## Resultado

**12/12 casos pasan (100%). 0 nodos prohibidos encontrados.**

Conclusión: PostgreSQL 18 + adjacency tables + recursive CTE es suficiente
para la primera etapa de KnowledgeMap. ArangoDB se mantiene como benchmark
de escala futura (50k+ nodos, 5+ niveles de profundidad).

## Próximos pasos

1. Migrar golden graph a tablas productivas (migración 004)
2. Crear endpoints de navegación: `GET /knowledge/graph/traverse`
3. Integrar con retrieval: enriquecer chunks de pgvector con navegación de grafo
4. Agregar más casos al golden graph (cross-package, cross-scope, cross-customer)
5. Benchmark contra ArangoDB con el mismo dataset (opcional)
