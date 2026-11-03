# Gates de cierre del inventario

Los estados distinguen cobertura física, trazabilidad y aptitud semántica. PASS de integridad o evaluación no implica capability productiva ni auditoría integral completa.

```text
TELCHI_INVESTIGATION_PHYSICAL_INVENTORY=PASS
TELCHI_HISTORICAL_QUESTIONS_INVENTORY=PARTIAL
TELCHI_HISTORICAL_SQL_INVENTORY=PARTIAL
TELCHI_QUESTION_SQL_TRACEABILITY=PARTIAL
TELCHI_HISTORICAL_RESULTS_TRACEABILITY=PARTIAL
TELCHI_BUSINESS_SEMANTICS_INVENTORY=PARTIAL
TELCHI_FOUNDATION_READINESS_MAPPING=PARTIAL
TELCHI_QUERY_FAMILIES=PARTIAL
TELCHI_EXECUTIVE_QUERY_REUSE=PASS
TELCHI_INVENTORY_COVERAGE=PARTIAL
TELCHI_HISTORICAL_QUERY_AUDIT=PARTIAL
```

| Gate | Evidencia y límite |
| --- | --- |
| TELCHI_INVESTIGATION_PHYSICAL_INVENTORY | physical_inventory.csv; validation_results.json: INVESTIGATION_PHYSICAL_COVERAGE 1219/1219 y hashes preservados |
| TELCHI_HISTORICAL_QUESTIONS_INVENTORY | 5791 ocurrencias/1398 textos; catálogos CEO 74+8 cubiertos; adjudicación semántica de variantes/candidatos pendiente |
| TELCHI_HISTORICAL_SQL_INVENTORY | 102 archivos SQL y SQL embebido indexados; builders y statements dinámicos no reconstruidos integralmente |
| TELCHI_QUESTION_SQL_TRACEABILITY | 111 links: 70 registry, 24 report artifacts, 17 misma sección; faltan cadenas granulares del resto |
| TELCHI_HISTORICAL_RESULTS_TRACEABILITY | 30 operaciones con resultados/hashes; 24 contratos documentados y 19 baselines; no resultado individual atribuido a todo SQL |
| TELCHI_BUSINESS_SEMANTICS_INVENTORY | business_semantics.md preserva estados/sources y gaps; el catálogo completo no está adjudicado por operación |
| TELCHI_FOUNDATION_READINESS_MAPPING | CURRENT 1408 confirmado; 30 operaciones/35 partes reproducidas; 9 READY, 8 condicionales, 13 requieren métrica; resto sin reproducción completa |
| TELCHI_QUERY_FAMILIES | 26 grupos respaldados por referencias e IDs; agrupación completa y equivalencia semántica aún no certificadas |
| TELCHI_EXECUTIVE_QUERY_REUSE | executive_query_reuse.md evalúa los seis casos, SQL/evidencia/semántica/mapping/gap/esfuerzo y recomendaciones; PASS de evaluación, no de habilitación |
| TELCHI_INVENTORY_COVERAGE | investigation físico completo y 4186 archivos extendidos; gzip de datos sólo metadata/hash y fuentes dinámicas pendientes |
| TELCHI_HISTORICAL_QUERY_AUDIT | Conocimiento reutilizable confirmado con evidencia; no total definitivo de intents y cadenas empresariales en toda la historia |

Validaciones: [validation_results.json](validation_results.json), [validation_commands.log](validation_commands.log), [verified_operations.csv](verified_operations.csv).
