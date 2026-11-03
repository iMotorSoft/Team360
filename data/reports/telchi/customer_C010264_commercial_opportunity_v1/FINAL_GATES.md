# Gates finales — oportunidades comerciales L&S

Entrega PROVISIONAL con productos, rankings y brechas comerciales concretas. La corrección transaccional está verificada; la pertenencia propia no está certificada. Resultado global PARTIAL, no PASS final.

## Estados exigidos

Los estados separan la comparación reproducible del universo candidato de la certificación empresarial pendiente.

```text
TELCHI_LS_CUSTOMER_PROFILE=PASS
TELCHI_LS_PORTFOLIO_EVIDENCE=PARTIAL
TELCHI_LS_MEMBERSHIP_CLASSIFICATION=PARTIAL
TELCHI_LS_GLOBAL_TOP20=PROVISIONAL
TELCHI_LS_CUSTOMER_TOP20=PROVISIONAL
TELCHI_LS_OPPORTUNITY_GROUP_A=PROVISIONAL
TELCHI_LS_OPPORTUNITY_GROUP_B=PROVISIONAL
TELCHI_LS_OPPORTUNITY_GROUP_C=PROVISIONAL
TELCHI_LS_INDEPENDENT_VALIDATION=PARTIAL
TELCHI_LS_EXECUTIVE_DELIVERY=PROVISIONAL
TELCHI_LS_COMMERCIAL_OPPORTUNITIES_V1=PARTIAL
```

## Resultados y certidumbre

Se entregan dos rankings de 20 filas, cinco oportunidades A, seis B y diez C. Todos usan el mismo universo candidato, período, grano y métrica; ninguno es un Top 20 propio certificado.

| Garantía | Evidencia y resultado |
| --- | --- |
| Perfil del cliente | Baseline completo reutilizado: 52 facturas, 3 NC, 98 ItemCodes, 822 líneas; montos y vendedor observados preservados |
| Binding | FoundationReader antes/después: CURRENT foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408; READ_ONLY verificado |
| Frecuencia global | 6.581 productos vendidos; join y consulta independiente por semijoin producen idénticas frecuencias |
| Compras cliente | Nuevo cotejo sólo de frecuencias por semijoin coincide con los 98 artículos baseline; no se reconstruye detalle ni perfil |
| Joins de referencia | Catálogo enriquecido sin duplicados ItemCode, unido después del agregado; unicidad/orfandad Atomic reutilizada del baseline pinned |
| Universo exploratorio | 915 vendidos, 19 códigos no L; incluye 58 RAW_MATERIAL y 129 OTHER_INPUT, sin restricción sólo a terminados; no afirma titularidad |
| Clasificación local | Evidencia y conflictos por artículo; CANDIDATE/UNKNOWN no se convierten en CONFIRMED. Ningún tercero confirmado se incluye; ausencia de terceros identificados NO demuestra inexistencia |
| Rankings y conjuntos | SQL independiente row_number / anti-joins / intersección sobre hechos capturados coincide con Python; 20 posiciones por ranking, A=5/B=6/C=10 |
| Frontera global | Corte 4.186, siguiente 4.081, máximo fuera de Uc 2.006; estabilidad frente a omitidos condicionada a acreditar los 20 actuales |
| Frontera cliente | Corte 13, siguiente 13; desempate ItemCode explícito; B puede cambiar por exclusiones anteriores |
| Pertenencia final | No acreditada: 11 artículos primera ola, 36 en shortlist incluyendo unión de rankings y cinco reemplazos; ampliar sólo si exclusiones afectan corte |
| Magnitudes | Frecuencia OINV activa, no facturación/volumen físico por producto. ORIN separado, no resta de ocurrencias; DocTotal sólo perfil documental |
| Cobertura | 01/01–24/09/2026; 24 parcial. No se certifica integridad histórica ni se afirma nunca comprado |

## Validaciones ejecutadas

Las pruebas y SQL verifican la comparación candidata; no crean una autorización comercial de pertenencia.

- Backend: `uv run --no-sync pytest modules/telchi/datalake/tests/test_product_business_classification.py modules/telchi/datalake/tests/test_product_commercial_semantics.py modules/telchi/datalake/tests/test_messaging_sales_query.py -q`: **58 passed**, 1,33 s; warning uv de dependencias de desarrollo obsoletas, sin modificar configuración.
- FINAL_SQL_EVIDENCE.json registra SELECT exactos y resultados; FINAL_VALIDATION.json conserva SQL independiente y resultados A/B/C, orden, frontera y hashes baseline.
- Revisión final: resumen ejecutivo, resolución de portfolio, CSV de rankings/oportunidades y reconciliación de artefactos; originales preservados mediante hashes. Encabezados anteriores archivados en baseline_partial/ antes de completar los CSV.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: aprobados. LAT escanea su alcance configurado; se revisaron además párrafos introductorios de los tres Markdown nuevos y sus resultados comerciales. Warnings LAT de init/version y clave LLM ausentes, sin cambios de configuración.
- Cotejo offline final: hashes de todos los originales/encabezados archivados, perfil/meses, 55 elaborados y 43 fraccionados del cliente, posiciones, sets A/B/C, etiquetas PROVISIONAL y repetición del SQL independiente concordantes.
- Se corrigió un alias de tabla fuera de alcance en el cotejo cliente y un alias SQL position antes de emitir resultados. Errores del runner analítico temporal, no defectos de aplicación ni abortos ambientales.

## Reproducción sin capacidades nuevas

La evidencia permite recalcular y comparar resultados sin modificar Foundation ni persistir una clasificación. Usar sólo la versión y snapshot registrados; abortar ante cambio de CURRENT.

Desde backend, con DuckLakeConnector.session(read_only=True), FoundationReader y el presupuesto indicado, ejecutar las consultas de FINAL_SQL_EVIDENCE.json. Comparar por ItemCode las frecuencias globales join/semijoin y cliente/baseline.

Para cotejo offline: abrir DuckDB con 2 threads/512 MiB, cargar FINAL_VALIDATION.json y ejecutar independent_rank_sql e independent_complement_sql. Los resultados esperados están en el mismo JSON; rutas absolutas del worktree actual. Estos SELECT sólo leen archivos de evidencia.

## Recursos y ownership

Host compartido BUSY_BUT_SAFE: 8 cores, load inicial 3,10/3,04/2,86, 6.142 MiB disponibles y swap histórica de 1 MiB sin actividad sostenida. Carga secuencial acotada, sin materialización del Data Lake.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=2
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

DuckDB 2 threads, 512 MiB, sin spill para scans; pytest secuencial. Durante revisión: load 5,05, 5.408 MiB disponibles, swap de unos 5 MiB sin presión sostenida en vmstat. No servidores, browsers ni workers persistentes creados.

## Scope y próximo paso

Rama feature/console-backend-core; HEAD 09d2ec715a31bb88574d734eacb9f437f008624e preservado. Scope único: directorio de informes solicitado. Impacto transversal nulo en runtime; sólo interpretación analítica local.

Se completaron TOP20_TELCHI.csv, TOP20_LS.csv y COMMERCIAL_OPPORTUNITIES.csv; se agregaron evidencia por producto, shortlist, Top100, SQL, validación, resolución, resumen ejecutivo y estos gates. DIRECTORIO_RESUMEN.md y toda la evidencia previa no autorizada a cambiar permanecen intactos.

Sin SAP, cambio CURRENT, Atomic/Reference, Business Semantics, State Engine, RBAC, commit, push ni deploy. Próximo paso: revisión comercial de los 11 prioritarios y cierre selectivo de frontera; no se pide normalizar los 16.934 productos SAP.
