# Telchi — Historical Business Query Inventory V1

Auditoría de conocimiento existente en `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Sólo se escribieron artefactos del informe; SAP, datos, Foundation y runtime no fueron modificados.

## Conclusión acreditada

La hipótesis se confirma en un alcance mínimo verificable: hay más conocimiento empresarial ejecutado que la única lectura fija del asistente. La exhaustividad semántica integral sigue **PARTIAL**; no se convierte extracción automática en negocio resuelto.

- **30 operaciones históricas**: 10 ventas, 10 OINM, 5 cruces y 5 OITW, con SQL SAP/DuckLake, resultados, hashes EXACT y drilldown. Registro y resultados originales son externos y accesibles.
- **30 operaciones reproducidas en CURRENT**, con **35 partes SQL** read-only. Se sustituyeron sólo relaciones por pins del reader y se reconstruyeron bindings desde scope/discovery preservados; no se ejecutó SAP.
- **9 READY_FOUNDATION**, **8 READY_CONDITIONAL**, **13 REQUIRES_METRIC_DEFINITION** dentro de esas 30. Primer estado: hechos nativos exactos, sin reetiquetarlos como ventas netas, rankings físicos o cifras actuales de SAP.
- **8 investigaciones adicionales con 24 contratos SQL** tienen ejecución N/N declarada y artefactos explícitos. Se conservan como evidencia documental con reservas de versión, distinta de paridad por hashes; ver research_chains.csv.
- **19 objetivos métricos baseline adicionales** preservados con resultados/períodos. El inventario SAP previo documenta 116 gates, 79 objetos, 31 relaciones, 26 reglas y 18 gaps; esas cifras son evidencia histórica, no conteos nuevos de preguntas SQL completas.
- Foundation publica también **purchasing, material_supply y receivables_collections**; se verificaron referencias selladas, schemas y muestras acotadas. No todos sus análisis históricos fueron reproducidos ni declarados READY.
- **26 familias conceptuales** permiten planificar reutilización. No equivalen a 26 capabilities listas. Primera selección recomendada: cobertura, últimos documentos, período monetario explícito, SKU y cliente; validar sus brechas antes de habilitar.

## Alcance físico y método

Se completó el recorrido recursivo de investigation antes de extender búsqueda a módulo, documentación relacionada, reportes, evidencia externa, LlmFit y source legacy. No se siguieron symlinks ni dependencias externas como negocio.

| Alcance | Archivos inventariados |
| --- | ---: |
| A_INVESTIGATION | 1219 |
| G_REPOSITORY_EXTENSION | 454 |
| G_EXTERNAL_EVIDENCE | 1856 |
| G_EXTERNAL_LLMFIT | 602 |
| G_EXTERNAL_LEGACY_SOURCE | 55 |
| Total | 4186 |

Investigation: **1.219 archivos**, 82.450.514 bytes al recorrido inicial; {'.md': 119, '.py': 383, '.pyc': 445, '.sql': 102, '.jsonl': 2, '.json': 37, '.csv': 117, '.yaml': 14}. Las 445 entradas pyc tienen metadata/hash, sin extracción de fuente. Conteo por primer directorio: {'.': 8, '__pycache__': 2, 'atomic': 24, 'datalake': 12, 'docs': 104, 'sql': 101, 'validation': 968}. El manifest incluye todos los directorios/conteos, no sólo esta tabla.

No hubo directorios inaccesibles identificados. Un archivo `.json` externo tiene JSON válido seguido por SUMMARY; se registró JSONDecodeError y se verificó el prefijo sin reescribirlo. Los 37 gzip externos son datasets generados, inventariados/hash; no se leyeron completos. No se copiaron Parquet ni datasets grandes.

## Catálogo de preguntas y SQL

Los conteos distinguen ocurrencias, redacciones, consultas técnicas y operaciones verificadas. No se acredita un total de intents empresariales únicos con deduplicación por texto.

| Medida | Conteo | Interpretación |
| --- | ---: | --- |
| Ocurrencias pregunta/objetivo/candidato | 5791 | Una fila por ubicación y redacción; conserva duplicados históricos |
| Redacciones lexicalmente distintas | 1398 | Casefold/espacios; no equivalencia semántica ni frecuencia de usuario |
| Ocurrencias SQL/implementación extraídas | 3684 | Archivos, AST, JSON, CSV y bloques Markdown; incluye técnico/fixtures |
| Ocurrencias read-query | 2783 | No todas son preguntas de negocio o SQL completo dinámico |
| Grupos SQL lexicales | 2687 | No demuestra equivalencia SQL por álgebra/semántica |
| SQL con ejecución acreditada / declarada | 94 | 70 ocurrencias registry + 24 contratos declarados en informes; 78 textos lexicales distintos |
| Asociaciones pregunta-SQL explícitas/contextuales | 111 | 70 registry; 24 artefactos de reportes con ejecución declarada; 17 misma sección Markdown sin ejecución |
| Operaciones empresariales nativas verificadas | 30 | Límite inferior; no sumar automáticamente los baselines ni todos los PASS anteriores |

Ambos catálogos CEO están cubiertos: **Q001–Q074 (74)** y **Q-V2-001–008 (8)**. query_catalog.md tiene **22 bloques SQL** preservados con secciones; parte son placeholders/ilustración y no se marcaron ejecutados por el título «realizadas». Todos los **102 archivos .sql** de investigation se encuentran representados. Se incluyeron SQL embebido y reportes, además de catálogos.

La extracción automática incluye encabezados de métricas y rótulos internos de query parts. Las filas conservan extraction_kind y UNRESOLVED cuando falta evaluación. Builders dinámicos y múltiples statements por implementación no se reconstruyeron exhaustivamente; el conteo SQL es de artefactos/expresiones, no un total definitivo de consultas de negocio.

## Foundation efectiva y casos del asistente

El reader oficial resolvió la única CURRENT y su manifest; el acceso fue READ_ONLY confirmado sobre el attachment, con pins de publicación, dos threads y 512 MB por conexión propia.

- Publicación: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`; snapshot de commit **1408**; base de manifest **1322**.
- Componentes lógicos: credit_memo, material_supply, oinm, oitw, purchasing, receivables_collections, reference, sales. component_count=5 corresponde al set core, no demuestra ausencia de los tres extensibles.
- Source as_of ventas 2026-09-24; publication data_as_of 2026-09-28; commit 2026-10-01. Ninguna de estas fechas equivale a «SAP actual».
- Máxima DocDate **2026-09-24**; último mes con filas **septiembre**. Agosto llega a 31/08, pero no se certificó último mes empresarial completo ni toda historia desde 2022.
- Mayo: 36.242 facturas BS activas, DocTotal **8.761.459,22** del snapshot; no importe neto tras NC ni importe por producto. Las reservas y estados Y/C están en executive_query_reuse.
- Calenta: candidatos de producto, no cliente/marca único acreditado; cuatro SKUs tienen filas mayo. Alias ambiguos y namespace `SAP_B1_HANA` vs `SAP_HANA` impiden un join literal fiable. LIKE incluye calentadores ajenos.
- Neto producto, conversiones de cantidades, universo comercial temporal y ranking genérico conservan gaps. El catálogo TelchiAI sigue limitado a sales.source_top_items fijo; ninguna capability nueva fue habilitada.

## Entregables y trazabilidad

Los CSV permiten continuar revisión sin repetir discovery. Los JSON contienen pruebas read-only y manifest efectivo; los informes separan conclusiones y criterios de integración.

- [questions_master.csv](questions_master.csv), [sql_master.csv](sql_master.csv), [question_sql_links.csv](question_sql_links.csv).
- [physical_inventory.csv](physical_inventory.csv), [coverage_manifest.json](coverage_manifest.json), [duplicate_files.csv](duplicate_files.csv), [external_references.csv](external_references.csv).
- [verified_operations.csv](verified_operations.csv), [foundation_readiness.csv](foundation_readiness.csv), [historical_findings.csv](historical_findings.csv), [evidence_index.csv](evidence_index.csv).
- [query_families.md](query_families.md), [business_semantics.md](business_semantics.md), [telchiai_priority_matrix.md](telchiai_priority_matrix.md), [unresolved_questions.md](unresolved_questions.md), [executive_query_reuse.md](executive_query_reuse.md).
- [foundation_current_inspection.json](foundation_current_inspection.json), [foundation_reproduction.json](foundation_reproduction.json), [foundation_business_cases.json](foundation_business_cases.json).

## Gaps y límites de exhaustividad

Todos los archivos del root principal tienen metadata/hash y los textos fueron escaneados, pero extracción amplia no acredita cada cadena ni una taxonomía semántica definitiva.

1. Queda adjudicar títulos/objetivos/variantes y reconstruir SQL dinámico, además de vincular resultados granulares fuera del registry directo. No se inventan asociaciones por dominio o coincidencia de tablas.
2. Los archivos idénticos, SQL lexicalmente repetido, resultados de snapshots distintos y correcciones se conservan. 112 grupos de archivos idénticos; no eliminación.
3. No se acreditó equivalencia SQL completa ni «versión corregida/reemplazada» para cada par. Historia FAIL/PASS permanece en evidence_index y fuentes; un PASS de gate no convierte todo SQL cercano en validado.
4. Material privado quedó fuera del inventario. El connector oficial consumió su configuración para Foundation; no se imprimieron credenciales ni se accedió a SAP/servicios externos.
5. Referencias literales externas incluyen paths obsoletos y plantillas; external_references no presenta cada literal faltante como documento perdido. Markdown links existentes están en reference_integrity.

## Validación, impacto y continuación

La validación final se registra en validation_results.json y validation_commands.log. Los gates de inventario tienen alcance explícito; no se declara PASS integral desde el total de archivos.

Impacto transversal: ninguno sobre código/datos/configuración. Sólo nuevos archivos bajo este directorio; worktree previo preservado; sin commit, push, deploy, DDL/DML, SAP, modelos ni servicios creados. Los procesos SQL propios cerraron sus conexiones.

Próximo paso: completar el adjudicado semántico y los vínculos SQL→resultado del resto de investigaciones; después formalizar bindings/permisos y contratos de un primer conjunto de familias. No repetir SAP ni comenzar desde cero.

## Gates finales

Los controles de integridad y documentación pasan. La auditoría integral permanece PARTIAL por adjudicación semántica y trazabilidad pendientes, no por un fallo funcional de Foundation.

Ver [gates.md](gates.md) y [validation_results.json](validation_results.json) para evidencia y límites por garantía.
